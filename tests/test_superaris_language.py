"""Workbench interface language stays independent of research tasks and input."""

import json
from pathlib import Path
import re
import subprocess
import unicodedata

import pytest

from tests.test_superaris_wizard import Terminal, environment, select_project, summary  # noqa: F401
from superaris.delivery import deliver
from superaris import ui, wizard


ROOT = Path(__file__).resolve().parents[1]
from tests.support import CLI
SUPERARIS = CLI


@pytest.fixture
def language_environment(environment):
    home = environment["root"] / "isolated-home"
    home.mkdir()
    environment["env"].update(HOME=str(home), USERPROFILE=str(home))
    environment["home"] = home
    return environment


@pytest.fixture
def language_terminal(language_environment):
    terminals = []

    def create(cwd=None):
        term = Terminal([], cwd or language_environment["root"], language_environment["env"], language=None)
        terminals.append(term)
        return term

    yield create
    for number, term in enumerate(terminals, 1):
        (language_environment["root"] / f"PTY-LANGUAGE-{number}.txt").write_text(term.text, encoding="utf-8")
        term.close()


def choose_language(term, language, default=1):
    term.expect("界面语言 / Interface language")
    term.expect(f"请选择语言 / Choose language [{default}]")
    assert "简体中文" in term.text and "English" in term.text
    before = len(term.text)
    term.line("2" if language == "en" else "1")
    return before


def select_project_en(term, project):
    term.expect("[1/4] Choose a project")
    term.expect("Project directory")
    term.line(str(project))


def summary_en(term):
    term.expect("Client combination")
    term.line("3")
    for _ in range(3):
        term.expect("Model selection")
        term.line()
    term.expect("Workbench name")
    term.line()
    term.expect("Task (leave blank")
    term.line()
    term.expect("[4/4] Startup summary")
    term.expect("Choose an option")


@pytest.mark.parametrize("language", ["zh", "en"])
def test_language_is_first_actual_terminal_choice_and_summary_cancel_is_read_only(language_environment, language_terminal, language):
    fixture = language_environment
    project = fixture["root"] / "new language project"
    term = language_terminal()
    start = choose_language(term, language)
    if language == "en":
        select_project_en(term, project)
        summary_en(term)
    else:
        select_project(term, project)
        summary(term)
    term.line("3")
    assert term.finish() == 0, term.text
    assert not project.exists()
    assert json.loads(fixture["state"].read_text())["commands"] == []
    assert list(fixture["home"].rglob("*")) == []
    if language == "en":
        assert "Startup cancelled" in term.text
        assert not re.search(r"[\u4e00-\u9fff]", term.text[start:])
    else:
        assert "已取消启动" in term.text


@pytest.mark.parametrize("language", ["zh", "en"])
def test_confirmed_new_labels_follow_ui_language_without_changing_task_language(language_environment, language_terminal, language):
    fixture = language_environment
    term = language_terminal()
    start = choose_language(term, language)
    if language == "en":
        select_project_en(term, fixture["project"])
        summary_en(term)
    else:
        select_project(term, fixture["project"])
        summary(term)
    term.line("1")
    assert term.finish() == 0, term.text
    bound = json.loads((fixture["project"] / ".aris/workbench/launch.json").read_text())
    assert bound["ui_language"] == language
    assert set(bound["roles"]) == {"main", "engineer", "writer"}
    commands = json.loads(fixture["state"].read_text())["commands"]
    titles = {"main": "Main", "engineer": "Engineer", "writer": "Writer"} if language == "en" else {
        "main": "主会话", "engineer": "工程", "writer": "写作"}
    for role, title in titles.items():
        matching = [args for args in commands if args[:3] == ["pane", "rename", bound["roles"][role]["pane_id"]]]
        assert len(matching) == 1
        assert matching[0][3].startswith(title + " · ")
        expected_wait = "wait for the user's concrete task" if role == "main" else "wait for the main owner's scoped assignment"
        assert expected_wait in bound["roles"][role]["inputs"]["task"]
        assert bound["roles"][role]["requested_model"] is None
    assert ["tab", "rename", "w1:t1", "SuperARIS · " + ("Workbench" if language == "en" else "工作台")] in commands
    if language == "en":
        assert not re.search(r"[\u4e00-\u9fff]", term.text[start:])
    assert list(fixture["home"].rglob("*")) == []


