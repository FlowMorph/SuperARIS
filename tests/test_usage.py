"""全部用合成日志核对只读统计，禁止访问真实会话或启动客户端。"""
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from superaris.cli import main
from superaris.usage import collect, render

NOW = 1700000000
HOUR = 3600


def stamp(at):
    return datetime.fromtimestamp(at, timezone.utc).isoformat()


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def claude(sid, mid="msg-1", at=NOW - 30, usage=None, **fields):
    return {"type": "assistant", "sessionId": sid, "timestamp": stamp(at),
            "message": {"id": mid, "content": "PRIVATE CONVERSATION MUST NOT LEAK", "usage": usage if usage is not None else {
                "input_tokens": 100, "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 8, "output_tokens": 4}}, **fields}


def meta(sid, project, **fields):
    return {"type": "session_meta", "payload": {"id": sid, "cwd": str(project), **fields}}


def codex(total=120, output=5, at=NOW - 20, *, last=True):
    counters = {"input_tokens": total, "cached_input_tokens": 20, "output_tokens": output}
    info = {"total_token_usage": counters}
    if last:
        info["last_token_usage"] = {"input_tokens": 120, "cached_input_tokens": 20, "output_tokens": 5}
    return {"type": "event_msg", "timestamp": stamp(at),
            "payload": {"type": "token_count", "info": info}}


@pytest.fixture
def logs(tmp_path):
    project = tmp_path / "project"
    workbench = project / ".aris" / "workbench"
    workbench.mkdir(parents=True)
    claude_root, codex_root = tmp_path / "claude", tmp_path / "codex"
    claude_root.mkdir()
    codex_root.mkdir()
    roles = {"main": {"harness": "claude", "native_session_id": "cc-main", "pane_id": "p1"},
             "engineer": {"harness": "codex", "native_session_id": "cx-engineer", "pane_id": "p2"}}
    (workbench / "launch.json").write_text(json.dumps({"roles": roles, "ui_language": "en"}))

    def run(**options):
        return collect(project, claude_root=claude_root, codex_root=codex_root, now=NOW, **options)

    return project, workbench, claude_root, codex_root, roles, run


def row(report, role, client):
    return report["roles"][role]["clients"][client]


def codes(report):
    return {d["code"] for d in report["diagnostics"]}


def test_precise_sessions_same_cwd_multiple_roles_and_unattributed(logs):
    project, wb, cc, cx, roles, run = logs
    roles["writer"] = {"harness": "claude", "native_session_id": "cc-writer"}
    (wb / "launch.json").write_text(json.dumps({"roles": roles}))
    jsonl(cc / "cc-main.jsonl", [claude("cc-main", cwd=str(project))])
    jsonl(cc / "cc-writer.jsonl", [claude("cc-writer", "msg-2", cwd=str(project))])
    jsonl(cc / "outside.jsonl", [claude("outside", "msg-3", cwd=str(project))])
    jsonl(cc / "unrelated.jsonl", [claude("unrelated", "msg-4", cwd="/unrelated")])
    jsonl(cx / "engineer.jsonl", [meta("cx-engineer", project), codex()])
    result = run()
    assert row(result, "main", "claude")["requests"] == 1
    assert row(result, "writer", "claude")["requests"] == 1
    assert row(result, "unattributed", "claude")["requests"] == 1
    assert result["clients"]["claude"]["requests"] == 3
    assert row(result, "main", "claude")["share"] == pytest.approx(1 / 3)
    assert "PRIVATE CONVERSATION" not in json.dumps(result)


def test_claude_duplicate_streaming_snapshots_cache_write_and_cross_file_copy(logs):
    project, wb, cc, cx, roles, run = logs
    first = claude("cc-main")
    updated = claude("cc-main", at=NOW - 10, usage={"input_tokens": 100,
        "cache_read_input_tokens": 20, "cache_creation_input_tokens": 8, "output_tokens": 6})
    jsonl(cc / "cc-main.jsonl", [first, first, updated])
    jsonl(cc / "copy" / "cc-main.jsonl", [first])
    result = run()
    usage = row(result, "main", "claude")
    assert usage["requests"] == 1
    assert usage["output_tokens"] == 6
    assert usage["cache_write_tokens"] == 8
    assert usage["equivalent_tokens"] == 142


def test_codex_last_not_added_to_total_repeated_snapshots_and_equal_requests(logs):
    project, wb, cc, cx, roles, run = logs
    jsonl(cx / "engineer.jsonl", [meta("cx-engineer", project), codex(), codex(at=NOW - 19),
                                  codex(240, 10, at=NOW - 10)])
    result = run()
    usage = row(result, "engineer", "codex")
    assert usage["requests"] == 2
    assert usage["raw_input_tokens"] == 240
    assert usage["input_tokens"] == 200
    assert usage["cache_read_tokens"] == 40
    assert usage["cache_write_tokens"] is None
    assert usage["equivalent_tokens"] == 254
    assert usage["status"] == "partial"


def test_codex_total_only_uses_baseline_delta_request_count_unknown(logs):
    project, wb, cc, cx, roles, run = logs
    jsonl(cx / "engineer.jsonl", [meta("cx-engineer", project), codex(120, 5, at=NOW - 100, last=False),
                                  codex(240, 10, at=NOW - 50, last=False)])
    result = run()
    usage = row(result, "engineer", "codex")
    assert usage["requests"] is None
    assert usage["observed"]["input_tokens"] == 120
    assert usage["input_tokens"] is None
    assert "codex_cumulative_baseline_missing_or_reset" in codes(result)


def test_codex_baseline_before_start_then_last_is_valid_but_delta_crossing_start_unknown(logs):
    project, wb, cc, cx, roles, run = logs
    jsonl(cx / "engineer.jsonl", [meta("cx-engineer", project), codex(120, 5, at=NOW - 100, last=False),
                                  codex(240, 10, at=NOW - 20, last=False)])
    result = run(since=NOW - 50)
    assert row(result, "engineer", "codex")["equivalent_tokens"] is None
    assert "cumulative_delta_crosses_range_start" in codes(result)


def test_explicit_child_link_and_unlinked_history(logs):
    project, wb, cc, cx, roles, run = logs
    jsonl(cx / "engineer.jsonl", [meta("cx-engineer", project), codex()])
    jsonl(cx / "child.jsonl", [meta("child", project, parent_thread_id="cx-engineer"), codex()])
    jsonl(cx / "old.jsonl", [meta("old", project), codex()])
    result = run()
    assert row(result, "engineer", "codex")["requests"] == 2
    assert row(result, "unattributed", "codex")["requests"] == 1


def test_claude_explicit_native_subagent_directory_link(logs):
    project, wb, cc, cx, roles, run = logs
    jsonl(cc / "cc-main.jsonl", [claude("cc-main")])
    jsonl(cc / "cc-main" / "subagents" / "agent-child.jsonl", [claude("cc-main", "child-msg")])
    assert row(run(), "main", "claude")["requests"] == 2


def test_conflicting_binding_never_defaults_to_main(logs):
    project, wb, cc, cx, roles, run = logs
    roles["writer"] = {"harness": "claude", "native_session_id": "cc-main"}
    (wb / "launch.json").write_text(json.dumps({"roles": roles}))
    jsonl(cc / "cc-main.jsonl", [claude("cc-main")])
    result = run()
    assert row(result, "main", "claude")["requests"] is None
    assert row(result, "unattributed", "claude")["requests"] == 1
    assert "ambiguous_session_owner" in codes(result)


@pytest.mark.parametrize("damage", ["tail", "schema", "missing_field", "missing_id", "timestamp"])
def test_damaged_or_incomplete_logs_mark_partial_and_never_fill_missing_zero(logs, damage):
    project, wb, cc, cx, roles, run = logs
    event = claude("cc-main")
    if damage == "schema":
        event = {"type": "unrecognized", "usage": {"unexpected": 500}}
    elif damage == "missing_field":
        del event["message"]["usage"]["cache_creation_input_tokens"]
    elif damage == "missing_id":
        del event["message"]["id"]
    elif damage == "timestamp":
        del event["timestamp"]
    path = jsonl(cc / "cc-main.jsonl", [event])
    if damage == "tail":
        with path.open("a") as stream:
            stream.write('{"secret":"DO NOT LEAK')
    result = run()
    usage = row(result, "main", "claude")
    assert usage["equivalent_tokens"] is None
    assert usage["status"] in ("partial", "unknown")
    assert result["diagnostics"]
    assert "DO NOT LEAK" not in json.dumps(result)


def test_real_zero_versus_missing_root_and_unsupported_client(logs):
    project, wb, cc, cx, roles, run = logs
    usage = {"input_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "output_tokens": 0}
    jsonl(cc / "cc-main.jsonl", [claude("cc-main", usage=usage)])
    roles["writer"] = {"harness": "agy", "native_session_id": "agy-1"}
    (wb / "launch.json").write_text(json.dumps({"roles": roles}))
    result = collect(project, claude_root=cc, codex_root=cx / "missing", now=NOW)
    assert row(result, "main", "claude")["equivalent_tokens"] == 0
    assert row(result, "main", "claude")["share"] is None
    assert result["clients"]["codex"]["input_tokens"] is None
    assert result["clients"]["codex"]["observed"] == {}
    assert result["sources"]["codex"]["status"] == "missing"
    assert row(result, "writer", "agy")["requests"] is None


def test_range_upper_bound_does_not_replace_in_range_message_with_later_snapshot(logs):
    project, wb, cc, cx, roles, run = logs
    jsonl(cc / "cc-main.jsonl", [claude("cc-main", at=NOW - 100), claude("cc-main", at=NOW - 10)])
    result = run(since=NOW - 200, until=NOW - 50)
    assert row(result, "main", "claude")["requests"] == 1


def test_cli_json_text_language_and_readonly_no_runtime_or_secret_read(logs, monkeypatch, capsys):
    project, wb, cc, cx, roles, run = logs
    jsonl(cc / "cc-main.jsonl", [claude("cc-main")])
    before = {p: p.read_bytes() for root in (project, cc, cx) for p in root.rglob("*") if p.is_file()}
    from superaris import client, runtime, usage
    original_read = usage._read

    def read_binding_only(path, diagnostics):
        assert path.name == "launch.json"
        return original_read(path, diagnostics)

    monkeypatch.setattr(usage, "_read", read_binding_only)
    monkeypatch.setattr(runtime, "start", lambda *a, **k: pytest.fail("不能启动会话"))
    monkeypatch.setattr(client.Herdr, "__init__", lambda *a, **k: pytest.fail("不能调用Herdr"))
    args = ["usage", str(project), "--claude-root", str(cc), "--codex-root", str(cx),
            "--since", stamp(NOW - HOUR), "--until", stamp(NOW)]
    assert main([*args, "--by-role", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "roles" in result
    assert "weekly_quotas" not in result and "deliveries" not in result
    assert main([*args, "--by-role"]) == 0
    text = capsys.readouterr().out
    assert "requests" in text and "unknown" in text
    assert "PRIVATE CONVERSATION" not in text
    assert main([*args, "--lang", "zh"]) == 0
    assert "本地用量" in capsys.readouterr().out
    assert all(path.read_bytes() == content for path, content in before.items())
    assert set(before) == {p for root in (project, cc, cx) for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("options", [["--hours", "nan"], ["--hours", "0"], ["--since", "yesterday"], ["--until", "2026-01-01T00:00:00"]])
def test_cli_bad_range_is_observable_error(logs, capsys, options):
    project, wb, cc, cx, roles, run = logs
    assert main(["usage", str(project), *options]) == 1
    assert "error:" in capsys.readouterr().err


def test_codex_native_thread_spawn_source_links_child_without_cwd_guess(logs):
    project, wb, cc, cx, roles, run = logs
    jsonl(cx / "engineer.jsonl", [meta("cx-engineer", project), codex()])
    jsonl(cx / "child.jsonl", [meta("native-child", project, source={"subagent": {
        "thread_spawn": {"parent_thread_id": "cx-engineer", "depth": 1}}}), codex()])
    result = run()
    assert row(result, "engineer", "codex")["requests"] == 2


def test_known_role_and_metadata_only_role_do_not_make_partial_total_complete(logs):
    project, wb, cc, cx, roles, run = logs
    roles["writer"] = {"harness": "claude", "native_session_id": "cc-writer"}
    (wb / "launch.json").write_text(json.dumps({"roles": roles}))
    jsonl(cc / "cc-main.jsonl", [claude("cc-main")])
    jsonl(cc / "cc-writer.jsonl", [{"type": "system", "sessionId": "cc-writer", "timestamp": stamp(NOW - 10)}])
    result = run()
    assert row(result, "main", "claude")["input_tokens"] == 100
    assert row(result, "writer", "claude")["input_tokens"] is None
    assert result["clients"]["claude"]["input_tokens"] is None
    assert result["clients"]["claude"]["observed"]["input_tokens"] == 100
    assert row(result, "main", "claude")["share"] is None


def structured(sid="cx-engineer", response="response-1", total=120, output=5, at=NOW - 20):
    legacy = codex(total, output, at=at)
    usage = {**legacy["payload"]["info"]["last_token_usage"],
             "cache_write_input_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 125}
    cumulative = {**legacy["payload"]["info"]["total_token_usage"],
                  "cache_write_input_tokens": 0, "reasoning_output_tokens": 0,
                  "total_tokens": total + output}
    return {"type": "token_usage_record", "timestamp": stamp(at), "ordinal": 1,
            "payload": {"thread_id": sid, "turn_id": "turn-1", "session_id": "runtime-1",
                        "root_turn_id": "turn-1", "response_id": response, "usage": usage,
                        "turn_token_usage": cumulative, "thread_token_usage": cumulative}}


@pytest.mark.parametrize("formats", ["structured", "structured-first", "legacy-first"])
def test_current_codex_response_and_legacy_pair_count_once(logs, formats):
    project, wb, cc, cx, roles, run = logs
    current = structured()
    events = [current, current] if formats == "structured" else (
        [current, codex(), codex()] if formats == "structured-first" else [codex(), current])
    jsonl(cx / "engineer.jsonl", [meta("cx-engineer", project), *events])
    result = run()
    usage = row(result, "engineer", "codex")
    assert usage["requests"] == 1
    assert usage["raw_input_tokens"] == 120
    assert usage["equivalent_tokens"] == 127
    assert usage["share"] == 1
    assert "usage_schema_unknown" not in codes(result)


@pytest.mark.parametrize("current", [False, True])
def test_copied_fork_prefix_not_billed_again_and_new_equal_request_retained(logs, current):
    project, wb, cc, cx, roles, run = logs
    first, second = codex(at=NOW - 60), codex(240, 10, at=NOW - 20)
    prefix = [structured(at=NOW - 60), first] if current else [first]
    new = [structured("child", "response-2", 240, 10), second] if current else [second]
    jsonl(cx / "parent.jsonl", [meta("cx-engineer", project), *prefix])
    jsonl(cx / "child.jsonl", [meta("child", project, forked_from_id="cx-engineer"), *prefix, *new])
    usage = row(run(), "engineer", "codex")
    assert usage["requests"] == 2
    assert usage["raw_input_tokens"] == 240
    assert usage["equivalent_tokens"] == 254
    # Range selection does not charge the out-of-window inherited request.
    usage = row(run(since=NOW - 40), "engineer", "codex")
    assert usage["requests"] == 1
    assert usage["raw_input_tokens"] == 120


def test_legacy_copied_prefix_uses_parent_response_provenance(logs):
    project, wb, cc, cx, roles, run = logs
    first = codex(at=NOW - 60)
    jsonl(cx / "parent.jsonl", [meta("cx-engineer", project), structured(at=NOW - 60), first])
    jsonl(cx / "child.jsonl", [meta("child", project, forked_from_id="cx-engineer"), first,
                               codex(240, 10)])
    assert row(run(), "engineer", "codex")["requests"] == 2


@pytest.mark.parametrize("current", [False, True])
def test_independent_equal_requests_in_fork_and_other_sessions_survive(logs, current):
    project, wb, cc, cx, roles, run = logs
    def events(sid, at, total=120, output=5):
        return ([structured(sid, "response-1", total, output, at=at), codex(total, output, at=at)]
                if current else [codex(total, output, at=at)])
    jsonl(cx / "parent.jsonl", [meta("cx-engineer", project), *events("cx-engineer", NOW - 60)])
    # A new equal-cost fork request advances the inherited cumulative total.
    jsonl(cx / "child.jsonl", [meta("child", project, forked_from_id="cx-engineer"),
                               *events("child", NOW - 20, 240, 10)])
    # Another session may have identical counters and even the same log timestamp.
    jsonl(cx / "other.jsonl", [meta("other", project), *events("other", NOW - 60)])
    result = run()
    assert row(result, "engineer", "codex")["requests"] == 2
    assert result["clients"]["codex"]["requests"] == 3
    assert result["clients"]["codex"]["raw_input_tokens"] == 360


def test_structured_response_ids_keep_distinct_zero_usage_requests(logs):
    project, wb, cc, cx, roles, run = logs
    events = [structured(response=r) for r in ("zero-1", "zero-2")]
    for event in events:
        for name in ("usage", "turn_token_usage", "thread_token_usage"):
            event["payload"][name] = {k: 0 for k in event["payload"][name]}
    jsonl(cx / "engineer.jsonl", [meta("cx-engineer", project), *events])
    usage = row(run(), "engineer", "codex")
    assert usage["requests"] == 2
    assert usage["equivalent_tokens"] == 0


def test_copied_fork_prefix_across_multiple_generations(logs):
    project, wb, cc, cx, roles, run = logs
    first, second = codex(at=NOW - 60), codex(240, 10, at=NOW - 40)
    jsonl(cx / "z-parent.jsonl", [meta("cx-engineer", project), first])
    jsonl(cx / "b-child.jsonl", [meta("child", project, forked_from_id="cx-engineer"), first, second])
    jsonl(cx / "a-grandchild.jsonl", [meta("grandchild", project, forked_from_id="child"), first,
                                    second, codex(360, 15)])
    assert row(run(), "engineer", "codex")["requests"] == 3


@pytest.mark.parametrize("current", [False, True])
def test_native_fork_rewritten_timestamps_use_original_usage_time(logs, current):
    project, wb, cc, cx, roles, run = logs
    def events(sid, response, at, total=120, output=5):
        old = codex(total, output, at=at)
        return [structured(sid, response, total, output, at=at), old] if current else [old]
    jsonl(cx / "parent.jsonl", [meta("cx-engineer", project),
                               *events("cx-engineer", "r1", NOW - 100)])
    jsonl(cx / "child.jsonl", [meta("child", project, forked_from_id="cx-engineer"),
                              *events("cx-engineer", "r1", NOW - 50),
                              *events("child", "r2", NOW - 20, 240, 10)])
    usage = row(run(), "engineer", "codex")
    assert usage["requests"] == 2
    assert usage["raw_input_tokens"] == 240
    usage = row(run(since=NOW - 60), "engineer", "codex")
    assert usage["requests"] == 1
    assert usage["raw_input_tokens"] == 120
