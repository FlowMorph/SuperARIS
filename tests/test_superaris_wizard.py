"""Actual terminal wizard paths; all Herdr and native harnesses remain fake."""

import codecs
import errno
import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import time

import pytest

from tests.test_aris_workbench import FAKE_HERDR
from superaris import receiver, wizard


ROOT = Path(__file__).resolve().parents[1]
from tests.support import CLI
SUPERARIS = CLI


class Terminal:
    def __init__(self, args, cwd, env, language=""):
        self.pid, self.master = pty.fork()
        if self.pid == 0:
            os.chdir(cwd)
            os.execvpe(SUPERARIS[0], [*SUPERARIS, *args], env)
        self.text = ""
        self.position = 0
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.exited = False
        if language is not None:
            self.expect("请选择语言 / Choose language")
            self.line(language)

    def read(self, timeout=0.05):
        if not select.select([self.master], [], [], timeout)[0]:
            return
        try:
            chunk = os.read(self.master, 65536)
        except OSError as exc:
            if exc.errno != errno.EIO:
                raise
            return
        self.text += self.decoder.decode(chunk)

    def expect(self, text, timeout=10):
        deadline = time.monotonic() + timeout
        while text not in self.text[self.position:]:
            assert time.monotonic() < deadline, f"Missing {text!r} in terminal:\n{self.text}"
            self.read()
        self.position = self.text.index(text, self.position) + len(text)

    def line(self, value=""):
        os.write(self.master, (value + "\n").encode())

    def finish(self, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.read()
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                self.exited = True
                self.read(0)
                return os.waitstatus_to_exitcode(status)
        pytest.fail("Wizard did not finish within the bounded terminal test:\n" + self.text)

    def close(self):
        if not self.exited:
            os.kill(self.pid, signal.SIGTERM)
            os.waitpid(self.pid, 0)
            self.exited = True
        os.close(self.master)


@pytest.fixture
def environment(tmp_path):
    project = tmp_path / "project with spaces"
    project.mkdir()
    state = tmp_path / "fake-state.json"
    socket = tmp_path / "fake-existing-socket"
    socket.touch()
    state.write_text(json.dumps({"project": str(project), "socket": str(socket),
                                 "pane_count": 0, "agents": {}, "commands": []}))
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "python3").symlink_to(sys.executable)
    fake = FAKE_HERDR.replace(
        'assert sys.argv[1:3] == ["--session", "isolated-test"], sys.argv',
        'assert sys.argv[1] == "--session", sys.argv',
    ).replace('state = json.loads(path.read_text())',
              'import fcntl\n'
              'state_lock = path.with_suffix(".lock").open("a")\n'
              'fcntl.flock(state_lock, fcntl.LOCK_EX)\n'
              'state = json.loads(path.read_text())'
    ).replace('    path.write_text(json.dumps(state))',
              '    temporary = path.with_name(path.name + "." + str(os.getpid()) + ".tmp")\n'
              '    temporary.write_text(json.dumps(state))\n'
              '    temporary.replace(path)'
    ).replace('if args == ["status"]:',
              'if not args:\n'
              '    if state.pop("replace_owner_on_attach", False):\n'
              '        for agent in state["agents"].values():\n'
              '            if agent["agent_status"] == "blocked":\n'
              '                agent["pid"] += 100\n'
              '    if state.get("blocked_attach_visits", 0):\n'
              '        state["blocked_attach_visits"] -= 1\n'
              '    else:\n'
              '        for agent in state["agents"].values():\n'
              '            if agent["agent_status"] == "blocked":\n'
              '                agent["agent_status"] = "idle"\n'
              '    save()\n    raise SystemExit(0)\n'
              'elif args[:2] == ["agent", "focus"]:\n'
              '    owner(args[2])\n    output({})\n'
              'elif args == ["status"]:')
    fake = fake.replace(
        '    output({"agent": state["agents"][name]})',
        '    if state.get("block_next_start") and kind == state.get("block_kind", "claude"):\n'
        '        state["block_next_start"] = False\n'
        '        state["agents"][name]["agent_status"] = "blocked"\n'
        '        save()\n'
        '        raise SystemExit("agent_not_ready: native trust required")\n'
        '    output({"agent": state["agents"][name]})',
    )
    (binaries / "herdr").write_text(f"#!{sys.executable}\n" + fake)
    (binaries / "herdr").chmod(0o755)
    for kind in ("codex", "claude", "agy"):
        path = binaries / kind
        path.write_text(f"#!{sys.executable}\nraise SystemExit('native harness must not run in wizard tests')\n")
        path.chmod(0o755)
    env = {**os.environ, "PATH": str(binaries), "ARIS_TEST_HERDR_STATE": str(state)}
    fixture = {"root": tmp_path, "project": project, "state": state, "bin": binaries, "env": env}
    yield fixture
    for record in tmp_path.rglob("receiver.json"):
        selected_project = record.parents[2]
        receiver.stop(selected_project)
        deadline = time.monotonic() + 10
        while receiver.status(selected_project)["managed_process_alive"] and time.monotonic() < deadline:
            time.sleep(0.05)
        remaining = receiver.status(selected_project)
        if remaining["managed_process_alive"]:
            os.kill(remaining["pid"], signal.SIGTERM)


