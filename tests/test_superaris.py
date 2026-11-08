"""SuperARIS entry and readable new-team layout, using fake Herdr only."""

import json
from pathlib import Path
import subprocess

from tests.test_aris_workbench import fake_herdr, project  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]
from tests.support import CLI
SUPERARIS = CLI


def invoke(entry, *args, env=None):
    return subprocess.run([*entry, *map(str, args)], env=env, capture_output=True,
                          text=True, timeout=20, check=False)


def team_start(project, fake, *options):
    return invoke(
        SUPERARIS, "start", project, "--session", "isolated-test", "--no-attach",
        "--no-install", "--no-receiver", "--herdr-bin", fake["binary"], *options,
        env=fake["env"],
    )


def test_installed_entry_has_help_and_offline_plan(project):
    arguments = ["start", project, "--plan", "--preset", "cc-codex-agy", "--only-role", "writer",
                 "--model", "writer=gemini-4-argon-high", "--task", "Existing approved task."]
    new = invoke(SUPERARIS, *arguments)
    assert new.returncode == 0, new.stderr
    assert json.loads(new.stdout)["mode"] == "plan"
    assert not (project / ".aris/workbench").exists()
    for entry, name in ((SUPERARIS, "superaris"),):
        result = invoke(entry, "--help")
        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith(f"usage: {name} ")


def test_new_three_role_team_gets_readable_names_and_right_column_layout(project, fake_herdr):
    result = team_start(
        project, fake_herdr, "--preset", "cc-codex-agy", "--only-role", "main",
        "--only-role", "engineer", "--only-role", "writer",
    )
    assert result.returncode == 0, result.stderr
    roles = json.loads(result.stdout)["roles"]
    commands = json.loads(fake_herdr["state"].read_text())["commands"]
    workspace, = [args for args in commands if args[:2] == ["workspace", "create"]]
    assert workspace[workspace.index("--label") + 1] == "SuperARIS " + project.name
    assert ["tab", "rename", "w1:t1", "SuperARIS · Workbench"] in commands
    expected_labels = {"main": "Claude Code", "engineer": "Codex", "writer": "Antigravity"}
    for role, label in expected_labels.items():
        assert ["pane", "rename", roles[role]["pane_id"], f"{role} · {label}"] in commands
        assert roles[role]["name"].startswith("superaris-")
        assert len(roles[role]["name"]) <= 32
    splits = [args for args in commands if args[:2] == ["pane", "split"]]
    assert [(args[2], args[args.index("--direction") + 1]) for args in splits] == [
        (roles["main"]["pane_id"], "right"), (roles["engineer"]["pane_id"], "down"),
    ]
    assert len({role["name"] for role in roles.values()}) == 3


def test_reentering_existing_team_preserves_names_and_topology(project, fake_herdr):
    options = ["--preset", "cc-codex-agy", "--only-role", "main", "--only-role", "engineer", "--only-role", "writer"]
    initial = team_start(project, fake_herdr, *options)
    assert initial.returncode == 0, initial.stderr
    state = json.loads(fake_herdr["state"].read_text())
    count = len(state["commands"])
    result = team_start(project, fake_herdr, *options)
    assert result.returncode == 0, result.stderr
    original_roles, reused_roles = json.loads(initial.stdout)["roles"], json.loads(result.stdout)["roles"]
    for name in original_roles:
        assert reused_roles[name]["pane_id"] == original_roles[name]["pane_id"]
        assert reused_roles[name]["name"] == original_roles[name]["name"]
    added = json.loads(fake_herdr["state"].read_text())["commands"][count:]
    assert not any(args[:2] in (["workspace", "create"], ["tab", "create"], ["pane", "split"],
                               ["tab", "rename"], ["pane", "rename"], ["agent", "start"]) for args in added)


def test_adopted_owner_retains_legacy_name_and_original_topology(project, fake_herdr):
    state = json.loads(fake_herdr["state"].read_text())
    state["agents"]["legacy-owner"] = {
        "name": "legacy-owner", "pane_id": "w8:p7", "tab_id": "w8:t3", "workspace_id": "w8",
        "agent": "codex", "agent_status": "idle", "pid": 4321,
        "argv": ["codex", "--cd", str(project)], "cwd": str(project.parent),
    }
    fake_herdr["state"].write_text(json.dumps(state))
    result = team_start(project, fake_herdr, "--only-role", "main", "--owner", "legacy-owner")
    assert result.returncode == 0, result.stderr
    owner = json.loads(result.stdout)["roles"]["main"]
    assert owner["name"] == "legacy-owner"
    assert owner["pane_id"] == "w8:p7"
    assert owner["created"] is False
    commands = json.loads(fake_herdr["state"].read_text())["commands"]
    assert not any(args[:2] in (["workspace", "create"], ["tab", "create"], ["pane", "split"],
                               ["tab", "rename"], ["pane", "rename"], ["agent", "start"]) for args in commands)
