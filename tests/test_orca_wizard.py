"""Workbench choice is file-only, and existing bindings remain authoritative."""
from copy import deepcopy
from pathlib import Path

import pytest

from superaris import hosts, runtime, ui, wizard


@pytest.fixture(autouse=True)
def no_launch(monkeypatch):
    import socket
    import subprocess

    def forbidden(*args, **kwargs):
        pytest.fail("wizard selection must not launch a process or access the network")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    previous = ui.language
    yield
    ui.set_language(previous)


def available(herdr=None, orca=None, app=None, brew=None):
    return {"herdr": herdr, "orca": orca, "orca_app": app, "brew": brew,
            "codex": "fake-codex", "claude": "fake-claude", "agy": "fake-agy"}


def select(monkeypatch, tmp_path, answers, caps, bound=None):
    monkeypatch.chdir(tmp_path)
    record = bound or {}
    monkeypatch.setattr(runtime, "binding", lambda path: record)
    monkeypatch.setattr(wizard, "capabilities", lambda: caps)
    prompts = []
    iterator = iter(answers)

    def reply(prompt):
        prompts.append(prompt)
        return next(iterator)

    monkeypatch.setattr("builtins.input", reply)
    return wizard.run(), prompts


@pytest.mark.parametrize("caps,host,host_answer", [
    (available(herdr="herdr"), "herdr", None),
    (available(orca="orca"), "orca", None),
    (available(herdr="herdr", orca="orca"), "herdr", ""),
    (available(herdr="herdr", orca="orca"), "orca", "2"),
    (available(brew="brew"), "herdr", None),
    # An app is not itself a ready CLI; keep the established Herdr path.
    (available(herdr="herdr", app="Orca.app"), "herdr", None),
])
@pytest.mark.parametrize("language", ["1", "2"])
def test_new_project_selects_only_available_workbench_and_preserves_three_roles(
        monkeypatch, tmp_path, capsys, caps, host, host_answer, language):
    project = tmp_path / "new project with spaces"
    answers = [language, str(project)]
    if host_answer is not None:
        answers.append(host_answer)
    answers += ["1", "", "", "", "", "", "1"]
    selection, prompts = select(monkeypatch, tmp_path, answers, caps)
    assert selection.create_project
    assert not project.exists()
    assert ("--host" in selection.arguments) == (host == "orca")
    if host == "orca":
        assert selection.arguments[selection.arguments.index("--host") + 1] == "orca"
    assert {selection.arguments[i + 1] for i, value in enumerate(selection.arguments)
            if value == "--only-role"} == {"main", "engineer", "writer"}
    assert "wait for the user's concrete task" in selection.arguments[selection.arguments.index("--task") + 1]
    assert sum("Workbench host" in prompt or "工作台宿主" in prompt for prompt in prompts) == (host_answer is not None)
    output = capsys.readouterr().out
    assert ("Host: " if language == "2" else "宿主：") + ("Orca" if host == "orca" else "Herdr") in output
    assert selection.ui_language == ("zh" if language == "1" else "en")


@pytest.mark.parametrize("record_host", [None, "herdr", "orca"])
@pytest.mark.parametrize("pending", [False, True])
def test_bound_project_never_offers_host_choice_or_changes_pending_arguments(
        monkeypatch, tmp_path, record_host, pending):
    bound = {"session": "original-session", "roles": {"main": {"harness": "codex", "inputs": {"task": "original task"}}}}
    if record_host:
        bound["host"] = record_host
    arguments = ["start", str(tmp_path), "--session", "original-session", "--task", "original task", "--only-role", "main"]
    if record_host == "orca":
        launcher = tmp_path / "original launcher"
        launcher.write_text("official CLI fixture; must not be executed")
        arguments += ["--host", "orca", "--orca-bin", str(launcher)]
    if pending:
        bound["pending_start"] = {"arguments": arguments, "roles": [{"role": "main", "harness": "codex", "model": "original-model"}]}
    original = deepcopy(bound)
    selection, prompts = select(monkeypatch, tmp_path, ["2", str(tmp_path), "1", "1"],
                                available(herdr="herdr", orca="orca"), bound)
    assert bound == original
    assert not any("Workbench host" in prompt or "Model selection" in prompt for prompt in prompts)
    assert not selection.create_project
    if pending:
        assert selection.arguments == arguments
    else:
        assert selection.resume_existing
        assert selection.arguments == ["start", str(tmp_path), "--session", "original-session"] + (["--host", "orca"] if record_host == "orca" else [])


