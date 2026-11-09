"""Explicit-session Herdr transport. Mutations are never retried here."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from .platform import WINDOWS, detached_process_options
from .transport import connect, endpoint_exists


class HerdrError(RuntimeError):
    pass


class Herdr:
    def __init__(self, session: str, binary: str = "herdr"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", session):
            raise ValueError("session must be an explicit simple Herdr session name")
        self.session, self.binary = session, binary
        self._socket: str | None = None

    def run(self, *args: str, timeout: float = 30) -> str:
        try:
            result = subprocess.run([self.binary, "--session", self.session, *args],
                                    capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HerdrError(f"Herdr request did not finish; inspect real state before retrying: {exc}") from exc
        if result.returncode:
            raise HerdrError(result.stderr.strip() or result.stdout.strip() or f"Herdr exit {result.returncode}")
        return result.stdout.strip()

    def json(self, *args: str, timeout: float = 30) -> dict:
        try:
            response = json.loads(self.run(*args, timeout=timeout))
        except json.JSONDecodeError as exc:
            raise HerdrError("Herdr returned non-JSON output") from exc
        if response.get("error"):
            raise HerdrError(json.dumps(response["error"]))
        return response.get("result", response)

    def snapshot(self) -> dict:
        return self.json("api", "snapshot")["snapshot"]

    def socket_path(self) -> str:
        if self._socket is None:
            status = self.run("status")
            match = re.search(r"^\s*(?:socket|pipe):\s*(.+)$", status, re.MULTILINE)
            if not match:
                raise HerdrError("Cannot resolve this explicit session's socket from herdr status")
            self._socket = match.group(1).strip()
        return self._socket

    def request(self, method: str, params: dict, timeout: float = 30) -> dict:
        """One raw API request for methods without a CLI wrapper. No implicit target."""
        request = {"id": "aris-workbench", "method": method, "params": params}
        try:
            with connect(self.socket_path(), timeout) as connection:
                connection.sendall((json.dumps(request) + "\n").encode())
                response = json.loads(connection.readline())
        except (OSError, ValueError) as exc:
            raise HerdrError(f"Herdr {method} delivery unknown; reconcile before retry: {exc}") from exc
        if response.get("error"):
            raise HerdrError(json.dumps(response["error"]))
        return response.get("result", response)

    def events(self, subscriptions: list[dict], timeout: float = 30):
        """Yield a bounded native event stream; events_lost is surfaced, never replayed."""
        with connect(self.socket_path(), timeout) as connection:
            connection.sendall((json.dumps({"id": "aris-events", "method": "events.subscribe",
                                           "params": {"subscriptions": subscriptions}}) + "\n").encode())
            while True:
                try:
                    line = connection.readline()
                except TimeoutError:
                    return
                if not line:
                    raise HerdrError("Herdr event connection closed; refresh snapshot before resubscribing")
                value = json.loads(line)
                if value.get("error"):
                    raise HerdrError(json.dumps(value["error"]))
                yield value

    def ensure(self, log: Path, install: bool = True) -> None:
        if not shutil.which(self.binary):
            if not install:
                raise HerdrError("Herdr is missing; --no-install preserved the current environment")
            install_herdr()
            if not shutil.which(self.binary):
                raise HerdrError("Herdr installation finished but the command is not on PATH")
        # A live or stale existing socket is not permission to restart its server.
        endpoint = self.socket_path()
        if not endpoint_exists(endpoint):
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("ab") as output:
                subprocess.Popen([self.binary, "--session", self.session, "server"],
                                 stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                 **detached_process_options())
            deadline = time.monotonic() + 10
            while not endpoint_exists(endpoint) and time.monotonic() < deadline:
                time.sleep(0.05)
        self.snapshot()


def install_herdr() -> None:
    """The user's explicit start plan authorizes installing the missing TUI only."""
    if WINDOWS:
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            raise HerdrError("PowerShell is missing. Install Herdr from https://herdr.dev/tui/docs/install/ and retry.")
        result = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                                 "irm https://herdr.dev/install.ps1 | iex"], check=False)
        if result.returncode:
            raise HerdrError("Herdr installer failed; complete its native authentication/conflict before retrying")
        # Installers cannot change their parent process PATH. Read only the
        # documented compatibility alias; do not alter persistent environment.
        alias = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Programs/Herdr/bin"
        if (alias / "herdr.exe").is_file():
            os.environ["PATH"] = str(alias) + os.pathsep + os.environ.get("PATH", "")
        return
    brew = shutil.which("brew")
    if brew:
        result = subprocess.run([brew, "install", "herdr"], check=False)
        if result.returncode:
            raise HerdrError("Homebrew could not install Herdr; complete its system authentication/conflict first")
        return
    raise HerdrError("No supported installer detected. Install Herdr TUI from https://herdr.dev/tui/docs/install/ and rerun; no other product was installed.")


