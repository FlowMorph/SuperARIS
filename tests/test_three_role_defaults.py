"""Unified role defaults: invoke installed product with public fake transports.

Run with the product's wheel-installed test interpreter from its repository so
the public tests.support/fake helpers are importable. No native agents run.
"""

import copy
import json
import os
from pathlib import Path
import subprocess

import pytest

from tests.support import CLI, make_aris_repo
from tests.test_aris_workbench import fake_herdr, project  # noqa: F401
from tests.test_superaris_wizard import Terminal


TEAMS = {
    "codex": {"main": "codex", "engineer": "codex", "writer": "codex"},
    "cc-codex": {"main": "claude", "engineer": "codex", "writer": "claude"},
    "cc-codex-agy": {"main": "claude", "engineer": "codex", "writer": "agy"},
}


@pytest.fixture(autouse=True)
def isolated_dependency(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("SUPERARIS_ARIS_REPO", str(make_aris_repo(tmp_path / "synthetic-aris")))
    monkeypatch.delenv("ARIS_REPO", raising=False)


def invoke(project, *options, environment=None):
    return subprocess.run([*CLI, "start", str(project), *options], env=environment,
                          capture_output=True, text=True, timeout=20, check=False)


def start(project, fake, *options):
    result = invoke(
        project, "--session", "isolated-test", "--no-attach", "--no-receiver", "--no-install",
        "--herdr-bin", str(fake["binary"]), *options, environment=fake["env"],
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("preset", TEAMS)
def test_plan_defaults_to_three_roles_and_retains_explicit_only_role(project, preset):
    before = {str(path.relative_to(project)): path.read_bytes() for path in project.rglob("*") if path.is_file()}
    result = invoke(project, "--plan", "--preset", preset)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert {role["role"]: role["harness"] for role in plan["roles"]} == TEAMS[preset]
    assert {role["role"] for role in plan["roles"] if role["active"]} == {"main", "engineer", "writer"}
    assert all(role["model"] is None for role in plan["roles"])
    assert plan["will_mutate"] is False
    if preset == "codex":
        implicit = invoke(project, "--plan")
        assert implicit.returncode == 0, implicit.stderr
        assert {role["role"]: role["harness"] for role in json.loads(implicit.stdout)["roles"] if role["active"]} == TEAMS[preset]
    explicit = invoke(project, "--plan", "--preset", preset, "--only-role", "main")
    assert explicit.returncode == 0, explicit.stderr
    assert {role["role"] for role in json.loads(explicit.stdout)["roles"] if role["active"]} == {"main"}
    assert {str(path.relative_to(project)): path.read_bytes() for path in project.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("preset", TEAMS)
def test_actual_default_starts_each_role_once_with_scoped_waiting_and_same_layout(project, fake_herdr, preset):
    preset_options = [] if preset == "codex" else ["--preset", preset]
    team = start(project, fake_herdr, *preset_options, "--task", "Main must inspect the approved study before assigning work.")
    roles = team["roles"]
    assert {name: role["harness"] for name, role in roles.items()} == TEAMS[preset]
    assert {action["role"] for action in team["actions"] if action["action"] == "started"} == set(TEAMS[preset])
    assert len({role["context"]["packet"] for role in roles.values()}) == 3
    assert "Main must inspect the approved study" in roles["main"]["inputs"]["task"]
    for name in ("engineer", "writer"):
        record = roles[name]
        assert "wait" in record["inputs"]["task"].lower()
        assert "Main must inspect the approved study" not in record["inputs"]["task"]
        assert record["inputs"]["write_scope"] != roles["main"]["inputs"]["write_scope"]
        assert record["inputs"]["write_scope"] in Path(record["context"]["role_file"]).read_text()
        assert record["inputs"]["task"] in Path(record["context"]["packet"]).read_text()
    engineer_scope = Path(roles["engineer"]["inputs"]["write_scope"])
    writer_scope = Path(roles["writer"]["inputs"]["write_scope"])
    assert not engineer_scope.is_relative_to(writer_scope)
    assert not writer_scope.is_relative_to(engineer_scope)
    main_packet = Path(roles["main"]["context"]["packet"]).read_text()
    assert "excluded from your write scope" in main_packet
    assert str(engineer_scope) in main_packet and str(writer_scope) in main_packet
    commands = json.loads(fake_herdr["state"].read_text())["commands"]
    starts = [args for args in commands if args[:2] == ["agent", "start"]]
    assert len(starts) == 3
    assert {args[args.index("--pane") + 1] for args in starts} == {role["pane_id"] for role in roles.values()}
    splits = [args for args in commands if args[:2] == ["pane", "split"]]
    assert [(args[2], args[args.index("--direction") + 1]) for args in splits] == [
        (roles["main"]["pane_id"], "right"), (roles["engineer"]["pane_id"], "down"),
    ]


@pytest.mark.parametrize("preset,selected,pending", [
    ("codex", ["main"], False),
    ("cc-codex", ["main", "engineer"], True),
])
def test_historical_team_noarg_reentry_does_not_expand_reset_or_resend(project, fake_herdr, preset, selected, pending, monkeypatch):
    options = ["--preset", preset, "--task", "Keep the historical authorized task.", "--model", "main=historical-model"]
    for name in selected:
        options += ["--only-role", name]
    start(project, fake_herdr, *options)
    launch = project / ".aris/workbench/launch.json"
    original = json.loads(launch.read_text())
    original["roles"]["main"]["delivery"].update(phase="unknown", error="historical unconfirmed delivery")
    if pending:
        arguments = ["start", str(project), "--session", "isolated-test", *options]
        original["pending_start"] = {
            "arguments": arguments,
            "roles": [{"role": name, "harness": original["roles"][name]["harness"], "active": True,
                       "model": original["roles"][name].get("requested_model"),
                       **original["roles"][name]["inputs"]} for name in selected],
        }
    launch.write_text(json.dumps(original))
    saved = copy.deepcopy(original)
    if pending:
        from superaris import cli, wizard
        replies = iter(["1", str(project), "1", "1"])
        monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
        monkeypatch.setattr(wizard, "capabilities", lambda: {
            "herdr": "fake", "codex": "fake", "claude": "fake", "agy": "fake", "brew": None,
        })
        selection = wizard.run()
        assert selection.arguments == saved["pending_start"]["arguments"]
        recovered_plan = cli.make_plan(cli.parser().parse_args(selection.arguments))
        assert {role["role"] for role in recovered_plan["roles"] if role["active"]} == set(selected)
    before = json.loads(fake_herdr["state"].read_text())
    result = start(project, fake_herdr)
    assert set(result["roles"]) == set(selected)
    after = json.loads(launch.read_text())
    for name in selected:
        for field in ("inputs", "requested_model", "context", "delivery", "pane_id", "pid"):
            assert after["roles"][name][field] == saved["roles"][name][field]
    assert after.get("pending_start") is None  # Completed membership; unknown receipt remains above.
    state = json.loads(fake_herdr["state"].read_text())
    assert state.get("submissions", []) == before.get("submissions", [])
    assert sum(args[:2] == ["agent", "start"] for args in state["commands"]) == len(selected)


@pytest.mark.parametrize("choice,preset", [("1", "codex"), ("2", "cc-codex"), ("3", "cc-codex-agy")])
def test_actual_wizard_each_combination_asks_three_models_previews_mapping_and_cancel_is_read_only(tmp_path, fake_herdr, choice, preset):
    binaries = Path(fake_herdr["env"]["PATH"].split(os.pathsep)[0])
    (binaries / "herdr").symlink_to(fake_herdr["binary"])
    if choice == "1":
        (binaries / "claude").unlink()
    if choice in {"1", "2"}:
        (binaries / "agy").unlink()
    environment = {**fake_herdr["env"], "PATH": str(binaries)}
    project = tmp_path / "new unified project"
    term = Terminal([], tmp_path, environment)
    try:
        term.expect("项目目录")
        term.line(str(project))
        term.expect("客户端组合")
        term.line(choice)
        for name in ("main", "engineer", "writer"):
            term.expect("模型选择")
            term.line("2")
            term.expect("模型 ID")
            term.line(f"selected-{name}-model")
        term.expect("[3/4] 分工与工作台")
        term.expect("工作台名称")
        preview = term.text.rsplit("[3/4] 分工与工作台", 1)[1]
        compact = {"codex": "Codex", "claude": "CC", "agy": "AGY"}
        for role, label in (("main", "主会话"), ("engineer", "工程"), ("writer", "写作")):
            assert f"{label} / {compact[TEAMS[preset][role]]}" in preview
        term.line()
        term.expect("本次任务")
        term.line()
        term.expect("[4/4] 启动摘要")
        term.expect("请选择")
        for name in ("main", "engineer", "writer"):
            assert f"selected-{name}-model" in term.text
        if choice == "1":
            assert "CC/AGY 收到后续结果" not in term.text
        term.line("3")
        assert term.finish() == 0, term.text
        assert not project.exists()
        assert json.loads(fake_herdr["state"].read_text())["commands"] == []
    finally:
        (tmp_path / "PTY-three-role-defaults.txt").write_text(term.text, encoding="utf-8")
        term.close()


@pytest.mark.parametrize("preset", TEAMS)
def test_partial_parameter_start_restores_full_intent_after_owner_started_but_reply_lost(project, fake_herdr, preset):
    binary = fake_herdr["binary"]
    code = binary.read_text()
    anchor = '    output({"agent": state["agents"][name]})'
    assert anchor in code
    binary.write_text(code.replace(anchor, '''    if state.pop("fail_first_start_response", False):
        save()
        raise SystemExit("simulated startup timeout after owner actually launched")
    output({"agent": state["agents"][name]})''', 1))
    state = json.loads(fake_herdr["state"].read_text())
    state["fail_first_start_response"] = True
    fake_herdr["state"].write_text(json.dumps(state))
    (project / "CURRENT.md").write_text("Retain this approved recovery entry.\n")
    common = ["--session", "isolated-test", "--no-attach", "--no-receiver", "--no-install",
              "--herdr-bin", str(binary)]
    selected = ["--preset", preset, "--task", "Keep the complete originally selected team.",
                "--skill", "research-lit", "--recovery", "CURRENT.md",
                "--write-scope", "engineer=owned/checks", "--write-scope", "writer=owned/drafts"]
    for name in TEAMS[preset]:
        selected += ["--model", f"{name}=original-{name}-model"]
    first = invoke(project, *common, *selected, environment=fake_herdr["env"])
    assert first.returncode != 0 and "startup timeout" in first.stderr
    launch = project / ".aris/workbench/launch.json"
    partial = json.loads(launch.read_text())
    assert set(partial["roles"]) == {"main"}
    assert {item["role"]: item["harness"] for item in partial["pending_start"]["roles"]} == TEAMS[preset]
    from superaris.cli import parser
    saved_args = parser().parse_args(partial["pending_start"]["arguments"])
    original_args = parser().parse_args(["start", str(project), *common, *selected])
    assert vars(saved_args) == vars(original_args)
    assert partial["pending_start"]["arguments"][:2] == ["start", str(project)]
    main_packet = partial["roles"]["main"]["context"]["packet"]
    original_phase = partial["roles"]["main"]["delivery"]["phase"]
    # Ordinary reentry supplies no fresh team/model/skill/scope choices.
    recovered = start(project, fake_herdr)
    assert {name: record["harness"] for name, record in recovered["roles"].items()} == TEAMS[preset]
    complete = json.loads(launch.read_text())
    assert "pending_start" not in complete
    assert complete["roles"]["main"]["pane_id"] == partial["roles"]["main"]["pane_id"]
    assert complete["roles"]["main"]["context"]["packet"] == main_packet
    if original_phase == "unknown":
        assert complete["roles"]["main"]["delivery"]["phase"] == "unknown"
    for name, record in complete["roles"].items():
        assert record["requested_model"] == f"original-{name}-model"
        assert record["inputs"]["skills"] == ["research-lit"]
        assert record["inputs"]["recovery"] == ["CURRENT.md"]
        if name != "main":
            assert "wait for the main owner's scoped assignment" in record["inputs"]["task"]
            assert record["inputs"]["write_scope"] == str(project / "owned" / ("checks" if name == "engineer" else "drafts"))
    state = json.loads(fake_herdr["state"].read_text())
    starts = [args for args in state["commands"] if args[:2] == ["agent", "start"]]
    assert len(starts) == 3 and len({args[args.index("--pane") + 1] for args in starts}) == 3
    if original_phase == "unknown":
        assert not any(args[:3] == ["agent", "prompt", complete["roles"]["main"]["pane_id"]] for args in state["commands"])
    count = len(state["commands"])
    start(project, fake_herdr)
    later = json.loads(fake_herdr["state"].read_text())["commands"][count:]
    assert not any(args[:2] in (["agent", "start"], ["agent", "prompt"]) for args in later)


def test_relative_parameter_pending_can_resume_through_wizard_from_another_directory(project, fake_herdr, tmp_path, monkeypatch):
    binary = fake_herdr["binary"]
    code = binary.read_text()
    binary.write_text(code.replace('    output({"agent": state["agents"][name]})', '''    if state.pop("fail_first_start_response", False):
        save()
        raise SystemExit("simulated startup timeout after owner actually launched")
    output({"agent": state["agents"][name]})''', 1))
    state = json.loads(fake_herdr["state"].read_text());state["fail_first_start_response"] = True
    fake_herdr["state"].write_text(json.dumps(state))
    options = ["--session", "isolated-test", "--no-attach", "--no-receiver", "--no-install",
               "--herdr-bin", str(binary), "--model", "writer=original-writer-model",
               "--write-scope", "writer=owned/text", "--task", "Keep the relative-start task."]
    failed = subprocess.run([*CLI, "start", ".", *options], cwd=project, env=fake_herdr["env"],
                            capture_output=True, text=True, timeout=20)
    assert failed.returncode != 0 and "startup timeout" in failed.stderr
    launch = project / ".aris/workbench/launch.json"
    partial = json.loads(launch.read_text())
    assert partial["pending_start"]["arguments"][:2] == ["start", str(project)]
    assert len(partial["pending_start"]["roles"]) == 3
    from superaris import wizard
    monkeypatch.chdir(tmp_path)
    answers = iter(["1", str(project), "1", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(wizard, "capabilities", lambda: {
        "herdr": "fake", "codex": "fake", "claude": "fake", "agy": "fake", "brew": None,
    })
    selected = wizard.run()
    assert selected.arguments == partial["pending_start"]["arguments"]
    finished = subprocess.run([*CLI, *selected.arguments], env=fake_herdr["env"],
                              capture_output=True, text=True, timeout=20)
    assert finished.returncode == 0, finished.stderr
    complete = json.loads(launch.read_text())
    assert set(complete["roles"]) == {"main", "engineer", "writer"} and "pending_start" not in complete
    assert complete["roles"]["main"]["pane_id"] == partial["roles"]["main"]["pane_id"]
    assert complete["roles"]["writer"]["requested_model"] == "original-writer-model"
    assert complete["roles"]["writer"]["inputs"]["write_scope"] == str(project / "owned/text")
    state = json.loads(fake_herdr["state"].read_text())
    assert sum(args[:2] == ["agent", "start"] for args in state["commands"]) == 3