@pytest.mark.parametrize("action", ["3", "q"])
def test_cancel_after_orca_choice_creates_nothing(monkeypatch, tmp_path, action):
    project = tmp_path / "cancel project"
    answers = ["2", str(project), "2", "1", "", "", "", "", "", action]
    before = list(tmp_path.iterdir())
    if action == "q":
        with pytest.raises(wizard.Cancelled):
            select(monkeypatch, tmp_path, answers, available(herdr="herdr", orca="orca"))
    else:
        selection, _ = select(monkeypatch, tmp_path, answers, available(herdr="herdr", orca="orca"))
        assert selection is None
    assert list(tmp_path.iterdir()) == before


@pytest.mark.parametrize("interruption", [EOFError, KeyboardInterrupt])
def test_interruption_at_host_choice_has_no_side_effects(monkeypatch, tmp_path, interruption):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime, "binding", lambda path: {})
    monkeypatch.setattr(wizard, "capabilities", lambda: available(herdr="herdr", orca="orca"))
    replies = iter(["2", str(tmp_path / "uncreated")])

    def reply(prompt):
        try:
            return next(replies)
        except StopIteration:
            raise interruption

    monkeypatch.setattr("builtins.input", reply)
    with pytest.raises(interruption):
        wizard.run()
    assert list(tmp_path.iterdir()) == []


def test_orca_app_without_cli_gives_registration_action_not_reinstall(capsys):
    ui.set_language("en")
    assert not wizard.dependency_summary(available(app="/Applications/Orca.app"), "orca")
    output = capsys.readouterr().out
    assert "Settings → General → Orca CLI" in output
    assert "install and open" not in output
    assert "brew" not in output


def test_capabilities_reuses_file_only_orca_discovery(monkeypatch):
    monkeypatch.setattr(wizard.shutil, "which", lambda command: "fake-herdr" if command == "herdr" else None)
    monkeypatch.setattr(hosts, "discover_orca", lambda: {"cli": "/bundled/orca", "app": "/bundle/Orca.app", "source": "bundled"})
    result = wizard.capabilities()
    assert result["herdr"] == "fake-herdr"
    assert result["orca"] == "/bundled/orca"
    assert result["orca_app"] == "/bundle/Orca.app"


def test_legacy_capability_dictionary_and_default_summary_remain_compatible(capsys):
    legacy = {"herdr": "existing-herdr", "brew": None}
    assert wizard.select_workbench(legacy) == "herdr"
    assert wizard.dependency_summary(legacy)
    assert "Herdr" in capsys.readouterr().out


def test_back_to_same_new_project_preserves_orca_as_menu_default(monkeypatch, tmp_path):
    project = tmp_path / "new project"
    answers = ["2", str(project), "2", "1", "", "", "", "", "", "2",
               str(project), "", "1", "", "", "", "", "", "1"]
    selection, prompts = select(monkeypatch, tmp_path, answers, available(herdr="herdr", orca="orca"))
    host_prompts = [prompt for prompt in prompts if "Workbench host" in prompt]
    assert len(host_prompts) == 2
    assert "[1]" in host_prompts[0] and "[2]" in host_prompts[1]
    assert selection.arguments[selection.arguments.index("--host") + 1] == "orca"
    assert not project.exists()


