"""显式调用的本地用量报告；启动和监听链不导入或运行统计。"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

from .state import directory
from .usage_logs import Diagnostics, METRICS, Session, scan
from .ui import tr


def iso(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _read(path: Path, diag: Diagnostics) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        diag.add("metadata_missing", "workbench", path.name)
        return None
    except (OSError, UnicodeError, ValueError):
        diag.add("metadata_unreadable", "workbench", path.name)
        return None
    if not isinstance(value, dict):
        diag.add("metadata_schema_unknown", "workbench", path.name)
        return None
    return value


def _owners(roles: dict, sessions: list[Session], project: Path, diag: Diagnostics) -> tuple[dict, set]:
    candidates: dict[tuple, set[str]] = {}
    for name, role in roles.items():
        sid, client = role.get("native_session_id"), role.get("harness")
        if isinstance(sid, str) and sid and client in ("claude", "codex"):
            candidates.setdefault((client, sid), set()).add(name)
    direct = set(candidates)
    # 当前精确绑定优先，其余只沿显式父会话链接传播。
    for _ in range(len(sessions) + 1):
        changed = False
        for session in sessions:
            key = (session.client, session.sid)
            if key in direct:
                continue
            found = set(candidates.get(key, set()))
            for parent in session.parents:
                found.update(candidates.get((session.client, parent), set()))
            if found != candidates.get(key, set()):
                candidates[key] = found
                changed = True
        if not changed:
            break
    owners = {key: next(iter(names)) if len(names) == 1 else None for key, names in candidates.items()}
    relevant = set(candidates)
    for session in sessions:
        key = (session.client, session.sid)
        if session.ambiguous:
            owners[key] = None
            relevant.add(key)
        # cwd仅用于圈定未归属的项目记录，从不决定归给哪个角色。
        for cwd in session.cwds:
            try:
                if Path(cwd).expanduser().resolve() == project:
                    relevant.add(key)
            except (OSError, ValueError):
                diag.add("cwd_invalid", session.client, session.file)
        if len(candidates.get(key, set())) > 1:
            diag.add("ambiguous_session_owner", session.client, session.file)
    return owners, relevant


def _empty() -> dict:
    return {"_seen": 0, "_partial": False, "_unknown": set(),
            "observed": dict.fromkeys(METRICS, 0), "_known": dict.fromkeys(METRICS, 0), "sessions": set()}


def _add(target: dict, sample: dict):
    target["_seen"] += 1
    for name in METRICS:
        value = sample["values"].get(name)
        if value is None:
            target["_unknown"].add(name)
        else:
            target["observed"][name] += value
            target["_known"][name] += 1


def _finish(row: dict, client: str) -> dict:
    unknown = set(METRICS) if not row["_seen"] or row["_partial"] else row["_unknown"]
    return {**{name: None if name in unknown else row["observed"][name] for name in METRICS},
            "observed": {name: row["observed"][name] for name in METRICS
                         if row["_known"][name]},
            "status": "unknown" if not row["_seen"] else "partial" if row["_partial"] or row["_unknown"] else "observed",
            "metric_status": {name: "partial" if row["_seen"] else "unknown" for name in unknown},
            "session_count": len(row["sessions"]),
            "equivalent_scope": "input_cache_read_cache_write_output" if client == "claude" else "input_cache_read_output",
            "share": None}




def collect(project: Path, *, claude_root: Path | None = None, codex_root: Path | None = None,
            since: float | None = None, until: float | None = None, hours: float = 24,
            now: float | None = None) -> dict:
    now = time.time() if now is None else now
    until = now if until is None else until
    since = until - hours * 3600 if since is None else since
    if not all(math.isfinite(v) for v in (since, until, now, hours)) or hours <= 0 or since >= until or until > now:
        raise ValueError("时间范围须满足 since < until <= 当前时间 / require since < until <= now")
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise ValueError("项目目录不存在 / project directory does not exist")
    diag = Diagnostics()
    root = directory(project)
    launch = _read(root / "launch.json", diag) or {}
    raw_roles = launch.get("roles", {})
    if not isinstance(raw_roles, dict):
        diag.add("roles_schema_unknown", "workbench", "launch.json")
        raw_roles = {}
    roles = {name: record for name, record in raw_roles.items() if isinstance(record, dict)}
    roots = {"claude": claude_root if claude_root is not None else Path.home() / ".claude" / "projects",
             "codex": codex_root if codex_root is not None else Path.home() / ".codex" / "sessions"}
    sessions, sources = [], {}
    for client, log_root in roots.items():
        found, sources[client] = scan(log_root.expanduser(), client, diag, until)
        sessions.extend(found)
    owners, relevant = _owners(roles, sessions, project, diag)
    buckets = {(name, client): _empty() for name, role in roles.items()
               for client in (role.get("harness"),) if client in ("claude", "codex")}
    totals = {client: _empty() for client in roots}
    # 同一消息可能在恢复/分叉文件重复出现；归属冲突时放入未归属，不重复累加。
    records: dict[tuple, list[tuple]] = {}
    for session in sessions:
        key = (session.client, session.sid)
        if key not in relevant:
            continue
        owner = owners.get(key) or "unattributed"
        bucket = buckets.setdefault((owner, session.client), _empty())
        bucket["sessions"].add(session.sid)
        totals[session.client]["sessions"].add(session.sid)
        if session.incomplete:
            bucket["_partial"] = totals[session.client]["_partial"] = True
        for identity, sample in session.samples.items():
            at = sample["at"]
            if at is None:
                bucket["_partial"] = totals[session.client]["_partial"] = True
                diag.add("usage_timestamp_missing", session.client, session.file, sample["line"])
                continue
            if not since <= at < until:
                continue
            start = sample.get("interval_start")
            if start is not None and start < since:
                bucket["_partial"] = totals[session.client]["_partial"] = True
                diag.add("cumulative_delta_crosses_range_start", session.client, session.file, sample["line"])
                continue
            # Codex response provenance survives copied forks; legacy counters are
            # shared only for an exact inherited prefix, never globally by value.
            record_key = ((session.client, identity) if session.client == "claude"
                          else sample["record_key"])
            records.setdefault(record_key, []).append((owner, session, sample))
    for copies in records.values():
        client = copies[0][1].client
        names = {v[0] for v in copies}
        owner = next(iter(names)) if len(names) == 1 else "unattributed"
        bucket = buckets.setdefault((owner, client), _empty())
        if len(names) > 1:
            diag.add("duplicate_message_owner_conflict", client)
        sample = max((v[2] for v in copies), key=lambda v: v["at"])
        _add(bucket, sample)
        _add(totals[client], sample)
    # 绑定编号未在本地找到时，当前项目用量覆盖仍未知；不能由其他已知角色补齐。
    present = {(s.client, s.sid) for s in sessions}
    for name, role in roles.items():
        client = role.get("harness")
        if isinstance(client, str) and client not in totals:
            totals[client] = _empty()
            buckets[(name, client)] = _empty()
            sources[client] = {"status": "unsupported", "files": 0, "scope": "no_native_usage_parser"}
            diag.add("client_usage_unsupported", client)
    for name, role in roles.items():
        client, sid = role.get("harness"), role.get("native_session_id")
        sid = sid if isinstance(sid, str) else None
        if client in totals and (not sid or (client, sid) not in present):
            buckets.setdefault((name, client), _empty())["_partial"] = True
            totals[client]["_partial"] = True
            diag.add("bound_session_missing", client)
    # 任一相关会话只有元数据、没有范围内用量证据时，汇总仍有未知覆盖。
    for (_, client), bucket in buckets.items():
        if not bucket["_seen"] or bucket["_partial"]:
            totals[client]["_partial"] = True
    result_roles = {name: {"clients": {}} for name in roles}
    result_roles.setdefault("unattributed", {"clients": {}})
    for (name, client), bucket in sorted(buckets.items()):
        result_roles[name]["clients"][client] = _finish(bucket, client)
    result_totals = {client: _finish(bucket, client) for client, bucket in totals.items()}
    known_equivalent_total = sum(v["equivalent_tokens"] or 0 for v in result_totals.values())
    all_clients_known = all(v["equivalent_tokens"] is not None for v in result_totals.values()
                            if v["session_count"] or v["status"] != "unknown")
    for row in result_roles.values():
        for client, usage in row["clients"].items():
            denominator = result_totals[client]["equivalent_tokens"]
            usage["share_scope"] = "within_client_local_observations"
            usage["all_clients_share"] = (usage["equivalent_tokens"] / known_equivalent_total
                                          if all_clients_known and known_equivalent_total > 0
                                          and usage["equivalent_tokens"] is not None else None)
            if denominator is not None and denominator > 0 and usage["equivalent_tokens"] is not None:
                usage["share"] = usage["equivalent_tokens"] / denominator
    # 任一已绑定客户端未知时，全客户端相对贡献也保持未知。
    if any(result_totals.get(role.get("harness"), {}).get("equivalent_tokens") is None for role in roles.values()):
        for row in result_roles.values():
            for usage in row["clients"].values():
                usage["all_clients_share"] = None
    return {"schema_version": 1, "project": str(project), "generated_at": iso(now),
            "range": {"since": iso(since), "until": iso(until), "bounds": "[since, until)"},
            "coverage": "local_observations_not_accounting_ledger", "sources": sources,
            "clients": result_totals, "roles": result_roles,
            "diagnostics": list(diag.rows.values()),
            "diagnostics_suppressed": diag.suppressed,
            "ui_language": launch.get("ui_language") if launch.get("ui_language") in ("zh", "en") else "zh",
            "weights": {"input": 1, "cache_read": .1, "cache_write": 1.25, "output": 5},
            "binding_scope": "current_native_session_ids_and_explicit_descendants; unlinked_history_unknown"}


def render(report: dict, *, by_role: bool = False, lang: str = "zh") -> str:
    def t(key, **values):
        return tr(key, lang=lang, **values)

    def fmt(value):
        return t("未知") if value is None else f"{value:.2f}".rstrip("0").rstrip(".")

    lines = [t("本地用量 / Usage"), f"{report['range']['since']} → {report['range']['until']}",
             t("范围内本地观测；缺失字段为未知。")]
    rows = [(client, data) for client, data in report["clients"].items()]
    if by_role:
        rows = [(f"{role}/{client}", data) for role, row in report["roles"].items()
                for client, data in row["clients"].items()]
    for label, data in rows:
        lines.append(t("{label}：请求 {requests}，输入 {input}，缓存读 {read}，缓存写 {write}，输出 {output}，等效 {equivalent}，占比 {share}；状态 {status}",
                       label=label, requests=fmt(data["requests"]), input=fmt(data["input_tokens"]),
                       read=fmt(data["cache_read_tokens"]), write=fmt(data["cache_write_tokens"]),
                       output=fmt(data["output_tokens"]), equivalent=fmt(data["equivalent_tokens"]),
                       share=fmt(data["share"] * 100) + "%" if data["share"] is not None else t("未知"), status=data["status"]))
    for row in report["diagnostics"]:
        lines.append(f"! {row['client']}: {row['code']} ({row['count']}) {row['file']}")
    return "\n".join(lines)