def test_bound_resume_changes_only_ui_preference_and_retains_unknown_assignment(language_environment, language_terminal):
    fixture = language_environment
    result = subprocess.run(
        [*SUPERARIS, "start", str(fixture["project"]), "--session", "original-language-session",
         "--preset", "cc-codex-agy", "--only-role", "main", "--only-role", "engineer", "--only-role", "writer",
         "--task", "保留中文论文任务", "--model", "main=original-main", "--model", "writer=original-writer",
         "--no-attach", "--no-install", "--no-receiver"],
        env=fixture["env"], capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    launch = fixture["project"] / ".aris/workbench/launch.json"
    before = json.loads(launch.read_text())
    before["ui_language"] = "zh"
    before["roles"]["main"]["delivery"]["phase"] = "unknown"
    before["roles"]["main"]["delivery"]["error"] = "original unknown submission"
    launch.write_text(json.dumps(before))
    commands_before = len(json.loads(fixture["state"].read_text())["commands"])
    term = language_terminal(cwd=fixture["project"])
    choose_language(term, "en")
    select_project_en(term, fixture["project"])
    term.expect("How to continue")
    term.line("1")
    term.expect("Recovery summary")
    term.expect("Choose an option")
    term.line("1")
    assert term.finish() == 0, term.text
    after = json.loads(launch.read_text())
    assert after["ui_language"] == "en"
    before.pop("ui_language")
    after.pop("ui_language")
    assert after == before
    added = json.loads(fixture["state"].read_text())["commands"][commands_before:]
    assert not any(args[:2] in (["agent", "start"], ["agent", "prompt"], ["pane", "rename"], ["tab", "rename"])
                   for args in added)


def test_pending_resume_changes_ui_but_preserves_original_launch_arguments(language_environment, language_terminal):
    fixture = language_environment
    state = json.loads(fixture["state"].read_text())
    state.update(block_next_start=True, blocked_attach_visits=2)
    fixture["state"].write_text(json.dumps(state))
    first = language_terminal()
    choose_language(first, "zh")
    select_project(first, fixture["project"])
    summary(first, models=["", "3", "3"])
    first.line("1")
    first.expect("客户端仍在等待")
    first.line("2")
    assert first.finish() == 0, first.text
    launch = fixture["project"] / ".aris/workbench/launch.json"
    before = json.loads(launch.read_text())
    original_pending = before["pending_start"]
    original_roles = before["roles"]
    second = language_terminal(cwd=fixture["project"])
    choose_language(second, "en")
    select_project_en(second, fixture["project"])
    second.expect("How to continue")
    second.line("1")
    second.expect("Recovery summary")
    second.expect("Choose an option")
    second.line("1")
    second.expect("The client is still waiting")
    second.line("2")
    assert second.finish() == 0, second.text
    after = json.loads(launch.read_text())
    assert after["ui_language"] == "en"
    assert after["pending_start"] == original_pending
    assert after["roles"] == original_roles
    assert sum(args[:2] == ["agent", "start"] for args in json.loads(fixture["state"].read_text())["commands"]) == 1


def test_saved_cwd_language_is_first_screen_default_and_cancel_does_not_write(language_environment, language_terminal):
    fixture = language_environment
    launch = fixture["project"] / ".aris/workbench/launch.json"
    launch.parent.mkdir(parents=True)
    launch.write_text(json.dumps({"ui_language": "en", "session": "original", "roles": {"main": {"harness": "codex"}}}))
    before = launch.read_bytes()
    term = language_terminal(cwd=fixture["project"])
    term.expect("请选择语言 / Choose language [2]")
    term.line()
    term.expect("Project directory")
    term.line("q")
    assert term.finish() == 0, term.text
    assert "Startup cancelled" in term.text
    assert launch.read_bytes() == before
    assert json.loads(fixture["state"].read_text())["commands"] == []


@pytest.mark.parametrize("language,title", [("zh", "ARIS 工作包已准备"), ("en", "ARIS work packet ready")])
def test_notification_chrome_changes_but_original_prompt_body_does_not(tmp_path, language, title):
    project = tmp_path / "notification-project"
    directory = project / ".aris/workbench"
    directory.mkdir(parents=True)
    role = {"pane_id": "w1:p1", "harness": "codex", "pid": 123, "automation_owned": False}
    (directory / "launch.json").write_text(json.dumps({"ui_language": language, "roles": {"main": role}}))
    calls = []

    class FakeClient:
        def json(self, *args):
            calls.append(args)
            if args[:2] == ("agent", "get"):
                return {"agent": {"pane_id": "w1:p1", "agent": "codex", "agent_status": "idle"}}
            if args[:2] == ("pane", "process-info"):
                return {"process_info": {"foreground_processes": [{"argv": ["codex"], "cwd": str(project), "pid": 123}]}}
            assert args[:2] == ("notification", "show")
            return {}

    prompt = "保留中文论文任务；read the original packet without translating the assignment."
    receipt = deliver(FakeClient(), project, role, prompt)
    assert receipt["delivery"] == "visible_notice"
    notification, = [args for args in calls if args[:2] == ("notification", "show")]
    assert notification[2] == title
    assert notification[notification.index("--body") + 1] == prompt


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize("role_count", [1, 2, 3])
def test_layout_preview_borders_align_by_terminal_display_columns(capsys, language, role_count):
    previous = ui.language
    try:
        ui.set_language(language)
        wizard.layout(wizard.COMBINATIONS[2][2][:role_count])
    finally:
        ui.set_language(previous)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith(("┌", "│", "├", "└"))]

    def border_columns(line):
        columns = set()
        column = 0
        for character in line:
            if character in "┌┬┐├┼┤└┴┘│":
                columns.add(column)
            column += 0 if unicodedata.combining(character) else 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
        return columns, column

    assert lines
    expected = border_columns(lines[0])
    assert all(border_columns(line) == expected for line in lines[1:])