@pytest.fixture
def terminal(environment):
    terminals = []

    def create(*args):
        term = Terminal(list(args), environment["root"], environment["env"])
        terminals.append(term)
        return term

    yield create
    for number, term in enumerate(terminals, 1):
        (environment["root"] / f"PTY-{number}.txt").write_text(term.text, encoding="utf-8")
        term.close()


def select_project(term, project):
    term.expect("[1/4] 选择项目")
    term.expect("项目目录")
    term.line(str(project))


def summary(term, combo="3", task="", models=None):
    term.expect("客户端组合")
    term.line(combo)
    for model_choice in models or [""] * 3:
        term.expect("模型选择")
        term.line(model_choice)
    term.expect("工作台名称")
    term.line()
    term.expect("本次任务")
    term.line(task)
    term.expect("[4/4] 启动摘要")
    term.expect("请选择")


@pytest.mark.parametrize("at_home", [False, True])
def test_home_and_filesystem_root_offer_separate_project_without_creating_it(tmp_path, at_home):
    home = tmp_path / "home"
    home.mkdir()
    cwd = home if at_home else Path(home.anchor)
    expected = home / "Desktop/superaris-project"
    assert wizard.default_project(cwd, home) == expected
    assert not expected.exists()


@pytest.mark.parametrize("args", [[], ["start"]])
def test_non_terminal_entry_is_friendly_and_does_not_start(environment, args):
    result = subprocess.run([*SUPERARIS, *args], env=environment["env"],
                            cwd=environment["root"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "需要交互终端" in result.stdout
    assert "未启动任何会话" in result.stdout
    assert json.loads(environment["state"].read_text())["commands"] == []
    assert not (environment["project"] / ".aris").exists()


def test_actual_terminal_three_role_summary_cancel_keeps_new_spaces_path_absent(environment, terminal):
    path = environment["root"] / "new project with spaces"
    term = terminal()
    select_project(term, path)
    summary(term)
    assert "Claude Code（CC）" in term.text
    assert "工程 / Codex" in term.text
    assert "写作 / AGY" in term.text
    assert "任务：暂不安排" in term.text
    term.line("3")
    assert term.finish() == 0
    assert "已取消启动" in term.text
    assert not path.exists()
    assert json.loads(environment["state"].read_text())["commands"] == []


@pytest.mark.parametrize("key", [b"\x03", b"\x04"])
def test_actual_terminal_interrupt_or_eof_cancels_without_mutation(environment, terminal, key):
    term = terminal()
    term.expect("项目目录")
    os.write(term.master, key)
    assert term.finish() == 0
    assert "已取消启动" in term.text
    assert json.loads(environment["state"].read_text())["commands"] == []
    assert not (environment["project"] / ".aris").exists()


def test_missing_selected_client_is_actionable_and_never_invoked(environment, terminal):
    (environment["bin"] / "agy").unlink()
    term = terminal()
    select_project(term, environment["project"])
    term.expect("客户端组合")
    term.line("3")
    term.expect("请先安装该组合缺少的客户端并完成原生登录")
    term.line("q")
    assert term.finish() == 0
    assert "缺少 Antigravity（AGY）" in term.text
    assert json.loads(environment["state"].read_text())["commands"] == []


def test_summary_return_keeps_selection_and_creates_no_project(environment, terminal):
    path = environment["root"] / "return without creating"
    term = terminal("start")
    select_project(term, path)
    summary(term)
    term.line("2")
    term.expect("[1/4] 选择项目")
    term.expect("项目目录")
    term.line()
    term.expect("客户端组合 [3]")
    term.line("q")
    assert term.finish() == 0
    assert not path.exists()
    assert json.loads(environment["state"].read_text())["commands"] == []


def test_summary_return_can_clear_previous_task_without_creating_project(environment, terminal):
    path = environment["root"] / "task can be cleared"
    term = terminal()
    select_project(term, path)
    summary(term, combo="1", task="This task should be cleared explicitly.")
    term.line("2")
    select_project(term, path)
    term.expect("客户端组合")
    term.line("1")
    for _ in range(3):
        term.expect("模型选择")
        term.line()
    term.expect("工作台名称")
    term.line()
    term.expect("任务安排")
    term.line("3")
    term.expect("[4/4] 启动摘要")
    term.expect("请选择")
    last_summary = term.text.rsplit("[4/4] 启动摘要", 1)[1]
    assert "This task should be cleared explicitly." not in last_summary
    assert "任务：暂不安排" in last_summary
    term.line("3")
    assert term.finish() == 0
    assert not path.exists()
    assert json.loads(environment["state"].read_text())["commands"] == []


def test_actual_terminal_confirmation_reaches_existing_runtime_with_three_active_roles(environment, terminal):
    path = environment["root"] / "new confirmed project with spaces"
    state = json.loads(environment["state"].read_text())
    state["project"] = str(path)
    environment["state"].write_text(json.dumps(state))
    term = terminal()
    select_project(term, path)
    summary(term, models=["", "", "3"])
    assert not path.exists()
    term.line("1")
    assert term.finish() == 0, term.text
    bound = json.loads((path / ".aris/workbench/launch.json").read_text())
    assert set(bound["roles"]) == {"main", "engineer", "writer"}
    assert [bound["roles"][role]["harness"] for role in ("main", "engineer", "writer")] == ["claude", "codex", "agy"]
    assert bound["roles"]["main"]["requested_model"] is None
    assert bound["roles"]["writer"]["requested_model"] == "gemini-4-argon-high"
    assert "wait for the user's concrete task" in bound["roles"]["main"]["inputs"]["task"]
    for role in ("engineer", "writer"):
        assert bound["roles"][role]["inputs"]["write_scope"] == str(path / "outputs" / role)
        assert "wait for the main owner's scoped assignment" in bound["roles"][role]["inputs"]["task"]
    live = receiver.status(path)
    assert live["managed_process_alive"] is True
    assert live["status"] == "running"
    assert all(Path(role["context"]["packet"]).is_file() for role in bound["roles"].values())


def test_actual_terminal_bound_project_resume_keeps_role_models_tasks_and_packets(environment, terminal):
    project = environment["project"]
    result = subprocess.run(
        [*SUPERARIS, "start", str(project), "--session", "original-session", "--preset", "cc-codex-agy",
         "--only-role", "main", "--only-role", "engineer", "--only-role", "writer", "--task", "Original approved task.",
         "--model", "main=original-main-model", "--model", "writer=original-writer-model",
         "--no-attach", "--no-install", "--no-receiver"],
        env=environment["env"], capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    before = json.loads((project / ".aris/workbench/launch.json").read_text())
    commands_before = len(json.loads(environment["state"].read_text())["commands"])
    term = terminal()
    select_project(term, project)
    term.expect("如何继续")
    term.line("1")
    term.expect("恢复摘要")
    term.expect("请选择")
    term.line("1")
    assert term.finish() == 0, term.text
    after = json.loads((project / ".aris/workbench/launch.json").read_text())
    assert after["session"] == "original-session"
    assert set(after["roles"]) == set(before["roles"])
    for name, original in before["roles"].items():
        assert after["roles"][name]["inputs"] == original["inputs"]
        assert after["roles"][name]["requested_model"] == original["requested_model"]
        assert after["roles"][name]["context"]["packet"] == original["context"]["packet"]
    added = json.loads(environment["state"].read_text())["commands"][commands_before:]
    assert not any(args[:2] in (["agent", "start"], ["agent", "prompt"], ["pane", "split"])
                   for args in added)


def test_actual_terminal_blocked_native_trust_reuses_owner_and_finishes_selected_team(environment, terminal):
    project = environment["project"]
    state = json.loads(environment["state"].read_text())
    state["block_next_start"] = True
    environment["state"].write_text(json.dumps(state))
    term = terminal()
    select_project(term, project)
    term.expect("客户端组合")
    term.line("3")
    term.expect("模型选择")
    term.line("2")
    term.expect("模型 ID")
    term.line("user-configured-cc-model")
    for _ in range(2):
        term.expect("模型选择")
        term.line("3")
    term.expect("工作台名称")
    term.line("Readable trust handoff")
    term.expect("本次任务")
    term.line("Wait for the user's scoped assignment.")
    term.expect("[4/4] 启动摘要")
    term.expect("请选择")
    term.line("1")
    assert term.finish() == 0, term.text
    bound = json.loads((project / ".aris/workbench/launch.json").read_text())
    assert set(bound["roles"]) == {"main", "engineer", "writer"}
    models = {"main": "user-configured-cc-model", "engineer": "gpt-6.1-sol", "writer": "gemini-4-argon-high"}
    for name, model in models.items():
        assert bound["roles"][name]["requested_model"] == model
    for name in ("engineer", "writer"):
        assert bound["roles"][name]["inputs"]["write_scope"] == str(project / "outputs" / name)
    state = json.loads(environment["state"].read_text())
    starts = [args for args in state["commands"] if args[:2] == ["agent", "start"]]
    assert [args[args.index("--kind") + 1] for args in starts] == ["claude", "codex", "agy"]
    assert starts[0][starts[0].index("--pane") + 1] == bound["roles"]["main"]["pane_id"]
    focused = [args for args in state["commands"] if args[:2] == ["agent", "focus"]]
    assert len(focused) == 1
    assert focused[0][2] in {bound["roles"]["main"]["pane_id"], bound["roles"]["main"]["name"]}
    assert len(state["submissions"]) == 1
    assert bound["roles"]["main"]["delivery"]["phase"] == "unknown"
    assert not any("send-keys" in args or "send_keys" in args for args in state["commands"])
    assert '"roles": {' not in term.text
    assert '"mode": "running"' not in term.text


def test_retained_blocked_wizard_resume_restores_original_three_role_selection(environment, terminal):
    project = environment["project"]
    state = json.loads(environment["state"].read_text())
    state.update(block_next_start=True, blocked_attach_visits=1)
    environment["state"].write_text(json.dumps(state))
    first = terminal()
    select_project(first, project)
    summary(first, models=["", "3", "3"])
    first.line("1")
    first.expect("客户端仍在等待")
    first.line("2")
    assert first.finish() == 0, first.text
    launch = project / ".aris/workbench/launch.json"
    retained = json.loads(launch.read_text())
    assert set(retained["roles"]) == {"main"}
    original_pane = retained["roles"]["main"]["pane_id"]
    pending = retained["pending_start"]
    arguments = pending["arguments"]
    assert [arguments[i + 1] for i, arg in enumerate(arguments) if arg == "--only-role"] == ["main", "engineer", "writer"]
    assert "engineer=gpt-6.1-sol" in arguments
    assert "writer=gemini-4-argon-high" in arguments
    assert "engineer=outputs/engineer" in arguments
    assert "writer=outputs/writer" in arguments
    second = terminal()
    select_project(second, project)
    second.expect("如何继续")
    second.line("1")
    second.expect("恢复摘要")
    second.expect("请选择")
    assert "gpt-6.1-sol" in second.text
    assert "gemini-4-argon-high" in second.text
    second.line("1")
    assert second.finish() == 0, second.text
    complete = json.loads(launch.read_text())
    assert not complete.get("pending_start")
    assert set(complete["roles"]) == {"main", "engineer", "writer"}
    assert complete["roles"]["main"]["pane_id"] == original_pane
    for name, model in (("engineer", "gpt-6.1-sol"), ("writer", "gemini-4-argon-high")):
        assert complete["roles"][name]["requested_model"] == model
        assert complete["roles"][name]["inputs"]["write_scope"] == str(project / "outputs" / name)
    commands = json.loads(environment["state"].read_text())["commands"]
    starts = [args for args in commands if args[:2] == ["agent", "start"]]
    assert [args[args.index("--kind") + 1] for args in starts] == ["claude", "codex", "agy"]
    assert complete["roles"]["main"]["delivery"]["phase"] == "unknown"
    assert len(json.loads(environment["state"].read_text())["submissions"]) == 1


def test_explicit_human_control_clears_prepared_codex_bootstrap_before_reentry(environment):
    project = environment["project"]
    state = json.loads(environment["state"].read_text())
    state.update(block_next_start=True, block_kind="codex")
    environment["state"].write_text(json.dumps(state))
    arguments = [*SUPERARIS, "start", str(project), "--session", "prepared-bootstrap",
                 "--no-install", "--no-attach", "--no-receiver", "--only-role", "main"]
    failed = subprocess.run(arguments, env=environment["env"], capture_output=True, text=True, timeout=20)
    assert failed.returncode != 0
    launch = project / ".aris/workbench/launch.json"
    role = json.loads(launch.read_text())["roles"]["main"]
    assert role["bootstrap_pending"] is True
    assert role["delivery"]["phase"] == "prepared"
    controlled = subprocess.run(
        [*SUPERARIS, "control", str(project), "--role", "main", "--mode", "human"],
        env=environment["env"], capture_output=True, text=True, timeout=20,
    )
    assert controlled.returncode == 0, controlled.stderr
    role = json.loads(launch.read_text())["roles"]["main"]
    assert role["automation_owned"] is False
    assert not role.get("bootstrap_pending")
    state = json.loads(environment["state"].read_text())
    for agent in state["agents"].values():
        agent["agent_status"] = "idle"
    state["visible_input"] = "› Ask Codex to do anything"
    environment["state"].write_text(json.dumps(state))
    resumed = subprocess.run(arguments, env=environment["env"], capture_output=True, text=True, timeout=20)
    assert resumed.returncode == 0, resumed.stderr
    role = json.loads(launch.read_text())["roles"]["main"]
    assert role["automation_owned"] is False
    assert role["delivery"]["phase"] == "visible_notice"
    state = json.loads(environment["state"].read_text())
    assert state.get("submissions", []) == []
    assert sum(args[:2] == ["agent", "start"] for args in state["commands"]) == 1


def test_replaced_owner_during_native_handoff_keeps_original_pin_and_stops_new_tasks(environment, terminal):
    state = json.loads(environment["state"].read_text())
    state.update(block_next_start=True, replace_owner_on_attach=True)
    environment["state"].write_text(json.dumps(state))
    term = terminal()
    select_project(term, environment["project"])
    summary(term)
    term.line("1")
    assert term.finish() != 0, term.text
    assert "process changed" in term.text.lower()
    bound = json.loads((environment["project"] / ".aris/workbench/launch.json").read_text())
    assert set(bound["roles"]) == {"main"}
    assert bound["roles"]["main"]["pid"] == 1001
    assert bound.get("pending_start")
    state = json.loads(environment["state"].read_text())
    assert next(iter(state["agents"].values()))["pid"] == 1101
    starts = [args for args in state["commands"] if args[:2] == ["agent", "start"]]
    assert len(starts) == 1
    assert starts[0][starts[0].index("--kind") + 1] == "claude"
    assert state.get("submissions", []) == []
