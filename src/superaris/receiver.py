"""One project-scoped receiver, lasting only as long as its original owner.

This is a local runtime component, not an owner restarter or global service.
Control and transport metadata live alongside the existing launch/handle files.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time

from .client import Herdr, HerdrError, verify_owner
from .runtime import binding
from .state import directory, read, write
from . import __version__


def implementation() -> dict:
    return {"package": "superaris", "version": __version__, "path": str(Path(__file__).resolve().parent)}


def signature(bound: dict) -> dict:
    main = bound.get("roles", {}).get("main", {})
    return {"session": bound.get("session"), **{key: main.get(key) for key in
            ("pane_id", "harness", "pid", "native_session_id")}}


def same_owner(expected: dict, current: dict) -> bool:
    if any(expected.get(key) != current.get(key) for key in ("session", "pane_id", "harness", "pid")):
        return False
    before, after = expected.get("native_session_id"), current.get("native_session_id")
    return not (before and after and before != after)


def held(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("r") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream, fcntl.LOCK_UN)
        return False


@contextmanager
def _start_lock(project: Path):
    root = directory(project)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "receiver-start.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def status(project: Path) -> dict:
    root = directory(project)
    record = read(root / "receiver.json", {})
    control = read(root / "receiver-control.json", {"enabled": True})
    return {**record, "enabled": control.get("enabled", True),
            "managed_process_alive": held(root / "receiver-owner.lock"),
            "receiving": held(root / "listen.lock")}


def stop(project: Path) -> dict:
    with _start_lock(project):
        root = directory(project)
        control = read(root / "receiver-control.json", {})
        write(root / "receiver-control.json", {**control, "enabled": False})
    return {**status(project), "requested": "stop", "reason": "explicit_stop"}


def ensure_receiver(project: Path, binary: str = "herdr", enable: bool = False) -> dict:
    """Start/reuse a component independently of whether a TUI client attaches."""
    with _start_lock(project):
        root = directory(project)
        bound = binding(project)
        expected = signature(bound)
        if not expected["session"] or not expected["pane_id"] or not expected["pid"]:
            raise ValueError("Receiver needs the verified original main process identity")
        verify_owner(Herdr(expected["session"], binary), bound["roles"]["main"], project)
        control = read(root / "receiver-control.json", {"enabled": True})
        if enable:
            control["enabled"] = True
            write(root / "receiver-control.json", control)
        if not control.get("enabled", True):
            return {**status(project), "action": "disabled"}
        existing = read(root / "receiver.json", {})
        if held(root / "receiver-owner.lock"):
            if existing.get("implementation") != implementation():
                raise ValueError("An active receiver belongs to another installation. Stop it with its original entry before switching; no second receiver was started.")
            if not same_owner(existing.get("owner", {}), expected):
                raise ValueError("Previous receiver is ending after owner change; inspect it before starting another")
            return {**status(project), "action": "reused"}
        generation = str(time.time_ns())
        write(root / "receiver-control.json", {"enabled": True, "generation": generation})
        record = {"generation": generation, "owner": expected, "status": "starting", "implementation": implementation()}
        write(root / "receiver.json", record)
        argv = [sys.executable, "-m", "superaris", "receiver", str(project), "--action", "run",
                "--generation", generation, "--herdr-bin", binary]
        with (root / "receiver.log").open("ab") as output:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                       start_new_session=True)
        # The child may write its live record immediately; do not overwrite it.
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            live = status(project)
            if (live["managed_process_alive"] and live.get("pid") and live.get("status") == "running") or process.poll() is not None:
                break
            time.sleep(0.03)
        actual = status(project)
        if not actual["managed_process_alive"] or not actual.get("pid") or actual.get("status") != "running":
            raise RuntimeError(f"Project receiver did not remain running; inspect {root / 'receiver.log'}: {actual}")
        return {**actual, "action": "started"}


class ProjectLifetime:
    def __init__(self, project: Path, generation: str, expected_owner: dict):
        self.project, self.generation, self.expected_owner = project, generation, expected_owner
        self.reason = None

    def is_set(self) -> bool:
        control = read(directory(self.project) / "receiver-control.json", {})
        if not control.get("enabled"):
            self.reason = "explicit_stop"
        elif control.get("generation") != self.generation:
            self.reason = "receiver_replaced"
        elif not same_owner(self.expected_owner, signature(binding(self.project))):
            self.reason = "original_owner_changed"
        return self.reason is not None

    def wait(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while not self.is_set() and time.monotonic() < deadline:
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        return self.is_set()


def run(project: Path, generation: str, binary: str = "herdr") -> dict:
    """Internal child entry; never recreates a server or a native owner."""
    from .bridge import listen
    root = directory(project)
    record = read(root / "receiver.json", {})
    if record.get("generation") != generation:
        raise ValueError("Receiver generation no longer belongs to this launch")
    lifetime = ProjectLifetime(project, generation, record["owner"])
    with (root / "receiver-owner.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("A managed receiver already owns this project") from exc
        record.update(pid=os.getpid(), status="running")
        write(root / "receiver.json", record)
        outcome = {"reason": "stopped"}
        try:
            while not lifetime.is_set():
                current = binding(project)
                # Also verify the exact native process while a diagnostic
                # foreground listener temporarily owns listen.lock.
                verify_owner(Herdr(record["owner"]["session"], binary), current["roles"]["main"], project)
                try:
                    outcome = listen(project, binary, duration=None, interval=2, stop_event=lifetime)
                    if outcome.get("reason") == "unknown_requires_inspection":
                        # Remain available for explicit receipt resolution. This
                        # only checks local state/native identity, never an LLM.
                        lifetime.wait(2)
                        continue
                    break
                except ValueError as exc:
                    if "Another receiver" not in str(exc):
                        raise
                    lifetime.wait(1)
            outcome["reason"] = lifetime.reason or outcome["reason"]
        except (OSError, ValueError, HerdrError) as exc:
            outcome = {"reason": "owner_or_server_unavailable", "error": str(exc)}
        finally:
            record.update(status="stopped", outcome=outcome)
            write(root / "receiver.json", record)
            fcntl.flock(stream, fcntl.LOCK_UN)
    return record