@pytest.fixture
def orca_startup(monkeypatch, tmp_path):
    """In-memory host/runtime; no native process, UI command or receiver starts."""
    from contextlib import nullcontext
    from types import SimpleNamespace
    from superaris import client, receiver, state

    original = {"host": "orca", "harness": "claude", "pane_id": "original-terminal",
                "created": True, "runtime_id": "runtime-original", "process_incarnation": "original-pty",
                "status": "blocked", "pid": None, "delivery": {"phase": "unknown", "request_id": "original-request"}}
    bound = {"project": str(tmp_path), "host": "orca", "session": "original-session", "preset": "cc-codex-agy",
             "roles": {"main": deepcopy(original)},
             "pending_start": {"arguments": ["start", str(tmp_path), "--host", "orca", "--model", "main=original-model"],
                               "roles": [{"role": "main", "harness": "claude"}]}}
    calls = {"verify": [], "screen": [], "open": [], "receiver": [], "start": [], "errors": []}

    class FakeOrca:
        host = "orca"
        replaced = False

        def verify_owner(self, record, project):
            calls["verify"].append(record["pane_id"])
            if self.replaced:
                raise client.HerdrError("Original Orca PTY process incarnation changed")
            return {**record, "status": bound["roles"]["main"]["status"] if record["pane_id"] == "original-terminal" else "idle"}

        def read_screen(self, handle):
            calls["screen"].append(handle)
            return {"source": "screen", "tail": ["Native permission prompt"]}

        def open_ui(self, handle=None):
            calls["open"].append(handle)
            return {"opened": True}  # GUI open returns immediately, not detach.

    fake = FakeOrca()
    monkeypatch.setattr(hosts, "client_for_binding", lambda *args, **kwargs: fake)
    monkeypatch.setattr(runtime, "binding", lambda project: bound)

    def save(project, updated):
        if updated is not bound:
            bound.clear()
            bound.update(deepcopy(updated))

    monkeypatch.setattr(runtime, "save_binding", save)
    monkeypatch.setattr(state, "launch_lock", lambda project: nullcontext())
    monkeypatch.setattr(state, "write", lambda path, value: calls["errors"].append(deepcopy(value)))
    monkeypatch.setattr(receiver, "ensure_receiver", lambda project, binary: calls["receiver"].append("start") or {"active": True})
    monkeypatch.setattr(receiver, "stop", lambda project: calls["receiver"].append("stop") or {"active": False})
    monkeypatch.setattr(runtime, "attach", lambda *args: pytest.fail("Orca GUI open is not a blocking Herdr attach"))
    roles = [{"role": role, "harness": kind, "active": True} for role, kind in
             [("main", "claude"), ("engineer", "codex"), ("writer", "agy")]]
    plan = {"project": str(tmp_path), "host": "orca", "session": "original-session", "preset": "cc-codex-agy", "roles": roles}
    args = SimpleNamespace(ui_language="en", wizard_resume_existing=False,
                           wizard_arguments=deepcopy(bound["pending_start"]["arguments"]),
                           no_receiver=False, herdr_bin="unused-herdr")
    return SimpleNamespace(bound=bound, calls=calls, fake=fake, plan=plan, args=args, original=original)


def test_orca_ui_immediate_return_waits_for_explicit_continue_then_finishes_original_team(monkeypatch, orca_startup):
    fixture = orca_startup
    before = deepcopy(fixture.bound["pending_start"])

    def answer(prompt):
        assert fixture.calls["open"] == ["original-terminal"]
        assert fixture.calls["screen"] == ["original-terminal"]
        assert not fixture.calls["start"]
        fixture.bound["roles"]["main"]["status"] = "idle"  # user handled native UI
        return "1"

    def start(plan, args):
        fixture.calls["start"].append(deepcopy(plan))
        assert fixture.bound["pending_start"] == before
        assert fixture.bound["roles"]["main"]["process_incarnation"] == "original-pty"
        assert fixture.bound["roles"]["main"]["delivery"] == fixture.original["delivery"]
        for role, harness in [("engineer", "codex"), ("writer", "agy")]:
            fixture.bound["roles"][role] = {**fixture.original, "pane_id": role, "status": "idle", "harness": harness}
        return {"roles": deepcopy(fixture.bound["roles"])}

    monkeypatch.setattr("builtins.input", answer)
    monkeypatch.setattr(runtime, "start", start)
    result = wizard.launch(fixture.plan, fixture.args)
    assert set(result["roles"]) == {"main", "engineer", "writer"}
    assert len(fixture.calls["start"]) == 1
    assert result["receiver"] == {"active": True}  # Orca identity has no Herdr PID.
    assert "pending_start" not in fixture.bound
    assert fixture.args.wizard_attached


