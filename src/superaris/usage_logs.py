"""只读原生会话日志，归一化可核实的用量和父子关系。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import math
from pathlib import Path


METRICS = ("requests", "raw_input_tokens", "input_tokens", "cache_read_tokens",
           "cache_write_tokens", "output_tokens", "equivalent_tokens")


def timestamp(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.timestamp() if parsed.tzinfo is not None else None
        except ValueError:
            return None
    return None


def number(value) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    return value if math.isfinite(value) and value >= 0 else None


class Diagnostics:
    """诊断只带白名单位置与原因，重复项聚合且数量有界。"""
    def __init__(self):
        self.rows: dict[tuple, dict] = {}
        self.suppressed = 0

    def add(self, code: str, client: str, file: str = "", line: int | None = None):
        key = (code, client, file)
        if key in self.rows:
            self.rows[key]["count"] += 1
        elif len(self.rows) < 100:
            self.rows[key] = {"code": code, "client": client, "file": file,
                              "first_line": line, "count": 1}
        else:
            self.suppressed += 1


@dataclass
class Session:
    client: str
    file: str
    sid: str | None = None
    parents: set[str] = field(default_factory=set)
    cwds: set[str] = field(default_factory=set)
    samples: dict[str, dict] = field(default_factory=dict)
    incomplete: bool = False
    ambiguous: bool = False
    forked_from: str | None = None


def _tokens(usage: dict, client: str) -> dict:
    names = {"raw_input_tokens": "input_tokens", "output_tokens": "output_tokens",
             "cache_read_tokens": "cache_read_input_tokens" if client == "claude" else "cached_input_tokens",
             "cache_write_tokens": "cache_creation_input_tokens"}
    values = {name: number(usage.get(key)) for name, key in names.items()}
    raw, cached = values["raw_input_tokens"], values["cache_read_tokens"]
    values["input_tokens"] = (raw if client == "claude" else
                               raw - cached if raw is not None and cached is not None and cached <= raw else None)
    required = ("input_tokens", "cache_read_tokens", "output_tokens")
    if client == "claude":
        required += ("cache_write_tokens",)
    values["equivalent_tokens"] = None
    if all(values[k] is not None for k in required):
        values["equivalent_tokens"] = (values["input_tokens"] + .1 * values["cache_read_tokens"]
                                        + 5 * values["output_tokens"])
        if client == "claude":
            values["equivalent_tokens"] += 1.25 * values["cache_write_tokens"]
    return values




def _claude(event: dict, session: Session, at: float | None, line: int, diag: Diagnostics):
    sid = event.get("sessionId")
    if isinstance(sid, str) and sid:
        if session.sid is None:
            session.sid = sid
        elif sid != session.sid:
            session.ambiguous = True
            diag.add("session_identity_conflict", "claude", session.file, line)
    for key in ("parentSessionId", "parent_session_id"):
        if isinstance(event.get(key), str) and event[key]:
            session.parents.add(event[key])
    message = event.get("message")
    if event.get("type") != "assistant" or not isinstance(message, dict):
        return
    usage = message.get("usage")
    if not isinstance(usage, dict):
        session.incomplete = True
        diag.add("usage_missing_or_unknown", "claude", session.file, line)
        return
    mid = message.get("id")
    if not isinstance(mid, str) or not mid:
        session.incomplete = True
        diag.add("message_identity_missing", "claude", session.file, line)
        return
    values = {"requests": 1, **_tokens(usage, "claude")}
    previous = session.samples.get(mid)
    if previous:
        # 流式消息重复快照逐字段保留已观测最大值，一次消息只记一次请求。
        for key in METRICS:
            a, b = previous["values"].get(key), values.get(key)
            if a is not None:
                values[key] = max(a, b) if b is not None else a
        values["equivalent_tokens"] = None
        if all(values[k] is not None for k in ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens")):
            values["equivalent_tokens"] = (values["input_tokens"] + .1 * values["cache_read_tokens"]
                                            + 1.25 * values["cache_write_tokens"] + 5 * values["output_tokens"])
    session.samples[mid] = {"at": at, "values": values, "line": line}


def _codex(event: dict, session: Session, at: float | None, line: int, diag: Diagnostics, state: dict):
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return
    if event.get("type") == "session_meta":
        sid = payload.get("id")
        if isinstance(sid, str) and sid:
            if session.sid is not None and session.sid != sid:
                session.ambiguous = True
                diag.add("session_identity_conflict", "codex", session.file, line)
            session.sid = sid
        if isinstance(payload.get("forked_from_id"), str):
            session.forked_from = payload["forked_from_id"]
        for key in ("forked_from_id", "parent_thread_id", "parent_session_id"):
            if isinstance(payload.get(key), str) and payload[key]:
                session.parents.add(payload[key])
        source = payload.get("source")
        subagent = source.get("subagent") if isinstance(source, dict) else None
        spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
        if isinstance(spawn, dict) and isinstance(spawn.get("parent_thread_id"), str):
            session.parents.add(spawn["parent_thread_id"])
        if isinstance(payload.get("cwd"), str):
            session.cwds.add(payload["cwd"])
        return
    if event.get("type") == "token_usage_record":
        thread, response, usage = (payload.get(k) for k in ("thread_id", "response_id", "usage"))
        if not (isinstance(thread, str) and thread and isinstance(response, str) and response
                and isinstance(usage, dict)):
            session.incomplete = True
            diag.add("usage_schema_unknown", "codex", session.file, line)
            return
        identity = "response:" + json.dumps([thread, response])
        session.samples.setdefault(identity, {
            "at": at, "values": {"requests": 1, **_tokens(usage, "codex")}, "line": line,
            "record_key": ("codex", "response", thread, response),
            "pair": _codex_pair(payload.get("thread_token_usage"), usage),
            "structured": True,
        })
        return
    if event.get("type") != "event_msg" or payload.get("type") != "token_count":
        return
    info = payload.get("info")
    info = info if isinstance(info, dict) else {}
    last, total = info.get("last_token_usage"), info.get("total_token_usage")
    if not isinstance(last, dict) and not isinstance(total, dict):
        # 没有用量的原生事件不构造一次请求。
        return
    keys = ("input_tokens", "cached_input_tokens", "output_tokens")
    counters = {k: number(total.get(k)) for k in keys} if isinstance(total, dict) else None
    cumulative = counters is not None and all(v is not None for v in counters.values())
    if cumulative:
        identity = json.dumps(counters, sort_keys=True)
        if identity in state["seen"]:
            return
        state["seen"].add(identity)
    else:
        identity = payload.get("id") or event.get("id") or event.get("uuid")
        if not isinstance(identity, str) or not identity:
            session.incomplete = True
            diag.add("codex_usage_identity_missing", "codex", session.file, line)
            return
        identity = "event:" + identity
    previous = state.get("previous")
    previous_at = state.get("previous_at")
    if cumulative and previous and any(counters[k] < previous[k] for k in keys):
        session.incomplete = True
        diag.add("codex_cumulative_regression_unknown", "codex", session.file, line)
        return
    if cumulative:
        state.update(previous=counters, previous_at=at)
    if isinstance(last, dict):
        values = {"requests": 1, **_tokens(last, "codex")}
    elif cumulative and previous and all(counters[k] >= previous[k] for k in keys):
        values = {"requests": None, **_tokens({k: counters[k] - previous[k] for k in keys}, "codex")}
    else:
        session.incomplete = True
        diag.add("codex_cumulative_baseline_missing_or_reset", "codex", session.file, line)
        return
    session.samples.setdefault(identity, {"at": at, "values": values, "line": line,
                                          "interval_start": previous_at if not isinstance(last, dict) else None,
                                          "pair": _codex_pair(total, last)})


def _codex_pair(total, last):
    """Match the two native representations, not unrelated equal-cost requests."""
    keys = ("input_tokens", "cached_input_tokens", "output_tokens")
    if not isinstance(total, dict) or not isinstance(last, dict):
        return None
    values = tuple(number(source.get(k)) for source in (total, last) for k in keys)
    return values if all(v is not None for v in values) else None


def _reconcile_codex(sessions: list[Session]):
    # Keep the legacy entries until copied-prefix provenance has been resolved:
    # a child may contain an old representation of a parent's structured response.
    by_sid: dict[str, list[Session]] = {}
    for session in sessions:
        by_sid.setdefault(session.sid, []).append(session)
        structured = {s["pair"]: s for s in session.samples.values()
                      if s.get("structured") and s.get("pair") is not None}
        for identity, sample in session.samples.items():
            sample.setdefault("record_key", ("codex", session.sid, identity))
            if not sample.get("structured") and sample.get("pair") in structured:
                sample["record_key"] = structured[sample["pair"]]["record_key"]
                sample["paired"] = True

    resolved, visiting = set(), set()

    def inherit(session):
        marker = id(session)
        if marker in resolved or marker in visiting:
            return
        visiting.add(marker)
        parents = by_sid.get(session.forked_from, [])
        for parent in parents:
            inherit(parent)
        # Only an exact observed prefix of an explicitly copied fork is inherited.
        # Equal counters elsewhere, or independent parent/child requests, stay distinct.
        for identity, sample in session.samples.items():
            if sample.get("structured"):
                continue  # its original thread/response identity is already explicit
            matches = [p.samples[identity] for p in parents if identity in p.samples
                       and p.samples[identity]["values"] == sample["values"]]
            if not matches:
                break
            keys = {m["record_key"] for m in matches}
            if len(keys) != 1:
                break
            sample["record_key"] = next(iter(keys))
            sample["at"] = matches[0]["at"]
            sample["interval_start"] = matches[0].get("interval_start")
        visiting.remove(marker)
        resolved.add(marker)

    for session in sessions:
        inherit(session)
    # The native writer restamps copied RolloutItems. Resolve time from the
    # original response's own thread before collect applies the time window.
    originals: dict[tuple, list[dict]] = {}
    for session in sessions:
        for sample in session.samples.values():
            key = sample["record_key"]
            origin_sid = key[2] if key[1] == "response" else key[1]
            if session.sid == origin_sid and sample["at"] is not None:
                originals.setdefault(key, []).append(sample)
    for session in sessions:
        for sample in session.samples.values():
            if not sample.get("structured"):
                continue
            source = originals.get(sample["record_key"], [])
            sample["at"] = min(s["at"] for s in source) if source else None
    for session in sessions:
        session.samples = {k: s for k, s in session.samples.items() if not s.get("paired")}


def scan(root: Path, client: str, diag: Diagnostics, until: float) -> tuple[list[Session], dict]:
    sessions = []
    source = {"root": str(root), "status": "observed", "files": 0,
              "scope": "local_files_only"}
    if not root.is_dir():
        source["status"] = "missing"
        diag.add("log_root_missing", client)
        return sessions, source
    try:
        paths = sorted(root.rglob("*.jsonl"))
    except OSError:
        source["status"] = "unreadable"
        diag.add("log_root_unreadable", client)
        return sessions, source
    for path in paths:
        if path.is_symlink():
            diag.add("symlink_log_skipped", client, str(path.relative_to(root)))
            source["status"] = "partial"
            continue
        relative = str(path.relative_to(root))
        session = Session(client, relative)
        if client == "claude":
            session.sid = path.stem
            if path.parent.name == "subagents" and path.stem.startswith("agent-"):
                # 原生子会话目录明确链接父编号；不根据项目目录或prompt猜归属。
                session.parents.add(path.parent.parent.name)
                session.sid = None
        elif path.stem.startswith("rollout-") and len(path.stem) >= 36:
            session.sid = path.stem[-36:]
        state = {"seen": set()}
        try:
            with path.open(encoding="utf-8") as stream:
                for line_no, raw in enumerate(stream, 1):
                    if not raw.strip():
                        continue
                    try:
                        event = json.loads(raw)
                    except ValueError:
                        session.incomplete = True
                        diag.add("malformed_jsonl", client, relative, line_no)
                        continue
                    if not isinstance(event, dict):
                        session.incomplete = True
                        diag.add("event_schema_unknown", client, relative, line_no)
                        continue
                    at = timestamp(event.get("timestamp"))
                    if isinstance(event.get("cwd"), str):
                        session.cwds.add(event["cwd"])
                    if at is not None and at >= until and event.get("type") != "session_meta":
                        continue
                    if ("usage" in event and event.get("type") != "assistant"
                            and not (client == "codex" and event.get("type") == "token_usage_record")):
                        session.incomplete = True
                        diag.add("usage_schema_unknown", client, relative, line_no)
                    if client == "claude":
                        _claude(event, session, at, line_no, diag)
                    else:
                        _codex(event, session, at, line_no, diag, state)
        except (OSError, UnicodeError):
            session.incomplete = True
            diag.add("log_unreadable", client, relative)
        if session.sid is None:
            session.sid = path.stem
        if session.incomplete:
            source["status"] = "partial"
        sessions.append(session)
    if client == "codex":
        _reconcile_codex(sessions)
    source["files"] = len(sessions)
    if not sessions and source["status"] == "observed":
        source["status"] = "empty"
    return sessions, source
