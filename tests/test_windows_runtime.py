"""Portable fake-Herdr runtime contracts, executed on actual Windows CI too."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from superaris import client, cli, state, wizard
from tests.test_aris_workbench import FAKE_HERDR, start


def executable(path, body):
    script = path.with_suffix(".py")
    script.write_text(body, encoding="utf-8")
    if os.name == "nt":
        path = path.with_suffix(".cmd")
        path.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
    else:
        path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
        path.chmod(0o755)
    return path


@pytest.fixture
def portable_team(tmp_path):
    project = tmp_path / "科研 project with spaces"
    project.mkdir()
    binary = executable(tmp_path / "fake herdr", FAKE_HERDR)
    endpoint = tmp_path / "existing endpoint"
    endpoint.touch()
    record = tmp_path / "transport.json"
    state.write(record, {"project": str(project), "socket": str(endpoint), "pane_count": 0,
                         "agents": {}, "commands": []})
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for kind in ("codex", "claude", "agy"):
        executable(binaries / kind, "raise SystemExit('fake native must never be invoked')")
    env = {**os.environ, "ARIS_TEST_HERDR_STATE": str(record), "PYTHONUTF8": "1",
           "PATH": str(binaries) + os.pathsep + os.environ["PATH"]}
    return project, {"binary": binary, "state": record, "env": env}


@pytest.mark.parametrize("preset,expected", [
    ("codex", ["codex", "codex", "codex"]),
    ("cc-codex", ["claude", "codex", "claude"]),
    ("cc-codex-agy", ["claude", "codex", "agy"]),
])
def test_three_roles_start_and_reuse_with_native_paths(portable_team, preset, expected):
    project, fake = portable_team
    first = start(project, fake, "--preset", preset)
    assert first.returncode == 0, first.stderr
    before = json.loads(first.stdout)
    assert [before["roles"][r]["harness"] for r in ("main", "engineer", "writer")] == expected
    main = before["roles"]["main"]
    assert all("wait for the main" in before["roles"][r]["inputs"]["task"].lower() for r in ("engineer", "writer"))
    scopes = [Path(before["roles"][r]["inputs"]["write_scope"]) for r in ("engineer", "writer")]
    assert scopes[0] != scopes[1] and all(p.is_relative_to(project) for p in scopes)
    again = start(project, fake)
    assert again.returncode == 0, again.stderr
    after = json.loads(again.stdout)
    assert after["roles"]["main"]["pid"] == main["pid"]
    commands = state.read(fake["state"])["commands"]
    assert sum(c[:2] == ["agent", "start"] for c in commands) == 3
    # Unknown initial delivery never causes a second native start or prompt.
    binding = state.read(state.directory(project) / "launch.json")
    binding["roles"]["main"]["delivery"]["phase"] = "unknown"
    state.write(state.directory(project) / "launch.json", binding)
    previous_prompts = sum(c[:2] == ["agent", "prompt"] for c in commands)
    last = start(project, fake)
    assert last.returncode == 0, last.stderr
    commands = state.read(fake["state"])["commands"]
    assert sum(c[:2] == ["agent", "start"] for c in commands) == 3
    assert sum(c[:2] == ["agent", "prompt"] for c in commands) == previous_prompts


def test_executable_suffix_and_node_wrapper_keep_owner_identity(tmp_path):
    for argv in (["codex.exe", "--cd", str(tmp_path)], ["node.exe", "C:/tools/codex.js", "--cd", str(tmp_path)]):
        result = client.foreground({"foreground_processes": [{"argv": argv, "cwd": str(tmp_path), "pid": 123}]}, "codex")
        assert result["pid"] == 123 and Path(result["cwd"]) == tmp_path
    class Owner:
        def json(self, *args):
            if args[:2] == ("agent", "get"):
                return {"agent": {"pane_id": "w1:p1", "agent": "codex", "agent_session": {"value": "original"}}}
            return {"process_info": {"foreground_processes": [{"argv": ["codex.exe"], "cwd": str(tmp_path), "pid": 124}]}}
    with pytest.raises(client.HerdrError, match="process changed"):
        client.verify_owner(Owner(), {"pane_id": "w1:p1", "harness": "codex", "pid": 123, "native_session_id": "original"}, tmp_path)


def test_wizard_cancel_does_not_install_or_write(tmp_path, monkeypatch):
    import builtins
    answers = iter(["2", "q"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtins, "input", lambda _: next(answers))
    monkeypatch.setattr(wizard, "capabilities", lambda: dict.fromkeys(("herdr", "codex", "claude", "agy", "brew")))
    with pytest.raises(wizard.Cancelled):
        wizard.run()
    assert list(tmp_path.iterdir()) == []
