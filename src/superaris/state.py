"""Launch ownership and delivery metadata; never research acceptance state."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
import time

from .platform import WINDOWS, FileLock, LockBusy
from pathlib import Path


def directory(project: Path) -> Path:
    path = project / ".aris" / "workbench"
    if not path.resolve().is_relative_to(project.resolve()):
        raise ValueError("workbench metadata escapes the selected project")
    return path


def _metadata_io(operation):
    # Windows replacement/read can briefly conflict through CRT sharing modes.
    # Retry only local metadata I/O, never an agent submission or API mutation.
    deadline = time.monotonic() + 1
    while True:
        try:
            return operation()
        except PermissionError as exc:
            if not WINDOWS or getattr(exc, "winerror", None) not in (None, 5, 32, 33) or time.monotonic() >= deadline:
                raise
            time.sleep(.01)


def read(path: Path, default=None):
    try:
        return json.loads(_metadata_io(lambda: path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return default


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _metadata_io(lambda: temporary.replace(path))


@contextmanager
def launch_lock(project: Path):
    # Serialize local launcher changes; process death releases the kernel lock.
    path = directory(project)
    path.mkdir(parents=True, exist_ok=True)
    try:
        lock = FileLock(path / "launch.lock", blocking=False).acquire()
    except LockBusy as exc:
        raise ValueError("Another launcher owns this project; wait for its result") from exc
    try:
        yield
    finally:
        lock.release()
