"""Host runtime dispatch with local fakes; no native processes or model calls."""
from copy import deepcopy
from pathlib import Path

import pytest

from superaris import cli, runtime
from superaris.client import HerdrError


class FakeOrca:
    host = "orca"
    binary = "/official/orca"

    def __init__(self, project):
        self.project = project
        self.bound = {}
        self.agents = []
        self.launches = []
        self.startable = []
        self.opened = []
        self.fail_at = None
        self.reply = None

    def ensure_startable(self, *, new):
        self.startable.append(new)

    def ensure_workspace(self):
        return {"worktreeId": "original-workspace"}

    def snapshot(self):
        return {"agents": self.agents}

    def terminal(self, handle):
        return {"agentIdentity": "codex", "handle": handle}

    def verify_owner(self, record, project):
        assert project == self.project
        if record.get("process_incarnation") not in (None, "original-incarnation"):
            raise HerdrError("Original Orca PTY process incarnation changed")
        return {**record, "host": "orca", "runtime_id": "runtime-A", "pid": None,
                "process_incarnation": "original-incarnation", "status": "done"}

    def launch_agent(self, kind, model, prompt):
        saved = runtime.binding(self.project)
        selected = next(record for record in saved["roles"].values()
                        if record.get("launch_phase") == "attempting")
        assert selected["delivery"]["phase"] == "attempting"
        assert saved["pending_start"]["host"] == "orca"
        assert saved["pending_start"]["execution_environment"] == "local"
        self.launches.append((kind, model, prompt))
        if self.fail_at == len(self.launches):
            raise HerdrError("lost launch reply")
        response = {"ok": True, "result": {
            "outcome": {"kind": "terminal", "handle": f"term-{len(self.launches)}"},
            "operationId": f"operation-{len(self.launches)}",
            "prompt": {"delivery": "submit", "outcome": "handed-to-terminal"}},
            "_meta": {"runtimeId": "runtime-A"}}
        return deepcopy(self.reply if self.reply is not None else response)

    def open_ui(self, handle):
        self.opened.append(handle)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    client = FakeOrca(project)
    monkeypatch.setattr(runtime, "client_for_binding", lambda *a, **kw: client)
    monkeypatch.setattr(runtime, "resolve_aris_repo", lambda *a: tmp_path)
    calls = []

    def prepare(project, role, kind, task, skills, recovery, repo, scope, *, workbench_host=None):
        assert workbench_host == "orca"
        packet = project / f"{role}-{len(calls)}.md"
        packet.write_text(task)
        context = {"packet": str(packet), "prompt": f"Read {packet}"}
        calls.append(context)
        return context

    monkeypatch.setattr(runtime, "prepare_context", prepare)
    deliveries = []

    def deliver(client, project, record, prompt):
        deliveries.append(deepcopy(record))
        return {"delivery": "submitted" if record["automation_owned"] else "visible_notice"}

    monkeypatch.setattr(runtime, "deliver", deliver)
    args = cli.parser().parse_args(["start", str(project), "--host", "orca", "--automation-owned", "--task", "original task"])
    plan = cli.make_plan(args)
    return project, client, args, plan, calls, deliveries


@pytest.mark.parametrize("preset", ["codex", "cc-codex", "cc-codex-agy"])
def test_new_team_real_native_receipts_and_reentry(setup, preset):
    project, client, args, plan, calls, deliveries = setup
    args.preset = preset
    plan = cli.make_plan(args)
    result = runtime.start(plan, args)
    assert result["host"] == "orca"
    assert len(client.launches) == 3
    assert [launch[0] for launch in client.launches] == list(cli.PRESETS[preset].values())
    assert client.startable == [True]
    assert deliveries == []  # launch already handed the packet to each terminal
    saved = runtime.binding(project)
    assert "pending_start" not in saved
    assert saved["worktree_selector"] == "id:original-workspace"
    assert saved["roles"]["engineer"]["inputs"]["write_scope"] != saved["roles"]["writer"]["inputs"]["write_scope"]
    assert all("wait" in saved["roles"][name]["inputs"]["task"].lower() for name in ("engineer", "writer"))
    for role in saved["roles"].values():
        assert role["runtime_id"] == "runtime-A" and role["pid"] is None
        assert role["process_incarnation"] == "original-incarnation"
        assert role["delivery"]["phase"] == "submitted"
        assert role["operation_id"] == role["launch_receipt"]["result"]["operationId"]
        assert role["pending_context"] == role["context"]["packet"]
    runtime.start(plan, args)
    assert len(client.launches) == len(calls) == 3
    assert client.startable == [True, False]
    assert runtime.binding(project)["roles"] == saved["roles"]


