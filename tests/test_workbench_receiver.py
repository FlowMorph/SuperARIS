"""Real receiver subprocess lifetimes against a file-backed fake Herdr transport."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from superaris import receiver


ROOT = Path(__file__).resolve().parents[1]
from tests.support import CLI
ARIS = CLI

FAKE_TRANSPORT = r'''
import json, os, sys
from pathlib import Path

state = json.loads(Path(os.environ["ARIS_RECEIVER_TEST_STATE"]).read_text())
assert sys.argv[1:3] == ["--session", "isolated-test"], sys.argv
args = sys.argv[3:]
descriptor = os.open(os.environ["ARIS_RECEIVER_TEST_COMMANDS"], os.O_APPEND | os.O_WRONLY | os.O_CREAT, 0o600)
os.write(descriptor, (json.dumps(args) + "\n").encode())
os.close(descriptor)
owner = state["owner"]

def output(value):
    print(json.dumps({"result": value}))

if not args:
    pass  # Fake TUI client attaches and exits; the receiver must remain alive.
elif args == ["status"]:
    print("socket: " + state["socket"])
elif args == ["api", "snapshot"]:
    if not state["server_available"]:
        raise SystemExit("fake server snapshot unavailable")
    output({"snapshot": {"agents": [owner]}})
elif args[:2] == ["agent", "get"]:
    assert args[2] in (owner["name"], owner["pane_id"])
    output({"agent": owner})
elif args[:2] == ["pane", "process-info"]:
    assert args[2:] == ["--pane", owner["pane_id"]]
    output({"process_info": {"pane_id": owner["pane_id"], "foreground_processes": [{
        "argv": ["codex", "--cd", state["project"]], "cwd": state["project"], "pid": owner["pid"],
    }]}})
elif args[:2] == ["notification", "show"]:
    output({})
else:
    raise SystemExit("unexpected native mutation: " + repr(args))
'''


def atomic_json(path, value):
    temporary = path.with_suffix(".replacement")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    pytest.fail("test-owned receiver did not reach the expected state before timeout")


class ReceiverProject:
    def __init__(self, directory):
        self.project = directory / "project"
        self.project.mkdir()
        (self.project / "CURRENT.md").write_text("Original task remains subject to its existing acceptance gate.\n")
        self.state_path = directory / "fake-state.json"
        self.commands_path = directory / "fake-commands.jsonl"
        self.binary = directory / "fake herdr transport"
        self.binary.write_text(f"#!{sys.executable}\n" + FAKE_TRANSPORT)
        self.binary.chmod(0o755)
        socket = directory / "fake-existing-socket"
        socket.touch()  # No real socket/server: event errors exercise timed reconciliation.
        atomic_json(self.state_path, {
            "project": str(self.project), "socket": str(socket), "server_available": True,
            "owner": {"name": "existing-owner", "pane_id": "w1:p1", "agent": "codex",
                      "agent_status": "idle", "pid": 4321},
        })
        self.env = {**os.environ, "ARIS_RECEIVER_TEST_STATE": str(self.state_path),
                    "ARIS_RECEIVER_TEST_COMMANDS": str(self.commands_path)}

    def invoke(self, command, *options):
        result = subprocess.run(
            [*ARIS, command, str(self.project), *map(str, options)],
            env=self.env, capture_output=True, text=True, timeout=20, check=False,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def launch(self, attach=False):
        return self.invoke(
            "start", "--only-role", "main", "--session", "isolated-test", "--owner", "existing-owner",
            "--no-install", "--herdr-bin", self.binary, *([] if attach else ["--no-attach"]),
        )

    def commands(self):
        if not self.commands_path.exists():
            return []
        return [json.loads(line) for line in self.commands_path.read_text().splitlines()]

    def late_notices(self):
        return [args for args in self.commands() if args[:2] == ["notification", "show"]
                and any("registered task late" in arg for arg in args)]

    def change_transport(self, change):
        state = json.loads(self.state_path.read_text())
        change(state)
        atomic_json(self.state_path, state)

    def wait_stopped(self):
        wait_until(lambda: not receiver.status(self.project)["managed_process_alive"])
        return receiver.status(self.project)


@pytest.fixture
def managed_project(tmp_path):
    fixture = ReceiverProject(tmp_path)
    yield fixture
    # Cooperate first; a failed assertion must not leave our own receiver behind.
    receiver.stop(fixture.project)
    deadline = time.monotonic() + 10
    while receiver.status(fixture.project)["managed_process_alive"] and time.monotonic() < deadline:
        time.sleep(0.05)
    remaining = receiver.status(fixture.project)
    if remaining["managed_process_alive"] and remaining.get("pid"):
        os.kill(remaining["pid"], signal.SIGTERM)
        wait_until(lambda: not receiver.status(fixture.project)["managed_process_alive"])


@pytest.mark.parametrize("attach", [False, True])
def test_receiver_survives_launcher_exit_and_collects_late_report_once(managed_project, attach):
    fixture = managed_project
    launched = fixture.launch(attach=attach)
    # launch() waits for the actual CLI parent to exit, including fake TUI return.
    live = wait_until(lambda: receiver.status(fixture.project) if receiver.status(fixture.project)["receiving"] else None)
    assert live["managed_process_alive"] is True
    assert live["status"] == "running"
    assert live["pid"] == launched["receiver"]["pid"]
    assert live["owner"]["pid"] == 4321
    assert ([] in fixture.commands()) is attach
    # Baseline the artifact before registering so the later report is one new
    # event; a file change and a report can legitimately produce two notices.
    (fixture.project / "result.txt").write_text("Late author artifact after launcher exit.\n")
    fixture.invoke(
        "watch", "--id", "late", "--record", "CURRENT.md", "--deliverable", "result.txt",
        "--wait-for", "the actual author artifact", "--query", "original worker status job-7",
        "--next", "Read the actual result and apply the existing reviewer gate.",
    )
    reported = fixture.invoke("report", "--id", "late", "--outcome", "completed", "--message", "Ready for verification.")
    wait_until(lambda: fixture.late_notices())
    handle = fixture.project / ".aris/workbench/handles/late.json"
    wait_until(lambda: json.loads(handle.read_text())["reports_seen"] == [reported["report"]])
    baseline = sum(args == ["api", "snapshot"] for args in fixture.commands())
    wait_until(lambda: sum(args == ["api", "snapshot"] for args in fixture.commands()) >= baseline + 2)
    assert len(fixture.late_notices()) == 1
    assert reported["acceptance"] == "not_evaluated"
    assert receiver.status(fixture.project)["managed_process_alive"] is True
    assert (fixture.project / "CURRENT.md").read_text() == "Original task remains subject to its existing acceptance gate.\n"


def test_explicit_stop_stays_disabled_until_receiver_start_and_reuses_one_child(managed_project):
    fixture = managed_project
    original = fixture.launch()["receiver"]
    fixture.invoke("receiver", "--action", "stop")
    stopped = fixture.wait_stopped()
    assert stopped["enabled"] is False
    assert stopped["outcome"]["reason"] == "explicit_stop"
    disabled = fixture.launch()["receiver"]
    assert disabled["action"] == "disabled"
    assert disabled["managed_process_alive"] is False
    restarted = fixture.invoke("receiver", "--action", "start", "--herdr-bin", fixture.binary)
    assert restarted["action"] == "started"
    assert restarted["generation"] != original["generation"]
    assert restarted["managed_process_alive"] is True
    reused = fixture.invoke("receiver", "--action", "start", "--herdr-bin", fixture.binary)
    assert reused["action"] == "reused"
    assert reused["pid"] == restarted["pid"]
    assert reused["generation"] == restarted["generation"]


@pytest.mark.parametrize("change", ["binding-owner", "live-occupant", "server-loss"])
def test_receiver_ends_on_original_owner_or_fake_server_loss_without_rebinding(managed_project, change):
    fixture = managed_project
    original = fixture.launch()["receiver"]
    launch_path = fixture.project / ".aris/workbench/launch.json"
    if change == "binding-owner":
        bound = json.loads(launch_path.read_text())
        bound["roles"]["main"]["pid"] += 1
        bound["roles"]["main"]["native_session_id"] = "replacement-native"
        atomic_json(launch_path, bound)
    elif change == "live-occupant":
        fixture.change_transport(lambda state: state["owner"].update(pid=9876))
    else:
        fixture.change_transport(lambda state: state.update(server_available=False))
    expected_binding = launch_path.read_bytes()
    stopped = fixture.wait_stopped()
    assert stopped["status"] == "stopped"
    assert stopped["owner"] == original["owner"]
    assert stopped["generation"] == original["generation"]
    if change == "binding-owner":
        assert stopped["outcome"]["reason"] == "original_owner_changed"
    else:
        assert stopped["outcome"]["reason"] == "owner_or_server_unavailable"
    assert launch_path.read_bytes() == expected_binding
    assert not any(args[:2] in (["agent", "start"], ["agent", "prompt"], ["workspace", "create"])
                   for args in fixture.commands())


def test_optional_native_id_discovery_preserves_same_owner_lifetime(managed_project):
    fixture = managed_project
    original = fixture.launch()["receiver"]
    launch_path = fixture.project / ".aris/workbench/launch.json"
    bound = json.loads(launch_path.read_text())
    bound["roles"]["main"]["native_session_id"] = "newly-discovered-id"
    atomic_json(launch_path, bound)
    lifetime = receiver.ProjectLifetime(fixture.project, original["generation"], original["owner"])
    assert lifetime.is_set() is False
    assert lifetime.wait(0.05) is False
    assert receiver.same_owner(original["owner"], receiver.signature(bound)) is True
    changed = {**receiver.signature(bound), "native_session_id": "different-known-id"}
    assert receiver.same_owner(receiver.signature(bound), changed) is False


@pytest.mark.parametrize("origin", ["same", "missing", "other"])
def test_held_receiver_from_other_implementation_is_never_adopted(tmp_path, monkeypatch, origin):
    project = tmp_path / "project"
    root = project / ".aris/workbench"
    root.mkdir(parents=True)
    bound = {"session": "test-only", "roles": {"main": {
        "pane_id": "w1:p1", "harness": "codex", "pid": 123, "native_session_id": "same-native",
    }}}
    (root / "launch.json").write_text(json.dumps(bound))
    record = {"owner": receiver.signature(bound), "generation": "original", "pid": 456, "status": "running"}
    if origin == "same":
        record["implementation"] = receiver.implementation()
    elif origin == "other":
        record["implementation"] = {"package": "another-runtime", "version": "0", "path": "unrelated-runtime"}
    (root / "receiver.json").write_text(json.dumps(record))
    monkeypatch.setattr(receiver, "held", lambda path: path.name == "receiver-owner.lock")
    monkeypatch.setattr(receiver, "verify_owner", lambda client, role, selected: role)

    def forbidden(*args, **kwargs):
        pytest.fail("a held receiver must not cause a new process or replacement")

    monkeypatch.setattr(receiver.subprocess, "Popen", forbidden)
    if origin == "same":
        assert receiver.ensure_receiver(project)["action"] == "reused"
    else:
        with pytest.raises(ValueError):
            receiver.ensure_receiver(project)
    assert json.loads((root / "receiver.json").read_text()) == record
