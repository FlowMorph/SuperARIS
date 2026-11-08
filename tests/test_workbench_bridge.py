"""Foreground listener tests use a fake clock/server and real draft-safe delivery."""
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from superaris import bridge
from superaris import runtime
from superaris.client import HerdrError
from superaris.state import directory, read, write

_ACTUAL_PENDING_SIGNALS = bridge._pending_signals


def test_attached_receiver_lives_until_its_client_stop_event(running):
    project, client, _ = running
    stop = threading.Event()
    client.streams = [[stop.set]]
    result = bridge.listen(project, duration=None, interval=1, stop_event=stop)
    assert result["reason"] == "stopped"
    assert len(client.subscriptions) == 1


def test_receiver_without_client_or_duration_is_rejected(running):
    project, _, _ = running
    with pytest.raises(ValueError, match="stop event"):
        bridge.listen(project, duration=None)


@pytest.fixture
def running(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    roles = {name: {"pane_id": f"w1:p{index}", "harness": "codex", "automation_owned": False}
             for index, name in enumerate(("main", "engineer"), 1)}
    write(directory(project) / "launch.json", {"session": "test-only", "roles": roles})
    clock = SimpleNamespace(now=0.0)

    def advance(seconds):
        clock.now += seconds

    monkeypatch.setattr(bridge, "time", SimpleNamespace(monotonic=lambda: clock.now, sleep=advance))

    class FakeHerdr:
        def __init__(self):
            self.session = "test-only"
            self.roles = roles
            self.signals = []
            self.streams = []
            self.subscriptions = []
            self.actions = []
            self.snapshots = 0
            self.absent = False
            self.server_gone = False
            self.status = "idle"
            self.visible = "› unsent human draft"

        def snapshot(self):
            self.snapshots += 1
            if self.server_gone:
                raise HerdrError("server gone")
            return {"agents": [] if self.absent else list(self.roles.values())}

        def events(self, subscriptions, timeout=30):
            self.subscriptions.append((subscriptions, timeout))
            for item in self.streams.pop(0) if self.streams else []:
                if callable(item):
                    item()
                elif isinstance(item, Exception):
                    raise item
                else:
                    yield item
            advance(timeout)

        def json(self, *args):
            if args[:2] == ("agent", "get"):
                return {"agent": {"pane_id": args[2], "agent": "codex", "agent_status": self.status}}
            if args[:2] == ("pane", "process-info"):
                return {"process_info": {"foreground_processes": [
                    {"argv": ["codex"], "cwd": str(project), "pid": 7}]}}
            self.actions.append(args)
            return {}

        def run(self, *args):
            assert args[:2] == ("agent", "read")
            return self.visible

    client = FakeHerdr()
    monkeypatch.setattr(bridge, "Herdr", lambda session, binary: client)
    monkeypatch.setattr(runtime, "Herdr", lambda session, binary: client)
    monkeypatch.setattr(bridge, "_pending_signals", lambda project, c: [dict(s) for s in c.signals])
    return project, client, clock


def signal(**kwargs):
    return {"id": "task-1", "reason": "artifact changed", "prompt": "Read actual receipt", **kwargs}


def event():
    return {"event": "pane.agent_status_changed", "data": {"pane_id": "w1:p2", "agent_status": "done"}}


def test_native_subscriptions_route_notice_and_persist_success(running):
    project, client, clock = running
    client.signals = [signal(owner_role="engineer")]
    result = bridge.listen(project, duration=2, interval=1)
    assert result["reason"] == "duration_elapsed"
    assert result["deliveries"][0]["pane_id"] == "w1:p2"
    assert result["deliveries"][0]["delivery"] == "visible_notice"
    assert all(action[:2] == ("notification", "show") for action in client.actions)
    subscriptions, timeout = client.subscriptions[0]
    assert subscriptions == [{"type": "pane.agent_status_changed", "pane_id": "w1:p1"},
                             {"type": "pane.agent_status_changed", "pane_id": "w1:p2"}]
    assert timeout == 1
    assert read(directory(project) / "bridge.json")["delivered"]["task-1"]["signal"] == client.signals[0]
    again = bridge.listen(project, duration=1, interval=1)
    assert again["deliveries"] == []
    assert len(client.actions) == 1


def test_changed_signal_same_id_is_delivered_after_native_event(running):
    project, client, _ = running
    client.signals = [signal()]
    client.streams = [[lambda: client.signals[0].update(reason="new evidence", prompt="Read new receipt"), event()]]
    result = bridge.listen(project, duration=2, interval=1)
    assert result["events"] == 1
    assert len(result["deliveries"]) == 2
    assert read(directory(project) / "bridge.json")["delivered"]["task-1"]["signal"]["prompt"] == "Read new receipt"


def test_local_receipt_checked_at_timeout_without_native_event(running):
    project, client, _ = running
    client.streams = [[lambda: client.signals.append(signal())]]
    result = bridge.listen(project, duration=2, interval=1)
    assert result["events"] == 0
    assert len(result["deliveries"]) == 1
    assert result["reconciliations"] >= 2


@pytest.mark.parametrize("lost", [{"error": {"code": "events_lost"}}, HerdrError("events_lost")])
def test_lost_events_reconcile_snapshot_and_original_signals(running, lost):
    project, client, _ = running
    client.streams = [[lambda: client.signals.append(signal()), lost]]
    result = bridge.listen(project, duration=3, interval=1)
    assert result["reconnects"] == 1
    assert client.snapshots >= 3
    assert len(result["deliveries"]) == 1
    assert len(client.actions) == 1


def test_empty_automation_input_can_submit_through_existing_delivery(running):
    project, client, _ = running
    client.roles["main"]["automation_owned"] = True
    write(directory(project) / "launch.json", {"session": "test-only", "roles": client.roles})
    client.visible = "› Ask Codex to do anything"
    client.signals = [signal()]
    result = bridge.listen(project, duration=1, interval=1)
    assert result["deliveries"][0]["delivery"] == "submitted"
    assert client.actions == [("agent", "prompt", "w1:p1", "Read actual receipt")]


def test_automation_with_human_draft_receives_only_notice(running):
    project, client, _ = running
    client.roles["main"]["automation_owned"] = True
    write(directory(project) / "launch.json", {"session": "test-only", "roles": client.roles})
    client.signals = [signal()]
    result = bridge.listen(project, duration=1, interval=1)
    assert result["deliveries"][0]["delivery"] == "visible_notice"
    assert client.actions[0][:2] == ("notification", "show")
    assert not runtime.binding(project)["roles"]["main"]["automation_owned"]
    assert not read(directory(project) / "bridge.json")["deferred"]


@pytest.mark.parametrize("failure", ["absent", "server_gone"])
def test_stops_when_owner_or_server_disappears(running, failure):
    project, client, _ = running
    client.streams = [[lambda: setattr(client, failure, True), event()]]
    result = bridge.listen(project, duration=10, interval=1)
    assert result["reason"] == "owner_or_server_unavailable"
    assert not client.actions


def test_failed_delivery_is_not_deduplicated_or_automatically_retried(running, monkeypatch):
    project, client, _ = running
    client.signals = [signal()]
    attempted = []

    def failed(*args):
        attempted.append(args)
        raise HerdrError("send outcome unknown")

    monkeypatch.setattr(bridge, "deliver", failed)
    result = bridge.listen(project, duration=10, interval=1)
    assert result["reason"] == "unknown_requires_inspection"
    assert len(attempted) == 1
    state = read(directory(project) / "bridge.json")
    assert not state["delivered"]
    assert state["attempts"]["task-1"]["status"] == "unknown"
    again = bridge.listen(project, duration=10, interval=1)
    assert again["reason"] == "unknown_requires_inspection"
    assert again["pending_unknown"] == "task-1"
    assert len(attempted) == 1


def test_zero_duration_reconciles_and_delivers_exactly_once(running):
    project, client, _ = running
    client.signals = [signal()]
    result = bridge.listen(project, duration=0)
    assert result["reconciliations"] == 1
    assert len(result["deliveries"]) == 1
    assert not client.subscriptions


def test_success_updates_original_observed_handle_after_delivery(running, monkeypatch):
    project, client, _ = running
    client.signals = [signal(observed={"paths": {"artifact": "current"}})]
    write(directory(project) / "handles/task-1.json", {"active": True})
    recorded = []

    def mark(project_arg, signal_arg, receipt):
        assert client.actions
        assert not read(directory(project_arg) / "bridge.json")["attempts"]
        recorded.append((signal_arg, receipt))

    from superaris import tasks
    monkeypatch.setattr(tasks, "mark_notified", mark)
    bridge.listen(project, duration=0)
    assert recorded[0][0] == client.signals[0]
    assert recorded[0][1]["delivery"] == "visible_notice"


def test_crash_before_receipt_still_blocks_resend_on_restart(running):
    project, client, _ = running
    client.signals = [signal()]
    write(directory(project) / "bridge.json", {"delivered": {}, "attempts": {
        "task-1": {"status": "attempted", "signal": signal(), "pane_id": "w1:p1"}}})
    result = bridge.listen(project, duration=0)
    assert result["reason"] == "unknown_requires_inspection"
    assert not client.actions


def test_attempt_is_persisted_before_delivery(running, monkeypatch):
    project, client, _ = running
    client.signals = [signal()]

    def send(client_arg, project_arg, role, prompt):
        assert read(directory(project_arg) / "bridge.json")["attempts"]["task-1"]["status"] == "attempted"
        return {"delivery": "visible_notice", "pane_id": role["pane_id"]}

    monkeypatch.setattr(bridge, "deliver", send)
    result = bridge.listen(project, duration=0)
    assert len(result["deliveries"]) == 1
    assert not read(directory(project) / "bridge.json")["attempts"]


def test_attached_lifecycle_stop_event_checked_after_socket_boundary(running):
    project, client, clock = running
    stop = threading.Event()
    client.streams = [[stop.set]]
    result = bridge.listen(project, duration=300, interval=1, stop_event=stop)
    assert result["reason"] == "stopped"
    assert clock.now <= 1
    assert len(client.subscriptions) == 1


def test_already_stopped_lifecycle_does_not_open_subscription(running):
    project, client, _ = running
    stop = threading.Event()
    stop.set()
    result = bridge.listen(project, duration=300, stop_event=stop)
    assert result["reason"] == "stopped"
    assert not client.subscriptions and not client.snapshots


def test_explicit_missing_role_is_not_redirected_to_main(running):
    project, client, _ = running
    client.signals = [signal(owner_role="writer")]
    result = bridge.listen(project, duration=1, interval=1)
    assert result["deliveries"] == []
    assert result["pending"][0]["id"] == "task-1"
    assert not client.actions


def test_duration_bounds_socket_timeout(running):
    project, client, clock = running
    result = bridge.listen(project, duration=0.25, interval=5)
    assert result["reason"] == "duration_elapsed"
    assert clock.now == 0.25
    assert client.subscriptions[0][1] == 0.25


@pytest.mark.parametrize("duration,interval", [(-1, 1), (1, 0), (float("inf"), 1), (1, float("nan"))])
def test_bad_limits_rejected(running, duration, interval):
    project, _, _ = running
    with pytest.raises(ValueError):
        bridge.listen(project, duration=duration, interval=interval)


def test_busy_notice_defers_one_idle_delivery_across_restart(running):
    project, client, _ = running
    client.roles["main"]["automation_owned"] = True
    write(directory(project) / "launch.json", {"session": "test-only", "roles": client.roles})
    client.status = "working"
    client.signals = [signal()]
    bridge.listen(project, duration=2, interval=1)
    assert len(client.actions) == 1
    assert client.actions[0][:2] == ("notification", "show")
    assert "task-1" in read(directory(project) / "bridge.json")["deferred"]
    client.signals = []  # Original handle observations were already consumed.
    client.status = "idle"
    client.visible = "› Ask Codex to do anything"
    bridge.listen(project, duration=2, interval=1)
    assert len(client.actions) == 2
    assert client.actions[-1][:2] == ("agent", "prompt")
    assert not read(directory(project) / "bridge.json")["deferred"]
    bridge.listen(project, duration=0)
    assert len(client.actions) == 2


def test_human_takeover_cancels_busy_deferred_delivery(running):
    project, client, _ = running
    client.roles["main"]["automation_owned"] = True
    write(directory(project) / "launch.json", {"session": "test-only", "roles": client.roles})
    client.status = "working"
    client.signals = [signal()]
    bridge.listen(project, duration=0)
    runtime.control(project, "main", "human", "fake")
    client.signals = []
    client.status = "idle"
    client.visible = "› Ask Codex to do anything"
    bridge.listen(project, duration=0)
    assert len(client.actions) == 1
    assert not read(directory(project) / "bridge.json")["deferred"]


def test_context_notice_later_submits_and_preserves_pending_context(running, monkeypatch):
    project, client, _ = running
    packet = str(project / ".aris/workbench/context/main/0001/packet.md")
    role = client.roles["main"]
    role.update(automation_owned=True, context={"packet": packet, "prompt": "Read actual context"},
                pending_context=packet, delivery={"phase": "visible_notice", "receipt": {"delivery": "visible_notice"}})
    write(directory(project) / "launch.json", {"session": "test-only", "roles": client.roles})
    from superaris import tasks
    monkeypatch.setattr(tasks, "pending_signals", lambda project, c: [])
    monkeypatch.setattr(bridge, "_pending_signals", _ACTUAL_PENDING_SIGNALS)
    client.status = "working"
    bridge.listen(project, duration=2, interval=1)
    assert not client.actions  # Runtime already showed the original notice.
    client.status = "idle"
    client.visible = "› Ask Codex to do anything"
    result = bridge.listen(project, duration=2, interval=1)
    assert result["deliveries"][0]["id"] == "context-main-0001"
    assert client.actions == [("agent", "prompt", "w1:p1", "Read actual context")]
    persisted = runtime.binding(project)["roles"]["main"]
    assert persisted["delivery"]["phase"] == "submitted"
    assert persisted["pending_context"] == packet


def test_fresh_signal_overrides_busy_deferred_payload(running):
    project, client, _ = running
    client.roles["main"]["automation_owned"] = True
    write(directory(project) / "launch.json", {"session": "test-only", "roles": client.roles})
    client.status = "working"
    client.signals = [signal()]
    bridge.listen(project, duration=0)
    client.signals = [signal(prompt="new actual evidence")]
    bridge.listen(project, duration=0)
    assert len(client.actions) == 2
    client.signals = []
    client.status = "idle"
    client.visible = "› Ask Codex to do anything"
    bridge.listen(project, duration=0)
    assert client.actions[-1] == ("agent", "prompt", "w1:p1", "new actual evidence")


@pytest.mark.parametrize("envelope", [
    {"result": {"type": "event", "event": {"type": "pane_agent_status_changed", "pane_id": "w1:p2"}}},
    {"type": "event", "event": {"event": "pane.agent_status_changed", "data": {"pane_id": "w1:p2"}}},
])
def test_nested_native_event_envelopes_trigger_reconciliation(running, envelope):
    project, client, _ = running
    client.streams = [[lambda: client.signals.append(signal()), envelope]]
    result = bridge.listen(project, duration=2, interval=1)
    assert result["events"] == 1
    assert len(result["deliveries"]) == 1


def test_second_receiver_fails_before_client_construction(running, monkeypatch):
    import fcntl
    project, _, _ = running
    monkeypatch.setattr(bridge, "Herdr", lambda *args: pytest.fail("Second receiver constructed a client"))
    with (directory(project) / "listen.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="Another receiver"):
            bridge.listen(project, duration=0)


def test_acknowledged_handle_does_not_submit_deferred_notice(running, monkeypatch):
    from superaris import tasks
    project, client, _ = running
    monkeypatch.setattr(bridge, "_pending_signals", _ACTUAL_PENDING_SIGNALS)
    client.roles["main"]["automation_owned"] = True
    write(directory(project) / "launch.json", {"session": "test-only", "roles": client.roles})
    (project / "TASK.md").write_text("Original authorized task and acceptance.\n")
    tasks.register(project, SimpleNamespace(id="finished", owner_role="main", worker_role=None,
        record="TASK.md", deliverable=["RESULT.md"], watch_file=[], wait_for="result", query="original worker",
        next="Read result, verify original gate, acknowledge when done"))
    (project / "RESULT.md").write_text("Actual result for synthetic case.\n")
    tasks.report(project, "finished", "completed", "Result ready.")
    client.status = "working"
    first = bridge.listen(project, duration=0)
    assert first["deliveries"][0]["delivery"] == "visible_notice"
    state = read(directory(project) / "bridge.json")
    assert "finished" in state["deferred"]
    original_history = state["delivered"]
    state["attempts"]["unresolved-other"] = {"status": "unknown"}
    write(directory(project) / "bridge.json", state)
    tasks.acknowledge(project, "finished", "RESULT.md")
    client.status = "idle"
    client.visible = "› Ask Codex to do anything"
    result = bridge.listen(project, duration=0)
    assert result["deliveries"] == []
    assert not any(action[:2] == ("agent", "prompt") for action in client.actions)
    state = read(directory(project) / "bridge.json")
    assert not state["deferred"]
    assert state["delivered"] == original_history
    assert state["attempts"]["unresolved-other"] == {"status": "unknown"}


def test_superseded_context_does_not_submit_old_deferred_packet(running, monkeypatch):
    project, client, _ = running
    monkeypatch.setattr(bridge, "_pending_signals", _ACTUAL_PENDING_SIGNALS)
    old = project / "context/main/0001/packet.md"
    old.parent.mkdir(parents=True)
    old.write_text("Old task instructions.\n")
    main = client.roles["main"]
    main.update(automation_owned=True, context={"packet": str(old), "prompt": "Read old task packet"},
                delivery={"phase": "visible_notice", "receipt": {"delivery": "visible_notice"}})
    write(directory(project) / "launch.json", {"session": "test-only", "roles": client.roles})
    client.status = "working"
    bridge.listen(project, duration=0)
    history = read(directory(project) / "bridge.json")["delivered"]
    assert read(directory(project) / "bridge.json")["deferred"]
    current = project / "context/main/0002/packet.md"
    current.parent.mkdir()
    current.write_text("New authorized task already delivered.\n")
    main.update(context={"packet": str(current), "prompt": "Read new task packet"}, delivery={"phase": "submitted"})
    write(directory(project) / "launch.json", {"session": "test-only", "roles": client.roles})
    client.status = "idle"
    client.visible = "› Ask Codex to do anything"
    result = bridge.listen(project, duration=0)
    assert result["deliveries"] == []
    assert not any(action[:2] == ("agent", "prompt") for action in client.actions)
    state = read(directory(project) / "bridge.json")
    assert not state["deferred"]
    assert state["delivered"] == history