@pytest.mark.parametrize("answer", ["2", "q", "eof", "interrupt"])
def test_orca_keep_or_interrupt_preserves_owner_and_pending_no_start(monkeypatch, orca_startup, answer):
    fixture = orca_startup
    before = deepcopy(fixture.bound)

    def reply(prompt):
        if answer == "eof":
            raise EOFError
        if answer == "interrupt":
            raise KeyboardInterrupt
        return answer

    monkeypatch.setattr("builtins.input", reply)
    monkeypatch.setattr(runtime, "start", lambda *args: pytest.fail("blocked owner must not be restarted"))
    assert wizard.launch(fixture.plan, fixture.args) is None
    assert fixture.bound["pending_start"] == before["pending_start"]
    for field in ("pane_id", "process_incarnation", "runtime_id", "delivery"):
        assert fixture.bound["roles"]["main"][field] == before["roles"]["main"][field]
    assert fixture.calls["open"] == ["original-terminal"]


def test_orca_still_blocked_after_continue_never_retries_start(monkeypatch, orca_startup):
    fixture = orca_startup
    answers = iter(["1", "2"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(runtime, "start", lambda *args: pytest.fail("native wait is still active"))
    assert wizard.launch(fixture.plan, fixture.args) is None
    assert fixture.calls["open"] == ["original-terminal", "original-terminal"]
    assert fixture.calls["screen"] == ["original-terminal", "original-terminal"]
    assert "pending_start" in fixture.bound


def test_orca_start_error_with_native_wait_keeps_one_attempt_until_user_returns(monkeypatch, orca_startup):
    from superaris.client import HerdrError
    fixture = orca_startup
    fixture.bound["roles"]["main"]["status"] = "idle"

    def start(*args):
        fixture.calls["start"].append("attempt")
        fixture.bound["roles"]["main"]["status"] = "blocked"
        raise HerdrError("native trust required")

    monkeypatch.setattr(runtime, "start", start)
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    assert wizard.launch(fixture.plan, fixture.args) is None
    assert fixture.calls["start"] == ["attempt"]
    assert fixture.calls["open"] == ["original-terminal"]
    assert fixture.bound["roles"]["main"]["delivery"] == fixture.original["delivery"]


def test_orca_unknown_start_error_is_not_replayed_or_sent_to_herdr(monkeypatch, orca_startup):
    from superaris.client import HerdrError
    fixture = orca_startup
    fixture.bound["roles"]["main"]["status"] = "idle"

    def start(*args):
        fixture.calls["start"].append("attempt")
        raise HerdrError("unknown receipt; inspect original request")

    monkeypatch.setattr(runtime, "start", start)
    with pytest.raises(HerdrError, match="unknown receipt"):
        wizard.launch(fixture.plan, fixture.args)
    assert fixture.calls["start"] == ["attempt"]
    assert fixture.calls["open"] == []
    assert fixture.bound["roles"]["main"]["delivery"] == fixture.original["delivery"]
    assert "pending_start" in fixture.bound


def test_orca_owner_change_after_ui_open_stops_before_any_new_start(monkeypatch, orca_startup):
    from superaris.client import HerdrError
    fixture = orca_startup
    original_pending = deepcopy(fixture.bound["pending_start"])

    def reply(prompt):
        fixture.fake.replaced = True
        return "1"

    monkeypatch.setattr("builtins.input", reply)
    monkeypatch.setattr(runtime, "start", lambda *args: pytest.fail("changed owner must stop startup"))
    with pytest.raises(HerdrError, match="incarnation changed"):
        wizard.launch(fixture.plan, fixture.args)
    assert fixture.bound["pending_start"] == original_pending
    assert fixture.bound["roles"]["main"]["process_incarnation"] == "original-pty"
    assert fixture.calls["open"] == ["original-terminal"]


@pytest.mark.parametrize("source", ["binding", "pending_field", "canonical_argv", "equals_argv"])
def test_recovery_uses_existing_recorded_orca_cli_when_not_in_path_or_app(
        monkeypatch, tmp_path, capsys, source):
    launcher = tmp_path / "official bundle" / "bin" / "orca"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("official executable fixture; never run")
    bound = {"host": "orca", "session": "original-orca", "roles": {"main": {
        "harness": "codex", "inputs": {"task": "original"}}}}
    original_args = ["start", str(tmp_path), "--host", "orca", "--model", "main=original"]
    if source == "binding":
        bound["orca_bin"] = str(launcher)
    else:
        bound["pending_start"] = {"roles": [{"role": "main", "harness": "codex", "model": "original"}],
                                  "arguments": original_args}
        if source == "pending_field":
            bound["pending_start"]["orca_bin"] = str(launcher)
        elif source == "canonical_argv":
            original_args += ["--orca-bin", str(launcher)]
        else:
            original_args += ["--orca-bin=" + str(launcher)]
    before = deepcopy(bound)
    monkeypatch.setattr(hosts.shutil, "which", lambda binary: None)
    selection, prompts = select(monkeypatch, tmp_path, ["2", str(tmp_path), "1", "1"], available(), bound)
    assert selection is not None
    assert bound == before
    if source != "binding":
        assert selection.arguments == original_args
    output = capsys.readouterr().out
    assert "Orca: CLI found" in output
    assert "install and open Orca" not in output
    assert not any("Workbench host" in prompt for prompt in prompts)


def test_invalid_recorded_cli_is_reported_as_original_entry_not_new_install(monkeypatch, tmp_path, capsys):
    bound = {"host": "orca", "orca_bin": str(tmp_path / "missing-original-orca"),
             "session": "original-orca", "roles": {"main": {"harness": "codex"}}}
    monkeypatch.setattr(hosts.shutil, "which", lambda binary: None)
    selection, _ = select(monkeypatch, tmp_path, ["2", str(tmp_path), "1", "1"],
                          available(orca="unrelated-PATH-cli"), bound)
    assert selection is None
    output = capsys.readouterr().out
    assert "original project's Orca CLI is unavailable" in output
    assert "--orca-bin" in output
    assert "install and open Orca" not in output


@pytest.mark.parametrize("language", ["1", "2"])
def test_installed_orca_app_without_cli_reaches_registration_instead_of_herdr_install(
        monkeypatch, tmp_path, capsys, language):
    project = tmp_path / "new uncreated project"
    selection, prompts = select(monkeypatch, tmp_path, [language, str(project)],
                                available(app="installed/Orca.app", brew="available-brew"))
    assert selection is None
    assert not project.exists()
    output = capsys.readouterr().out
    assert "Settings → General → Orca CLI" in output
    assert "brew install herdr" not in output
    assert not any("Client combination" in prompt or "客户端组合" in prompt for prompt in prompts)


def test_first_blocked_check_uses_confirmed_explicit_launcher(monkeypatch, orca_startup):
    fixture = orca_startup
    fixture.args.orca_bin = '/original/non-PATH/orca'
    original = wizard._blocked
    seen = []
    def blocked(project, binary):
        seen.append(runtime.binding(project).get('orca_bin'))
        return original(project,binary)
    monkeypatch.setattr(wizard,'_blocked',blocked)
    monkeypatch.setattr('builtins.input',lambda _: '2')
    assert wizard.launch(fixture.plan,fixture.args) is None
    assert seen and all(path == fixture.args.orca_bin for path in seen)
