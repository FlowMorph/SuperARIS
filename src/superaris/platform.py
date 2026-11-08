"""Small OS boundaries: kernel locks, detached children and shell examples."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import time

WINDOWS = os.name == "nt"


class LockBusy(BlockingIOError):
    pass


class FileLock:
    """An OS-owned lock released on close/process exit; never a PID-file lock."""
    def __init__(self, path: Path, blocking: bool = True):
        self.path, self.blocking, self.stream = Path(path), blocking, None

    def acquire(self):
        self.stream = self.path.open("a+b")
        if WINDOWS:
            import msvcrt
            # Windows byte-range locks need one byte. All callers lock byte 0.
            self.stream.seek(0, os.SEEK_END)
            if not self.stream.tell():
                self.stream.write(b"\0")
                self.stream.flush()
            while True:
                try:
                    self.stream.seek(0)
                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (13, 11, 36):
                        self.stream.close(); self.stream = None
                        raise
                    if not self.blocking:
                        self.stream.close(); self.stream = None
                        raise LockBusy(str(self.path)) from exc
                    time.sleep(0.05)
        else:
            import fcntl
            try:
                fcntl.flock(self.stream, fcntl.LOCK_EX | (0 if self.blocking else fcntl.LOCK_NB))
            except BlockingIOError as exc:
                self.stream.close(); self.stream = None
                raise LockBusy(str(self.path)) from exc
        return self

    def release(self):
        if self.stream is not None:
            try:
                if WINDOWS:
                    import msvcrt
                    self.stream.seek(0)
                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.stream, fcntl.LOCK_UN)
            finally:
                self.stream.close(); self.stream = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.release()


def detached_process_options() -> dict:
    if WINDOWS:
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def powershell_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def command_line(argv: list[str]) -> str:
    """Human/agent executable command for the platform's documented shell."""
    if WINDOWS:
        return "& " + " ".join(powershell_literal(arg) for arg in argv)
    return shlex.join(argv)
