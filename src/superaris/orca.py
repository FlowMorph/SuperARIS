"""Explicit local Orca CLI transport, preserving native receipts and failures.

Terminal surfaces only. No native task DAG, remote route inference or implicit
mutation retry. Workbench operations are connected by the product runtime.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from .client import HerdrError
from .hosts import discover_orca, orca_missing_action


class OrcaError(HerdrError):
    def __init__(self, message: str, response: dict | None = None):
        super().__init__(message)
        self.response = response or {}


class Orca:
    host = "orca"

    def __init__(self, project: Path, binary: str | None = None, bound: dict | None = None):
        self.project = Path(project).expanduser().resolve()
        self.bound = bound or {}
        if self.bound.get("execution_environment", "local") != "local":
            raise OrcaError("This Orca version supports the original local runtime only; no remote target was inferred")
        self.session = self.bound.get("session", "default")
        self.found = discover_orca(binary or self.bound.get("orca_bin"))
        if not self.found["cli"]:
            raise OrcaError(orca_missing_action(self.found))
        self.binary = self.found["cli"]
        self.environment = "local"  # Remote/chat support is not claimed by this v1.

    def call(self, *arguments: str, timeout: float = 30) -> dict:
        argv = [self.binary, *map(str, arguments), "--json"]
        environment = dict(os.environ)
        # This release's status command treats --environment local as a saved
        # server name. Pin the actual local route by clearing remote overrides.
        for key in ("ORCA_ENVIRONMENT", "ORCA_PAIRING_CODE"):
            environment.pop(key, None)
        try:
            result = subprocess.run(argv, cwd=self.project, env=environment, capture_output=True, text=True,
                                    encoding="utf-8", timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OrcaError(f"Orca result unknown; inspect the original workspace/receipt before retrying: {exc}") from exc
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise OrcaError("The selected command did not return Orca JSON. Use the official Orca CLI from its app; no fallback host was started.") from exc
        if result.returncode or response.get("ok") is False or response.get("error"):
            error = response.get("error", {})
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise OrcaError(message or result.stderr.strip() or f"Orca exit {result.returncode}", response)
        return response

    def status(self) -> dict:
        response = self.call("status")
        status = response.get("result", {})
        if status.get("target", {}).get("kind") not in (None, "local"):
            raise OrcaError("This first Orca path requires the explicit local runtime")
        return status

    def ensure_ready(self) -> dict:
        status = self.status()
        runtime = status.get("runtime", {})
        if not runtime.get("reachable") or not runtime.get("runtimeId"):
            raise OrcaError("Orca is installed but its local runtime is not reachable. Open Orca, then resume this project; no other host or team was created.")
        return status

    def ensure_startable(self, *, new: bool = False) -> dict:
        try:
            status = self.status()
        except OrcaError as exc:
            if not new or exc.response.get("error", {}).get("code") != "runtime_unavailable":
                raise
            # A stopped, previously registered local runtime returns this
            # native error rather than an offline status result. Open only
            # for a confirmed new project, never to replace an old owner.
            self.call("open", timeout=90)
            return self.ensure_ready()
        if new and not status.get("runtime", {}).get("reachable"):
            # Only a confirmed new startup can open the installed application.
            # An existing binding never silently recreates its missing owner.
            self.call("open", timeout=90)
        return self.ensure_ready()

    def launch_agent(self, kind: str, model: str | None, prompt: str) -> dict:
        workspace = self.ensure_workspace()
        arguments = ["agent", "launch", "--agent", {"agy": "antigravity"}.get(kind, kind),
                     "--surface", "terminal", "--worktree", "id:" + workspace["worktreeId"],
                     "--prompt", prompt]
        if model:
            arguments += ["--model", model]
        return self.call(*arguments, timeout=125)

    def open_ui(self, handle: str | None = None) -> dict:
        self.ensure_ready()
        if handle:
            # Do not reveal a stale/different workspace merely because a
            # caller retained a terminal handle from an earlier invocation.
            terminal = self.terminal(handle)
            workspace = self._workspace()
            if not workspace or terminal.get("worktreeId") != workspace["worktreeId"]:
                raise OrcaError("The requested UI terminal no longer belongs to this project")
        opened = self.call("open", timeout=90)
        if handle:
            return self.call("terminal", "switch", "--terminal", handle)
        return opened

    def terminal(self, handle: str) -> dict:
        return self.call("terminal", "show", "--terminal", handle).get("result", {})["terminal"]

    def read_screen(self, handle: str) -> dict:
        screen = self.call("terminal", "read", "--terminal", handle, "--screen").get("result", {})["terminal"]
        if screen.get("source") != "screen":
            raise OrcaError("Orca did not return a current rendered screen; no automatic input is safe")
        return screen

    def workspace_rows(self) -> list[dict]:
        result = self.call("worktree", "ps", "--limit", "10000").get("result", {})
        if result.get("truncated"):
            raise OrcaError("Workspace listing was truncated; inspect exact workspace addresses before launch")
        # Exact return shape is verified against the live supported release.
        return result.get("worktrees", [])

    def _workspace(self, *, create: bool = False) -> dict | None:
        rows = self.workspace_rows()
        selector = self.bound.get("worktree_selector")
        candidates = [row for row in rows if row.get("hostId") == "local"
                      and Path(row.get("path", "")).resolve() == self.project
                      and (not selector or selector == "id:" + row.get("worktreeId", ""))]
        if not candidates and create:
            # Register this same folder, never clone/branch a worktree per role.
            self.call("repo", "add", "--path", str(self.project), "--kind", "folder")
            return self._workspace()
        if len(candidates) > 1:
            raise OrcaError("Several Orca workspaces match this project; select its exact original workspace before launch")
        return candidates[0] if candidates else None

    def ensure_workspace(self) -> dict:
        workspace = self._workspace(create=True)
        if not workspace or not workspace.get("worktreeId"):
            raise OrcaError("Orca did not return an exact registered workspace identity")
        return workspace

    def _terminals(self) -> list[dict]:
        workspace = self._workspace()
        if not workspace:
            return []
        result = self.call("terminal", "list", "--worktree", "id:" + workspace["worktreeId"]).get("result", {})
        if result.get("truncated"):
            raise OrcaError("Terminal listing is truncated; do not infer ownership from a partial list")
        return result.get("terminals", [])

    def snapshot(self) -> dict:
        self.ensure_ready()
        agents = []
        for terminal in self._terminals():
            kind = {"codex": "codex", "claude": "claude", "antigravity": "agy"}.get(terminal.get("agentIdentity"))
            if kind and terminal.get("connected"):
                agents.append({"pane_id": terminal["handle"], "agent": kind, "name": terminal.get("paneTitle")})
        return {"agents": agents}

    def verify_owner(self, role: dict, project: Path) -> dict:
        status = self.ensure_ready()
        runtime_id = status["runtime"]["runtimeId"]
        if role.get("runtime_id") and role["runtime_id"] != runtime_id:
            raise OrcaError("Original Orca runtime changed; inspect the original owner before rebinding")
        terminal = self.terminal(role["pane_id"])
        workspace = self._workspace()
        if not workspace or terminal.get("worktreeId") != workspace["worktreeId"]:
            raise OrcaError("Orca terminal no longer belongs to the exact original workspace")
        if Path(terminal.get("worktreePath", "")).resolve() != project.resolve():
            raise OrcaError("Orca terminal workspace path differs from the authorized project")
        kind = {"codex": "codex", "claude": "claude", "antigravity": "agy"}.get(terminal.get("agentIdentity"))
        if (kind != role["harness"] or not terminal.get("connected") or not terminal.get("writable")
                or terminal.get("orphaned") or terminal.get("exitCause")
                or terminal.get("verdict") in {"dead", "unreachable"}):
            raise OrcaError("Recorded Orca terminal occupant is absent or changed")
        execution_host = terminal.get("executionHostId")
        if execution_host != "local" or (role.get("execution_host") and role["execution_host"] != execution_host):
            raise OrcaError("Original Orca execution host is absent or changed")
        incarnation = terminal.get("incarnationId")
        if not incarnation:
            raise OrcaError("Orca did not expose a live PTY incarnation; ownership cannot be verified")
        if role.get("process_incarnation") and role["process_incarnation"] != incarnation:
            raise OrcaError("Original Orca PTY process incarnation changed; no input was sent")
        key = f"{terminal['tabId']}:{terminal['leafId']}"
        if role.get("pane_key") and role["pane_key"] != key:
            raise OrcaError("Original Orca pane identity changed")
        peers = [agent for agent in workspace.get("agents", []) if agent.get("paneKey") == key]
        if (len(peers) != 1 or peers[0].get("agentType") != terminal.get("agentIdentity")
                or peers[0].get("hasLivePty") is not True):
            raise OrcaError("Original Orca agent is no longer observed in its live PTY")
        state = peers[0].get("state", "unknown")
        state = {"permission": "blocked", "waiting": "idle"}.get(state, state)
        return {**role, "host": "orca", "runtime_id": runtime_id,
                "execution_host": terminal.get("executionHostId"),
                "process_incarnation": incarnation, "pty_id": terminal.get("ptyId"),
                "pane_key": key, "status": state, "workspace_path": terminal["worktreePath"],
                "native_session_id": role.get("native_session_id"), "pid": None}

    def wait_owner(self, role: dict, project: Path, timeout: float = 10, *, on_observed=None) -> dict:
        """Wait only for new-launch observation; never launch or send again."""
        import time
        terminal = self.terminal(role["pane_id"])
        incarnation = terminal.get("incarnationId")
        if not incarnation:
            raise OrcaError("New Orca terminal has no PTY incarnation yet; retain its original launch receipt")
        if role.get("process_incarnation") and role["process_incarnation"] != incarnation:
            raise OrcaError("Original Orca PTY process incarnation changed; no input was sent")
        # Retain the first real incarnation in the original launch record,
        # including when waiting fails. A later process must not inherit it.
        role.update(process_incarnation=incarnation,
                    runtime_id=role.get("runtime_id") or self.ensure_ready()["runtime"]["runtimeId"])
        if on_observed is not None:
            on_observed()
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self.verify_owner(role, project)
            except OrcaError as exc:
                if "no longer observed in its live PTY" not in str(exc) or time.monotonic() >= deadline:
                    raise
                # The CLI can return its launch receipt just before the agent
                # peer becomes observable. Keep the same runtime/PTY pinned.
                time.sleep(0.25)

    def send_prompt(self, handle: str, text: str, *, request_id: str | None = None) -> dict:
        status = self.ensure_ready()
        if "terminal.prompt-delivery.v1" not in status["runtime"].get("capabilities", []):
            raise OrcaError("This Orca runtime lacks durable prompt receipts; no untraceable input was sent")
        args = ["terminal", "send", "--terminal", handle, "--text", text, "--enter", "--wait-submit", "5"]
        if request_id:
            if request_id == "unsupported-old-host":
                raise OrcaError("An old-host placeholder cannot safely replay delivery")
            args += ["--retry-request", request_id]
        response = self.call(*args, timeout=20)
        receipt = response.get("result", {}).get("send", {})
        if (not receipt.get("accepted") or not receipt.get("prompt", {}).get("requestId")
                or receipt.get("prompt", {}).get("requestId") == "unsupported-old-host"):
            raise OrcaError("Orca did not confirm a durable accepted prompt; inspect its original receipt", response)
        return receipt

    def notice(self, title: str, text: str) -> dict:
        from .state import directory
        workspace = self._workspace()
        if not workspace:
            raise OrcaError("Original Orca workspace is unavailable; no notification target was inferred")
        path = directory(self.project) / "NOTICES.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Transport notices only. Original tasks, attempts and acceptance remain
        # in their existing records; never overwrite the user's Orca comment.
        with path.open("a", encoding="utf-8") as output:
            output.write(f"\n## {title}\n\n{text}\n")
        self.call("worktree", "set", "--worktree", "id:" + workspace["worktreeId"], "--unread")
        return {"notice_file": str(path), "workspace": workspace["worktreeId"]}

    def events(self, subscriptions: list[dict], timeout: float = 5):
        # This CLI release has no long-lived event-subscribe command. Reuse the
        # existing bounded reconciliation clock; never spin on an already-idle
        # terminal or start LLM polling. Runtime availability is rechecked next.
        import time
        time.sleep(max(0, timeout))
        if False:
            yield None