@pytest.mark.parametrize("explicit", [False, True])
def test_adopted_owner_keeps_human_control(setup, explicit):
    project, client, args, plan, calls, deliveries = setup
    client.agents = [{"pane_id": "original-owner", "agent": "codex"}]
    if explicit:
        args.owner = "original-owner"
    result = runtime.start(plan, args)
    main = result["roles"]["main"]
    assert main["pane_id"] == "original-owner"
    assert main["automation_owned"] is False and main["created"] is False
    assert main["delivery"]["phase"] == "visible_notice"
    assert len(client.launches) == 2
    assert deliveries[0]["automation_owned"] is False


def test_lost_launch_retains_full_intent_and_never_duplicates(setup):
    project, client, args, plan, calls, deliveries = setup
    client.fail_at = 2
    with pytest.raises(HerdrError, match="lost launch"):
        runtime.start(plan, args)
    saved = runtime.binding(project)
    assert len(saved["pending_start"]["roles"]) == 3
    assert saved["roles"]["main"]["delivery"]["phase"] == "submitted"
    assert saved["roles"]["engineer"]["delivery"]["phase"] == "unknown"
    assert saved["roles"]["engineer"]["launch_phase"] == "unknown"
    with pytest.raises(HerdrError, match="Original Orca launch outcome is unknown"):
        runtime.start(plan, args)
    assert len(client.launches) == 2
    assert runtime.binding(project)["pending_start"] == saved["pending_start"]


def test_nonterminal_response_saved_as_unknown(setup):
    project, client, args, plan, calls, deliveries = setup
    client.reply = {"result": {"outcome": {"kind": "chat"}, "operationId": "actual-operation"}}
    with pytest.raises(HerdrError, match="terminal handle"):
        runtime.start(plan, args)
    role = runtime.binding(project)["roles"]["main"]
    assert role["launch_receipt"] == client.reply
    assert role["operation_id"] == "actual-operation"
    assert role["delivery"]["phase"] == "unknown"
    assert "pane_id" not in role


def test_control_and_attach_reuse_verified_handle(setup):
    project, client, args, plan, calls, deliveries = setup
    runtime.start(plan, args)
    runtime.control(project, "main", "human", "ignored-herdr")
    assert runtime.binding(project)["roles"]["main"]["automation_owned"] is False
    assert runtime.attach(project) == 0
    assert client.opened == ["term-1"]
    saved = runtime.binding(project)
    saved["roles"]["main"]["process_incarnation"] = "replacement"
    runtime.save_binding(project, saved)
    with pytest.raises(HerdrError, match="incarnation changed"):
        runtime.attach(project)
    assert client.opened == ["term-1"]


def test_missing_prompt_receipt_stays_unknown_on_reentry(setup):
    project, client, args, plan, calls, deliveries = setup
    client.reply = {"result": {"outcome": {"kind": "terminal", "handle": "term-actual"}}}
    runtime.start(plan, args)
    assert all(role["delivery"]["phase"] == "unknown" for role in runtime.binding(project)["roles"].values())
    result = runtime.start(plan, args)
    assert len(client.launches) == 3
    assert all(action["action"] == "pending_unknown" for action in result["actions"])
    assert deliveries == []


def test_original_herdr_factory_is_injected_and_no_orca_calls(tmp_path, monkeypatch):
    project = tmp_path / "herdr-project"
    project.mkdir()
    made = []

    class FakeHerdr:
        def __init__(self, session, binary):
            self.session = session
            made.append((session, binary))

        def ensure(self, path, *, install):
            assert install is False

        def snapshot(self):
            return {"agents": []}

    monkeypatch.setattr(runtime, "Herdr", FakeHerdr)
    monkeypatch.setattr(runtime, "resolve_aris_repo", lambda *a: tmp_path)
    args = cli.parser().parse_args(["start", str(project), "--no-install"])
    plan = cli.make_plan(args)
    for role in plan["roles"]:
        role["active"] = False
    result = runtime.start(plan, args)
    assert made == [(args.session, args.herdr_bin)]
    assert "host" not in result
    assert "host" not in runtime.binding(project)  # legacy binding shape preserved


def test_native_error_receipt_operation_is_retained(setup):
    from superaris.orca import OrcaError
    project, client, args, plan, calls, deliveries = setup
    response = {"ok": False, "result": {"operationId": "actual-error-operation"},
                "error": {"message": "native uncertain"}}

    def fail(*args):
        raise OrcaError("native uncertain", response)

    client.launch_agent = fail
    with pytest.raises(OrcaError, match="native uncertain"):
        runtime.start(plan, args)
    role = runtime.binding(project)["roles"]["main"]
    assert role["launch_receipt"] == response
    assert role["operation_id"] == "actual-error-operation"
    assert role["launch_phase"] == role["delivery"]["phase"] == "unknown"
