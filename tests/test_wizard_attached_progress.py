"""Startup must progress while the user remains in the attached fake TUI."""

import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import time

import pytest

from tests.test_superaris_wizard import Terminal, select_project, summary
from superaris import receiver


FAKE_HERDR = r'''
import fcntl, json, os, sys, time
from pathlib import Path

state_path = Path(os.environ["ARIS_ATTACHED_STATE"])
lock_path = state_path.with_suffix(".lock")
args = sys.argv[3:]
assert sys.argv[1] == "--session"
descriptor = os.open(os.environ["ARIS_ATTACHED_COMMANDS"], os.O_APPEND | os.O_WRONLY | os.O_CREAT, 0o600)
os.write(descriptor, (json.dumps(args) + "\n").encode())
os.close(descriptor)

def transaction(change=None):
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(state_path.read_text())
        value = change(state) if change else state
        if change:
            temporary = state_path.with_name(state_path.name + "." + str(os.getpid()))
            temporary.write_text(json.dumps(state))
            temporary.replace(state_path)
        return value

def output(result):
    print(json.dumps({"result": result}))

def option(flag):
    return args[args.index(flag) + 1]

def owner(target):
    for record in transaction()["agents"].values():
        if target in (record["name"], record["pane_id"]):
            return record
    raise SystemExit("fake owner is missing")

if not args:
    Path(os.environ["ARIS_ATTACH_ENTERED"]).touch()
    while not Path(os.environ["ARIS_ATTACH_RELEASE"]).exists():
        time.sleep(0.025)
elif args == ["status"]:
    print("socket: " + transaction()["socket"])
elif args == ["api", "snapshot"]:
    output({"snapshot": {"agents": list(transaction()["agents"].values())}})
elif args[:2] == ["workspace", "create"]:
    def create(state):
        state["panes"] += 1
        return {"workspace": {"workspace_id": "w1"}, "tab": {"tab_id": "w1:t1"},
                "root_pane": {"pane_id": f'w1:p{state["panes"]}', "tab_id": "w1:t1"}}
    output(transaction(create))
elif args[:2] == ["pane", "split"]:
    def split(state):
        state["panes"] += 1
        return {"pane": {"pane_id": f'w1:p{state["panes"]}', "tab_id": "w1:t1"}}
    output(transaction(split))
elif args[:2] in (["tab", "rename"], ["pane", "rename"], ["agent", "focus"], ["notification", "show"]):
    output({})
elif args[:2] == ["agent", "start"]:
    kind, name, pane = option("--kind"), args[2], option("--pane")
    def start(state):
        blocked = kind == "claude" and not state["agents"]
        state["agents"][name] = {
            "name": name, "pane_id": pane, "agent": kind,
            "agent_status": "blocked" if blocked else "idle", "pid": 1000 + state["panes"],
            "argv": [kind, *args[args.index("--") + 1:]], "cwd": state["project"],
        }
        return {"agent": state["agents"][name], "failed": blocked or state.get("fail_kind") == kind}
    result = transaction(start)
    if result.pop("failed"):
        raise SystemExit("agent_not_ready: fake native trust" if kind == "claude" else "fake later native startup failed")
    output(result)
elif args[:2] == ["agent", "get"]:
    output({"agent": owner(args[2])})
elif args[:2] == ["pane", "process-info"]:
    record = owner(option("--pane"))
    output({"process_info": {"pane_id": record["pane_id"], "foreground_processes": [{
        "pid": record["pid"], "argv": record["argv"], "cwd": record["cwd"],
    }]}})
elif args[:2] == ["agent", "read"]:
    record = owner(args[2])
    print(transaction().get(record["agent"] + "_view", "› Ask Codex to do anything"))
elif args[:2] == ["agent", "prompt"]:
    def submit(state):
        state.setdefault("submissions", []).append(args[3])
    transaction(submit)
    output({})
else:
    raise SystemExit("unexpected native control: " + repr(args))
'''


def wait_until(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    pytest.fail("attached startup did not reach the expected state")


class AttachedProject:
    def __init__(self, root):
        self.root = root
        self.project = root / "attached project"
        self.project.mkdir()
        self.state = root / "transport.json"
        self.commands = root / "commands.jsonl"
        self.entered = root / "attach-entered"
        self.release = root / "attach-release"
        socket = root / "existing-fake-socket"
        socket.touch()
        self.state.write_text(json.dumps({"project": str(self.project), "socket": str(socket), "panes": 0, "agents": {}}))
        binaries = root / "bin"
        binaries.mkdir()
        (binaries / "python3").symlink_to(sys.executable)
        (binaries / "herdr").write_text(f"#!{sys.executable}\n" + FAKE_HERDR)
        (binaries / "herdr").chmod(0o755)
        for kind in ("codex", "claude", "agy"):
            path = binaries / kind
            path.write_text(f"#!{sys.executable}\nraise SystemExit('native model must not execute')\n")
            path.chmod(0o755)
        self.env = {**os.environ, "PATH": str(binaries), "ARIS_ATTACHED_STATE": str(self.state),
                    "ARIS_ATTACHED_COMMANDS": str(self.commands), "ARIS_ATTACH_ENTERED": str(self.entered),
                    "ARIS_ATTACH_RELEASE": str(self.release)}
        self.term = Terminal([], root, self.env)

    def choose_team(self):
        select_project(self.term, self.project)
        summary(self.term, models=["", "3", "3"])
        self.term.line("1")
        wait_until(self.entered.exists)

    def update(self, change):
        with self.state.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.state.read_text())
            change(state)
            temporary = self.state.with_suffix(".test-replacement")
            temporary.write_text(json.dumps(state))
            temporary.replace(self.state)

    def binding(self):
        return json.loads((self.project / ".aris/workbench/launch.json").read_text())

    def ledger(self):
        return [json.loads(line) for line in self.commands.read_text().splitlines()]


