"""Durable transport pointers to existing tasks, never scientific acceptance state."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from .client import HerdrError, verify_owner
from .state import directory, launch_lock, read, write


def local(project: Path, value: str) -> Path:
    path = (project / value).expanduser().resolve()
    if not path.is_relative_to(project):
        raise ValueError(f"Path outside selected project: {value}")
    return path


def handle_path(project: Path, identifier: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", identifier):
        raise ValueError("Handle ID must be a single simple name")
    return directory(project) / "handles" / f"{identifier}.json"


def fingerprint(path: Path):
    try:
        stat = path.stat()
        return [stat.st_mtime_ns, stat.st_size]
    except FileNotFoundError:
        return None


def register(project: Path, args) -> dict:
    from .runtime import binding
    with launch_lock(project):
        owners = binding(project).get("roles", {})
        if args.owner_role not in owners or args.worker_role and args.worker_role not in owners:
            raise ValueError("Register only existing verified role names; start/adopt the owner first")
        record = local(project, args.record) if args.record else None
        if record and not record.is_file():
            raise ValueError("Original task record must already exist")
        paths = list(dict.fromkeys(str(local(project, value)) for value in [*args.deliverable, *args.watch_file]))
        path = handle_path(project, args.id)
        if path.exists():
            raise ValueError("Handle already registered; retain its reports and use a new ID for new work")
        value = {"id": args.id, "owner_role": args.owner_role, "worker_role": args.worker_role,
                 "record": str(record) if record else None, "deliverables": args.deliverable,
                 "wait_for": args.wait_for, "query": args.query, "next_authorized": args.next,
                 "paths": {name: fingerprint(Path(name)) for name in paths},
                 "reports_seen": [], "active": True}
        write(path, value)
        return value


def report(project: Path, identifier: str, outcome: str, message: str) -> dict:
    """An owner's report is a signal. Original gates must still be checked."""
    with launch_lock(project):
        handle = read(handle_path(project, identifier))
        if not handle or not handle["active"]:
            raise ValueError("No active registered handle")
        folder = directory(project) / "reports" / identifier
        folder.mkdir(parents=True, exist_ok=True)
        number = max((int(p.stem) for p in folder.glob("*.json") if p.stem.isdecimal()), default=0) + 1
        value = {"id": identifier, "outcome": outcome, "message": message,
                 "time": datetime.now(timezone.utc).isoformat(), "acceptance": "not_evaluated"}
        destination = folder / f"{number:04d}.json"
        write(destination, value)
        return {**value, "report": str(destination)}


def pending_signals(project: Path, client=None) -> list[dict]:
    """Reconcile registered reports/files at entry, event, and read/write boundaries.

    MCP query strings are pointers for their original driver, never executable
    shell or a made-up common job protocol. No arbitrary Markdown is parsed.
    """
    signals = []
    for path in sorted((directory(project) / "handles").glob("*.json")):
        handle = read(path)
        if not handle["active"]:
            continue
        reports = sorted(str(p) for p in (directory(project) / "reports" / handle["id"]).glob("*.json"))
        new = [p for p in reports if p not in handle["reports_seen"]]
        current = {name: fingerprint(Path(name)) for name in handle["paths"]}
        changes = [name for name, stat in current.items() if stat != handle["paths"][name]]
        state = ""
        if client is not None and handle.get("worker_role"):
            from .runtime import binding
            worker = binding(project).get("roles", {}).get(handle["worker_role"])
            if worker:
                try:
                    state = verify_owner(client, worker, project)["status"]
                except HerdrError:
                    state = "owner changed/unavailable; inspect before dispatch"
        # An initial idle observation is a baseline, not completed work.
        previous = handle.get("last_worker_status")
        settled = bool(state) and state != "working" and (
            previous == "working" or state not in {"idle", "done"} and state != previous)
        if not new and not changes and not settled:
            if state and state != handle.get("last_worker_status"):
                with launch_lock(project):
                    latest = read(path)
                    latest["last_worker_status"] = state
                    write(path, latest)
            continue
        prompt = (f"ARIS registered task {handle['id']} has new evidence. Original task: {handle['record'] or 'the existing owner conversation'}; "
                  f"new reports: {new}; changed registered files: {changes}; worker hint: {state}. "
                  f"Waiting for: {handle['wait_for']}; query through original protocol: {handle['query']}. "
                  "Read actual files/replies and the current original task, honor paused/authorization/budget boundaries, "
                  "and apply its original acceptance gate. Reports and status are not acceptance. "
                  f"After verification, continue only the next already authorized step: {handle['next_authorized']}. "
                  "Update the original task/wiki as appropriate; acknowledge this transport handle only when no longer waiting.")
        signals.append({"id": handle["id"], "reason": "new report or registered file change",
                        "owner_role": handle["owner_role"], "prompt": prompt,
                        "observed": {"paths": current, "reports_seen": reports, "last_worker_status": state}})
    return signals


def mark_notified(project: Path, signal: dict, delivery: dict) -> None:
    with launch_lock(project):
        path = handle_path(project, signal["id"])
        handle = read(path)
        handle.update(signal["observed"])
        handle["last_delivery"] = delivery
        write(path, handle)


def acknowledge(project: Path, identifier: str, evidence: str) -> dict:
    path = local(project, evidence)
    if not path.is_file():
        raise ValueError("Acknowledgement requires an existing original receipt/evidence file")
    with launch_lock(project):
        target = handle_path(project, identifier)
        handle = read(target)
        if not handle:
            raise ValueError("Unknown handle")
        handle.update(active=False, receipt=str(path))
        write(target, handle)
        return handle


def remember(project: Path, args) -> dict:
    destination = local(project, args.file)
    if not destination.is_file():
        raise ValueError("Choose an existing authoritative memory file; do not create a second ledger implicitly")
    with launch_lock(project):
        if args.expected_mtime_ns is not None and destination.stat().st_mtime_ns != args.expected_mtime_ns:
            raise ValueError("Memory changed since read; reread human edits before appending")
        entry = (f"\n\n### {args.kind} — {datetime.now(timezone.utc).isoformat()}\n\n"
                 f"Scope: {args.scope}\nSource: {args.source}\n\n{args.text}\n")
        with destination.open("a", encoding="utf-8") as stream:
            stream.write(entry)
    return {"file": str(destination), "event": args.kind, "mtime_ns": destination.stat().st_mtime_ns}
