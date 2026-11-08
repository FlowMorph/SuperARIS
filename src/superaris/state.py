"""Launch ownership and delivery metadata; never research acceptance state."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path


def directory(project: Path) -> Path:
    path = project / ".aris" / "workbench"
    if not path.resolve().is_relative_to(project.resolve()):
        raise ValueError("workbench metadata escapes the selected project")
    return path


def read(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


@contextmanager
def launch_lock(project: Path):
    # Serialize local launcher changes; old process death releases the lock.
    import fcntl
    path = directory(project)
    path.mkdir(parents=True, exist_ok=True)
    with (path / "launch.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another launcher owns this project; wait for its result") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