@pytest.fixture
def attached(tmp_path):
    fixture = AttachedProject(tmp_path)
    yield fixture
    fixture.release.touch()
    (tmp_path / "PTY-attached.txt").write_text(fixture.term.text, encoding="utf-8")
    fixture.term.close()
    receiver.stop(fixture.project)
    deadline = time.monotonic() + 10
    while receiver.status(fixture.project)["managed_process_alive"] and time.monotonic() < deadline:
        time.sleep(0.05)
    remaining = receiver.status(fixture.project)
    if remaining["managed_process_alive"]:
        os.kill(remaining["pid"], signal.SIGTERM)


def test_three_roles_and_receiver_finish_before_user_detaches(attached):
    fixture = attached
    fixture.choose_team()
    assert not fixture.release.exists()
    original = fixture.binding()["roles"]["main"]
    fixture.update(lambda state: next(iter(state["agents"].values())).update(agent_status="idle"))
    wait_until(lambda: set(fixture.binding()["roles"]) == {"main", "engineer", "writer"})
    wait_until(lambda: receiver.status(fixture.project)["managed_process_alive"])
    wait_until(lambda: not fixture.binding().get("pending_start"))
    complete = fixture.binding()
    assert not fixture.release.exists()
    assert complete["roles"]["main"]["pid"] == original["pid"] == 1001
    assert complete["roles"]["main"]["pane_id"] == original["pane_id"]
    assert complete["roles"]["main"]["delivery"]["phase"] == "unknown"
    for name, model in (("engineer", "gpt-6.1-sol"), ("writer", "gemini-4-argon-high")):
        assert complete["roles"][name]["requested_model"] == model
        assert complete["roles"][name]["inputs"]["write_scope"] == str(fixture.project / "outputs" / name)
    starts = [args for args in fixture.ledger() if args[:2] == ["agent", "start"]]
    assert [args[args.index("--kind") + 1] for args in starts] == ["claude", "codex", "agy"]
    assert len(json.loads(fixture.state.read_text())["submissions"]) == 1
    fixture.release.touch()
    assert fixture.term.finish() == 0, fixture.term.text
    assert fixture.ledger().count([]) == 1
    assert receiver.status(fixture.project)["managed_process_alive"] is True


@pytest.mark.parametrize("failure", ["owner-replaced", "later-start-error"])
def test_attached_startup_failure_keeps_pending_choices_without_duplicate_tasks(attached, failure):
    fixture = attached
    fixture.choose_team()
    original = fixture.binding()["roles"]["main"]

    def change(state):
        main = next(iter(state["agents"].values()))
        main["agent_status"] = "idle"
        if failure == "owner-replaced":
            main["pid"] += 100
        else:
            state["fail_kind"] = "codex"

    fixture.update(change)
    error_path = fixture.project / ".aris/workbench/startup-error.json"
    expected_error = "process changed" if failure == "owner-replaced" else "fake later native startup failed"
    wait_until(lambda: error_path.exists() and expected_error in json.loads(error_path.read_text())["error"].lower())
    assert not fixture.release.exists()
    fixture.release.touch()
    assert fixture.term.finish() != 0, fixture.term.text
    failed = fixture.binding()
    assert failed.get("pending_start")
    assert failed["roles"]["main"]["pid"] == original["pid"]
    assert "writer" not in failed["roles"]
    starts = [args for args in fixture.ledger() if args[:2] == ["agent", "start"]]
    expected = ["claude"] if failure == "owner-replaced" else ["claude", "codex"]
    assert [args[args.index("--kind") + 1] for args in starts] == expected
    assert json.loads(fixture.state.read_text()).get("submissions", []) == []
    assert fixture.ledger().count([]) == 1
    current_receiver = receiver.status(fixture.project)
    if current_receiver["managed_process_alive"]:
        assert current_receiver["owner"]["pid"] == original["pid"]


def test_startup_splash_and_idle_agy_trust_wait_without_keys_until_actual_ready_surface(attached):
    fixture = attached
    fixture.update(lambda state: state.update(
        codex_view="Codex is starting; composer is not displayed yet.",
        agy_view="Do you trust the contents of this project?\nYes, I trust this folder\nNo, exit",
    ))
    fixture.choose_team()
    fixture.update(lambda state: next(iter(state["agents"].values())).update(agent_status="idle"))

    def surfaces_waiting():
        roles = fixture.binding()["roles"]
        return (roles.get("engineer", {}).get("startup_wait") == "input_not_ready"
                and roles.get("writer", {}).get("startup_wait") == "directory_trust")

    wait_until(surfaces_waiting)
    roles = fixture.binding()["roles"]
    assert roles["engineer"]["bootstrap_pending"] is True
    assert roles["engineer"]["delivery"]["receipt"]["revoke_automation"] is False
    assert fixture.binding().get("pending_start")
    state = json.loads(fixture.state.read_text())
    assert state.get("submissions", []) == []
    assert next(record for record in state["agents"].values() if record["agent"] == "agy")["agent_status"] == "idle"
    fixture.update(lambda state: state.update(codex_view="› Ask Codex to do anything", agy_view="Ready for the user's task."))
    wait_until(lambda: not fixture.binding().get("pending_start"))
    assert len(json.loads(fixture.state.read_text())["submissions"]) == 1
    assert not fixture.release.exists()
    fixture.release.touch()
    assert fixture.term.finish() == 0, fixture.term.text
    assert fixture.ledger().count([]) == 1
    assert len(json.loads(fixture.state.read_text())["submissions"]) == 1
