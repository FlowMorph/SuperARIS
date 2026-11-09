"""Real receiver child processes with v254-shaped, file-backed fake Orca CLI.

These exercise subprocess/lock/receipt lifetimes, not a native Orca daemon or LLM.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import pytest

from superaris import receiver
from tests.support import CLI
from tests.test_windows_runtime import executable
from tests.test_workbench_receiver import atomic_json, wait_until


FAKE_ORCA = r'''
import json, os, sys
from pathlib import Path

state = json.loads(Path(os.environ["SUPERARIS_ORCA_RECEIVER_STATE"]).read_text())
args = sys.argv[1:]
assert args[-1] == "--json", args
args = args[:-1]
descriptor = os.open(os.environ["SUPERARIS_ORCA_RECEIVER_COMMANDS"], os.O_APPEND | os.O_WRONLY | os.O_CREAT, 0o600)
os.write(descriptor, (json.dumps(args) + "\n").encode())
os.close(descriptor)
assert "ORCA_ENVIRONMENT" not in os.environ
assert "ORCA_PAIRING_CODE" not in os.environ

def output(result):
    print(json.dumps({"ok": True, "result": result, "_meta": {"runtimeId": state["runtime_id"]}}))

terminal = {"handle": "term-owner", "ptyId": "original-pty", "incarnationId": state["incarnation"],
            "orphaned": False, "worktreeId": "original-workspace", "worktreePath": state["project"],
            "tabId": "tab-owner", "leafId": "leaf-owner", "connected": True, "writable": True,
            "executionHostId": "local", "agentIdentity": "codex", "paneRuntimeId": -1,
            "rendererGraphEpoch": 0, "agentWait": None}
workspace = {"worktreeId": "original-workspace", "hostId": "local", "path": state["project"],
             "agents": [{"paneKey": "tab-owner:leaf-owner", "state": state["agent_state"], "agentType": "codex", "hasLivePty": True}],
             "liveTerminalCount": 1, "hasAttachedPty": True, "terminalVerdict": "live"}
if args == ["status"]:
    output({"target": {"kind": "local"}, "runtime": {"reachable": state["available"],
           "runtimeId": state["runtime_id"], "capabilities": ["terminal.prompt-delivery.v1"]}})
elif args == ["worktree", "ps", "--limit", "10000"]:
    output({"worktrees": [workspace], "totalCount": 1, "truncated": False,
            "hostScope": {"hostIds": ["local"], "omittedHostIds": []}})
elif args == ["terminal", "list", "--worktree", "id:original-workspace"]:
    output({"terminals": [terminal], "truncated": False})
elif args == ["terminal", "show", "--terminal", "term-owner"]:
    output({"terminal": terminal})
elif args == ["terminal", "read", "--terminal", "term-owner", "--screen"]:
    output({"terminal": {**terminal, "source": "screen", "tail": ["› Ask Codex to do anything"],
                         "draft": state.get("draft", "")}})
elif args[:2] == ["terminal", "send"]:
    assert args[2:4] == ["--terminal", "term-owner"]
    assert "--enter" in args and "--wait-submit" in args
    if state.get("send_error"):
        print(json.dumps({"ok": False, "error": {"code": "unknown", "message": "Inspect original receipt",
              "data": {"requestId": "original-native-request"}}}))
        raise SystemExit(1)
    output({"send": {"accepted": True, "prompt": {"requestId": "original-native-request",
                                                   "state": "submitted"}}})
elif args == ["worktree", "set", "--worktree", "id:original-workspace", "--unread"]:
    output({"worktree": workspace})
else:
    raise SystemExit("Unexpected fake Orca mutation: " + repr(args))
'''


class OrcaProject:
    def __init__(self, folder):
        self.project = folder / "project with spaces"
        self.project.mkdir()
        self.root = self.project / ".aris/workbench"
        self.root.mkdir(parents=True)
        (self.project / "CURRENT.md").write_text("Original acceptance remains authoritative.\n")
        self.state_path = folder / "transport.json"
        self.commands_path = folder / "commands.jsonl"
        self.binary = executable(folder / "official fake orca", FAKE_ORCA)
        atomic_json(self.state_path, {"project": str(self.project), "available": True,
                    "runtime_id": "runtime-original", "incarnation": "incarnation-original", "agent_state": "done"})
        self.env = {**os.environ, "SUPERARIS_ORCA_RECEIVER_STATE": str(self.state_path),
                    "SUPERARIS_ORCA_RECEIVER_COMMANDS": str(self.commands_path),
                    "ORCA_ENVIRONMENT": "must-not-use", "ORCA_PAIRING_CODE": "must-not-use"}
        atomic_json(self.root / "launch.json", {
            "project": str(self.project), "session": "original-session", "host": "orca",
            "execution_environment": "local", "orca_bin": str(self.binary.resolve()),
            "worktree_selector": "id:original-workspace", "roles": {"main": {
                "host": "orca", "pane_id": "term-owner", "harness": "codex", "pid": None,
                "runtime_id": "runtime-original", "process_incarnation": "incarnation-original",
                "execution_host": "local", "pane_key": "tab-owner:leaf-owner", "automation_owned": False,
                "created": False, "status": "done"}}})

    def run(self, command, *options, ok=True):
        result = subprocess.run([*CLI, command, str(self.project), *map(str, options)],
                                env=self.env, capture_output=True, text=True, timeout=20, check=False)
        if not ok:
            return result
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def start(self):
        result = self.run("receiver", "--action", "start")
        wait_until(lambda: receiver.status(self.project)["receiving"])
        return result

    def commands(self):
        return [json.loads(line) for line in self.commands_path.read_text().splitlines()] if self.commands_path.exists() else []

    def count(self, prefix):
        return sum(args[:len(prefix)] == prefix for args in self.commands())

    def update_transport(self, **updates):
        state = json.loads(self.state_path.read_text())
        atomic_json(self.state_path, {**state, **updates})

    def update_binding(self, change):
        path = self.root / "launch.json"
        bound = json.loads(path.read_text())
        change(bound)
        atomic_json(path, bound)

    def report(self, identifier="late"):
        (self.project / "result.txt").write_text("Actual late test artifact.\n")
        self.run("watch", "--id", identifier, "--record", "CURRENT.md", "--deliverable", "result.txt",
                 "--wait-for", "actual artifact", "--query", "original worker query", "--next", "Apply original acceptance")
        return self.run("report", "--id", identifier, "--outcome", "completed", "--message", "Ready for verification")

    def bridge(self):
        path = self.root / "bridge.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def wait_stopped(self):
        wait_until(lambda: not receiver.status(self.project)["managed_process_alive"])
        return receiver.status(self.project)


@pytest.fixture
def orca_project(tmp_path, request):
    fixture = OrcaProject(tmp_path)
    yield fixture
    receiver.stop(fixture.project)
    deadline = time.monotonic() + 10
    while receiver.status(fixture.project)["managed_process_alive"] and time.monotonic() < deadline:
        time.sleep(.05)
    remaining = receiver.status(fixture.project)
    if remaining["managed_process_alive"] and remaining.get("pid"):
        os.kill(remaining["pid"], signal.SIGTERM)
        wait_until(lambda: not receiver.status(fixture.project)["managed_process_alive"])
    # Retain bounded fake evidence when the requested audit output directory exists.
    evidence = Path(os.environ["SUPERARIS_ORCA_RECEIVER_LOGS"]) if os.environ.get("SUPERARIS_ORCA_RECEIVER_LOGS") else None
    if evidence:
        evidence.mkdir(parents=True, exist_ok=True)
        name = request.node.name.replace("[", "-").replace("]", "")
        snapshot = {"test": request.node.name, "scope": "real subprocess with fake Orca transport",
                    "receiver": receiver.status(fixture.project), "bridge": fixture.bridge(), "commands": fixture.commands()}
        (evidence / f"{name}.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        log = fixture.root / "receiver.log"
        if log.exists():
            (evidence / f"{name}.log").write_bytes(log.read_bytes())


def test_child_survives_cli_launcher_and_late_report_notifies_once(orca_project):
    fixture = orca_project
    original = fixture.start()  # subprocess.run has already waited for CLI launcher exit
    live = receiver.status(fixture.project)
    assert live["managed_process_alive"] and live["receiving"]
    assert live["pid"] == original["pid"] and live["owner"]["pid"] is None
    reported = fixture.report()
    wait_until(lambda: "late" in fixture.bridge().get("delivered", {}))
    notice = fixture.root / "NOTICES.md"
    assert notice.read_text().count("ARIS registered task late") == 1
    handle = fixture.root / "handles/late.json"
    wait_until(lambda: json.loads(handle.read_text())["reports_seen"] == [reported["report"]])
    baseline = fixture.count(["terminal", "list"])
    wait_until(lambda: fixture.count(["terminal", "list"]) >= baseline + 2)
    assert notice.read_text().count("ARIS registered task late") == 1
    assert fixture.count(["worktree", "set"]) == 1
    assert fixture.count(["terminal", "send"]) == 0
    assert reported["acceptance"] == "not_evaluated"
    assert (fixture.project / "CURRENT.md").read_text() == "Original acceptance remains authoritative.\n"


def test_stop_restart_reuses_one_child_and_foreground_listener_cannot_duplicate(orca_project):
    fixture = orca_project
    original = fixture.start()
    second = fixture.run("receiver", "--action", "start")
    assert second["action"] == "reused" and second["pid"] == original["pid"]
    competitor = fixture.run("listen", "--duration", "0", ok=False)
    assert competitor.returncode != 0 and "Another receiver" in competitor.stderr
    fixture.run("receiver", "--action", "stop")
    stopped = fixture.wait_stopped()
    assert stopped["enabled"] is False and stopped["outcome"]["reason"] == "explicit_stop"
    restarted = fixture.start()
    assert restarted["generation"] != original["generation"]
    assert restarted["action"] == "started"
    reused = fixture.run("receiver", "--action", "start")
    assert reused["pid"] == restarted["pid"] and reused["generation"] == restarted["generation"]


@pytest.mark.parametrize("change", ["runtime", "live-incarnation", "binding-incarnation", "server", "host", "environment"])
def test_original_native_lifetime_or_binding_change_stops_child(orca_project, change):
    fixture = orca_project
    original = fixture.start()
    if change == "runtime":
        fixture.update_transport(runtime_id="replacement-runtime")
    elif change == "live-incarnation":
        fixture.update_transport(incarnation="replacement-incarnation")
    elif change == "binding-incarnation":
        fixture.update_binding(lambda b: b["roles"]["main"].update(process_incarnation="replacement"))
    elif change == "server":
        fixture.update_transport(available=False)
    elif change == "host":
        fixture.update_binding(lambda b: b.update(host="herdr"))
    else:
        fixture.update_binding(lambda b: b.update(execution_environment="other"))
    original_binding = (fixture.root / "launch.json").read_bytes()
    stopped = fixture.wait_stopped()
    assert stopped["status"] == "stopped" and stopped["owner"] == original["owner"]
    assert stopped["generation"] == original["generation"]
    assert stopped["outcome"]["reason"] == (
        "original_owner_changed" if change in {"binding-incarnation", "host", "environment"} else "owner_or_server_unavailable")
    assert (fixture.root / "launch.json").read_bytes() == original_binding
    assert fixture.count(["terminal", "send"]) == 0
    assert fixture.count(["agent", "launch"]) == fixture.count(["repo", "add"]) == fixture.count(["open"]) == 0


def test_unknown_send_preserves_request_id_and_never_retries_after_receiver_restart(orca_project):
    fixture = orca_project
    fixture.update_binding(lambda b: b["roles"]["main"].update(automation_owned=True))
    fixture.update_transport(send_error=True)
    fixture.start()
    fixture.report("unknown")
    attempt = wait_until(lambda: (entry if entry.get("status") == "unknown" else None)
                         if (entry := fixture.bridge().get("attempts", {}).get("unknown", {})) else None)
    assert attempt["status"] == "unknown"
    assert attempt["native_response"]["error"]["data"]["requestId"] == "original-native-request"
    assert fixture.count(["terminal", "send"]) == 1
    fixture.run("receiver", "--action", "stop")
    fixture.wait_stopped()
    fixture.start()
    baseline = fixture.count(["status"])
    wait_until(lambda: fixture.count(["status"]) >= baseline + 3)
    assert fixture.count(["terminal", "send"]) == 1
    assert fixture.bridge()["attempts"]["unknown"] == attempt
    assert receiver.status(fixture.project)["managed_process_alive"]


def test_native_draft_revokes_automation_without_sending_or_later_retry(orca_project):
    fixture = orca_project
    fixture.update_binding(lambda b: b["roles"]["main"].update(automation_owned=True))
    fixture.update_transport(draft="Preserve the original human draft")
    fixture.start()
    fixture.report("draft")
    wait_until(lambda: "draft" in fixture.bridge().get("delivered", {}))
    bound = json.loads((fixture.root / "launch.json").read_text())
    assert bound["roles"]["main"]["automation_owned"] is False
    receipt = fixture.bridge()["delivered"]["draft"]["receipt"]
    assert receipt["delivery"] == "visible_notice" and receipt["revoke_automation"] is True
    assert fixture.bridge().get("deferred", {}) == {}
    fixture.update_transport(draft="")
    baseline = fixture.count(["terminal", "list"])
    wait_until(lambda: fixture.count(["terminal", "list"]) >= baseline + 2)
    assert fixture.count(["terminal", "send"]) == 0
    assert (fixture.root / "NOTICES.md").read_text().count("ARIS registered task draft") == 1