def foreground(info: dict, kind: str | None = None) -> dict:
    matches = []
    for item in info.get("foreground_processes", []):
        argv = item.get("argv") or []
        if not argv or not item.get("cwd"):
            continue
        executable = Path(argv[0]).name.lower()
        executable = executable.removesuffix(".exe").removesuffix(".cmd")
        for harness in ([kind] if kind else ["codex", "claude", "agy"]):
            if executable == harness or (executable in {"node", "nodejs"} and len(argv) > 1
                    and (Path(argv[1]).name == f"{harness}.js" or
                         harness == "claude" and "claude-code" in Path(argv[1]).parts)):
                cwd = Path(item["cwd"])
                if harness == "codex":
                    for index, arg in enumerate(argv):
                        if arg == "--":
                            break
                        if arg in {"--cd", "-C"} and index + 1 < len(argv):
                            value = Path(argv[index + 1]); cwd = value if value.is_absolute() else cwd / value
                            break
                        if arg.startswith("--cd="):
                            value = Path(arg.split("=", 1)[1]); cwd = value if value.is_absolute() else cwd / value
                            break
                matches.append({"kind": harness, "cwd": str(cwd.resolve()), "pid": item.get("pid")})
    if len(matches) != 1:
        raise HerdrError("Expected one recognizable foreground agent; inspect actual pane before sending input")
    return matches[0]


def verify_owner(client: Herdr, role: dict, project: Path) -> dict:
    if getattr(client, "host", None) == "orca":
        return client.verify_owner(role, project)
    agent = client.json("agent", "get", role["pane_id"])["agent"]
    if agent.get("pane_id") != role["pane_id"] or agent.get("agent") != role["harness"]:
        raise HerdrError("Recorded pane occupant changed; explicit owner handoff is required")
    live = foreground(client.json("pane", "process-info", "--pane", role["pane_id"])["process_info"], role["harness"])
    if Path(live["cwd"]) != project:
        raise HerdrError(f"Owner effective cwd mismatch: {live['cwd']} != {project}")
    native = (agent.get("agent_session") or {}).get("value")
    if role.get("native_session_id") and native and role["native_session_id"] != native:
        raise HerdrError("Native session changed; inspect ownership before rebinding")
    if role.get("pid") and role["pid"] != live["pid"]:
        raise HerdrError("Foreground process changed; inspect ownership before rebinding")
    return {**role, **live, "native_session_id": native or role.get("native_session_id"),
            "status": agent.get("agent_status", "unknown"), "name": agent.get("name", role.get("name"))}


def read_screen(client, target: str) -> str:
    if getattr(client, "host", None) == "orca":
        screen = client.read_screen(target)
        if screen.get("draft"):
            # Keep a pending UI composer draft visible to the same guard.
            return "› " + screen["draft"]
        return "\n".join(screen.get("tail", []))
    return client.run("agent", "read", target, "--source", "visible", "--lines", "24")


def send_prompt(client, target: str, text: str) -> dict:
    if getattr(client, "host", None) == "orca":
        return client.send_prompt(target, text)
    return client.json("agent", "prompt", target, text)


def notify(client, title: str, text: str) -> dict:
    if getattr(client, "host", None) == "orca":
        return client.notice(title, text)
    return client.json("notification", "show", title, "--body", text, "--sound", "none")
