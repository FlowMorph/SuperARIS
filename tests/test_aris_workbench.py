"""Behavioral workbench tests use isolated projects and fake Herdr only."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
from tests.support import CLI
ARIS = CLI


def invoke(*args, env=None):
    return subprocess.run(
        [*ARIS, *map(str, args)], capture_output=True, text=True,
        env=env, timeout=20, check=False,
    )


def tree_contents(directory):
    return {str(p.relative_to(directory)): p.read_bytes()
            for p in directory.rglob("*") if p.is_file()}


@pytest.fixture
def project(tmp_path):
    project = tmp_path / "project with spaces; literal"
    project.mkdir()
    for name, content in {
        "AGENTS.md": "Continue only the authorized task.\n",
        ".aris/reviewer.json": '{"backend":"grok","effort":"xhigh"}\n',
        ".codex/config.toml": 'model = "user-model"\n',
        ".agents/skills/custom/SKILL.md": "User custom skill.\n",
        ".claude/settings.json": '{"custom":"retain"}\n',
    }.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return project


def test_plan_is_actual_offline_cli_without_project_or_global_mutation(project, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_herdr = tmp_path / "must not run herdr"
    fake_herdr.write_text(f"#!{sys.executable}\nraise SystemExit('Herdr must not run in plan mode')\n")
    fake_herdr.chmod(0o755)
    before_project = tree_contents(project)
    before_home = tree_contents(fake_home)
    environment = {**os.environ, "HOME": str(fake_home), "USERPROFILE": str(fake_home)}
    result = invoke("start", project, "--plan", "--herdr-bin", fake_herdr, env=environment)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["mode"] == "plan"
    assert plan["project"] == str(project)
    assert plan["will_mutate"] is False
    assert plan["skills"] == ["project-agent"]
    assert tree_contents(project) == before_project
    assert tree_contents(fake_home) == before_home
    assert not (project / ".aris" / "workbench").exists()


@pytest.mark.parametrize("preset,main_harness", [
    ("codex", "codex"), ("cc-codex", "claude"), ("cc-codex-agy", "claude"),
])
def test_plan_starts_three_roles_by_default_without_assuming_model(project, preset, main_harness):
    result = invoke("start", project, "--plan", "--preset", preset)
    assert result.returncode == 0, result.stderr
    roles = json.loads(result.stdout)["roles"]
    assert [(r["role"], r["harness"]) for r in roles if r["active"]] == [
        ("main", main_harness), ("engineer", "codex"),
        ("writer", {"codex": "codex", "cc-codex": "claude", "cc-codex-agy": "agy"}[preset]),
    ]
    assert all(r["model"] is None for r in roles)


def test_plan_preserves_explicit_session_task_skills_and_new_session_model_overrides(project):
    result = invoke(
        "start", project, "--plan", "--preset", "cc-codex-agy", "--session", "isolated-test",
        "--skill", "research-lit", "--skill", "paper-write", "--only-role", "main",
        "--only-role", "writer", "--model", "writer=gemini-4-argon-high",
        "--task", "Write the already approved method section.",
    )
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["session"] == "isolated-test"
    assert plan["task"] == "Write the already approved method section."
    assert plan["skills"] == ["research-lit", "paper-write"]
    roles = {r["role"]: r for r in plan["roles"]}
    assert roles["main"]["active"] is True
    assert roles["writer"]["active"] is True
    assert roles["writer"]["harness"] == "agy"
    assert roles["writer"]["model"] == "gemini-4-argon-high"
    assert roles["engineer"]["active"] is False


def test_optional_role_can_be_planned_without_starting_other_roles(project):
    result = invoke("start", project, "--plan", "--role", "figures=agy", "--only-role", "figures")
    assert result.returncode == 0, result.stderr
    roles = json.loads(result.stdout)["roles"]
    assert [(r["role"], r["harness"]) for r in roles if r["active"]] == [("figures", "agy")]


@pytest.mark.parametrize("options", [
    ["--model", "unknown=some-model"],
    ["--model", "missing-assignment"],
    ["--only-role", "unknown-role"],
    ["--role", "engineer=unknown-harness"],
])
def test_invalid_plan_selection_fails_without_writing(project, options):
    before = tree_contents(project)
    result = invoke("start", project, "--plan", *options)
    assert result.returncode != 0
    assert result.stdout == ""
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr
    assert tree_contents(project) == before


def test_nonexistent_project_is_not_created_for_plan(tmp_path):
    missing = tmp_path / "missing-project"
    result = invoke("start", missing, "--plan")
    assert result.returncode != 0
    assert "does not exist" in result.stderr
    assert not missing.exists()


FAKE_HERDR = r'''
import json, os, sys
from pathlib import Path

path = Path(os.environ["ARIS_TEST_HERDR_STATE"])
state = json.loads(path.read_text())
assert sys.argv[1:3] == ["--session", "isolated-test"], sys.argv
args = sys.argv[3:]
state["commands"].append(args)

def save():
    path.write_text(json.dumps(state))

def output(result):
    save()
    print(json.dumps({"result": result}))
    raise SystemExit(0)

def option(flag):
    return args[args.index(flag) + 1]

def owner(target):
    for agent in state["agents"].values():
        if target in (agent["name"], agent["pane_id"]):
            return agent
    save()
    raise SystemExit("no such fake owner")

if args == ["status"]:
    save()
    print("socket: " + state["socket"])
elif args == ["api", "snapshot"]:
    output({"snapshot": {"agents": list(state["agents"].values())}})
elif args[:2] == ["workspace", "create"]:
    state["pane_count"] += 1
    output({"workspace": {"workspace_id": "w1"}, "tab": {"tab_id": "w1:t1"}, "root_tab": {"tab_id": "w1:t1"},
            "root_pane": {"pane_id": f'w1:p{state["pane_count"]}', "tab_id": "w1:t1", "workspace_id": "w1"}})
elif args[:2] == ["pane", "split"]:
    state["pane_count"] += 1
    output({"pane": {"pane_id": f'w1:p{state["pane_count"]}', "tab_id": "w1:t1", "workspace_id": "w1"}})
elif args[:2] == ["tab", "create"]:
    state["pane_count"] += 1
    output({"tab": {"tab_id": f'w1:t{state["pane_count"]}'},
            "root_pane": {"pane_id": f'w1:p{state["pane_count"]}', "tab_id": f'w1:t{state["pane_count"]}', "workspace_id": "w1"}})
elif args[:2] in (["tab", "rename"], ["pane", "rename"]):
    output({})
elif args[:2] == ["agent", "start"]:
    name, kind, pane = args[2], option("--kind"), option("--pane")
    state["agents"][name] = {
        "name": name, "pane_id": pane, "agent": kind, "agent_status": "idle",
        "pid": 1000 + state["pane_count"],
        "argv": [kind, *args[args.index("--") + 1:]],
        "cwd": state["project"],
    }
    output({"agent": state["agents"][name]})
elif args[:2] in (["agent", "get"], ["pane", "get"]):
    output({"agent" if args[0] == "agent" else "pane": owner(args[2])})
elif args[:2] == ["pane", "process-info"]:
    agent = owner(option("--pane"))
    output({"process_info": {"pane_id": agent["pane_id"], "foreground_processes": [{
        "argv": agent["argv"], "cwd": agent["cwd"], "pid": agent["pid"],
    }]}})
elif args[:2] == ["agent", "read"]:
    owner(args[2])
    save()
    print(state.get("visible_input", "› Ask Codex to do anything"))
elif args[:2] == ["agent", "prompt"]:
    owner(args[2])
    state.setdefault("submissions", []).append(args[3])
    if state.pop("lose_next_prompt_response", False):
        save()
        raise SystemExit("simulated response lost after possible prompt submission")
    output({})
elif args[:2] == ["notification", "show"]:
    output({})
else:
    save()
    raise SystemExit("unexpected fake Herdr command: " + repr(args))
'''


@pytest.fixture
def fake_herdr(tmp_path, project):
    binary = tmp_path / "fake herdr; literal"
    binary.write_text(f"#!{sys.executable}\n" + FAKE_HERDR, encoding="utf-8")
    binary.chmod(0o755)
    socket = tmp_path / "existing-fake-socket"
    socket.touch()
    state = tmp_path / "herdr-state.json"
    state.write_text(json.dumps({
        "project": str(project), "socket": str(socket), "pane_count": 0,
        "agents": {}, "commands": [],
    }))
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for kind in ("codex", "claude", "agy"):
        harness = binaries / kind
        harness.write_text(f"#!{sys.executable}\nraise SystemExit('native harness must not execute in tests')\n")
        harness.chmod(0o755)
    environment = {
        **os.environ, "ARIS_TEST_HERDR_STATE": str(state),
        "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
    }
    return {"binary": binary, "state": state, "env": environment}


def start(project, fake, *options):
    return invoke(
        "start", project, "--session", "isolated-test", "--no-attach", "--no-install",
        "--no-receiver", "--herdr-bin", fake["binary"], *options, env=fake["env"],
    )


def test_start_non_git_project_without_native_id_preserves_customization(project, fake_herdr):
    before = tree_contents(project)
    result = start(project, fake_herdr, "--only-role", "main", "--task", "Inspect the existing approved task.")
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["mode"] == "running"
    assert value["acceptance"] == "not_evaluated"
    assert value["actions"][0]["action"] == "started"
    assert value["roles"]["main"]["native_session_id"] is None
    packet = Path(value["roles"]["main"]["context"]["packet"])
    assert packet.is_relative_to(project / ".aris" / "workbench")
    assert "Inspect the existing approved task." in packet.read_text()
    assert str(project / "AGENTS.md") in packet.read_text()
    assert all(path.startswith(".aris/workbench/") for path in tree_contents(project).keys() - before.keys())
    for path, original in before.items():
        actual = (project / path).read_bytes()
        if path == "AGENTS.md":
            assert actual.startswith(original)
            assert actual.count(b"<!-- ARIS workbench recovery: begin -->") == 1
            assert b".aris/workbench/RECOVERY.md" in actual
        else:
            assert actual == original
    assert not (project / ".git").exists()
    commands = json.loads(fake_herdr["state"].read_text())["commands"]
    assert sum(command[:2] == ["workspace", "create"] for command in commands) == 1
    assert sum(command[:2] == ["agent", "start"] for command in commands) == 1
    assert sum(command[:2] == ["agent", "prompt"] for command in commands) == 1


def test_repeat_start_reuses_owner_without_duplicate_team_or_prompt(project, fake_herdr):
    first = start(project, fake_herdr, "--only-role", "main")
    assert first.returncode == 0, first.stderr
    second = start(project, fake_herdr)
    assert second.returncode == 0, second.stderr
    initial, repeated = json.loads(first.stdout), json.loads(second.stdout)
    assert repeated["actions"][0]["action"] == "reused"
    assert repeated["roles"]["main"]["pane_id"] == initial["roles"]["main"]["pane_id"]
    commands = json.loads(fake_herdr["state"].read_text())["commands"]
    assert sum(command[:2] == ["workspace", "create"] for command in commands) == 1
    assert sum(command[:2] == ["agent", "start"] for command in commands) == 1
    assert sum(command[:2] == ["agent", "prompt"] for command in commands) == 1


def test_reuse_rejects_changed_owner_without_creating_replacement(project, fake_herdr):
    result = start(project, fake_herdr, "--only-role", "main")
    assert result.returncode == 0, result.stderr
    launch = project / ".aris" / "workbench" / "launch.json"
    before = launch.read_bytes()
    state = json.loads(fake_herdr["state"].read_text())
    next(iter(state["agents"].values()))["pid"] += 1
    fake_herdr["state"].write_text(json.dumps(state))
    result = start(project, fake_herdr)
    assert result.returncode != 0
    assert "process changed" in result.stderr.lower()
    assert launch.read_bytes() == before
    commands = json.loads(fake_herdr["state"].read_text())["commands"]
    assert sum(command[:2] == ["agent", "start"] for command in commands) == 1


def test_collaborators_get_distinct_tasks_and_exclusive_output_context(project, fake_herdr):
    result = start(
        project, fake_herdr, "--preset", "cc-codex-agy", "--only-role", "main",
        "--only-role", "engineer", "--only-role", "writer",
        "--task", "Coordinate the approved study.",
        "--role-task", "engineer=Implement only the approved analysis.",
        "--role-task", "writer=Draft the approved method explanation.",
        "--write-scope", "engineer=work/analysis", "--write-scope", "writer=work/writing",
    )
    assert result.returncode == 0, result.stderr
    roles = json.loads(result.stdout)["roles"]
    main = Path(roles["main"]["context"]["packet"]).read_text()
    engineer = Path(roles["engineer"]["context"]["packet"]).read_text()
    writer = Path(roles["writer"]["context"]["packet"]).read_text()
    assert "Coordinate the approved study." in main
    assert "Implement only the approved analysis." in engineer
    assert "Draft the approved method explanation." in writer
    assert "Coordinate the approved study." not in engineer + writer
    assert str(project / "work" / "analysis") in engineer
    assert str(project / "work" / "writing") in writer
    assert str(project / "work" / "analysis") in main
    assert str(project / "work" / "writing") in main
    assert len({roles[name]["context"]["packet"] for name in roles}) == len(roles)


def test_unassigned_collaborator_waits_instead_of_copying_main_task(project, fake_herdr):
    result = start(
        project, fake_herdr, "--preset", "cc-codex", "--only-role", "main",
        "--only-role", "engineer", "--task", "Main owner must make the next research decision.",
    )
    assert result.returncode == 0, result.stderr
    role = json.loads(result.stdout)["roles"]["engineer"]
    packet = Path(role["context"]["packet"]).read_text()
    assert "Main owner must make the next research decision." not in packet
    assert "wait" in role["inputs"]["task"].lower()
    assert Path(role["inputs"]["write_scope"]).is_relative_to(project / ".aris" / "workbench" / "outputs")


def test_overlapping_collaborator_scopes_fail_before_any_native_start(project, fake_herdr):
    result = start(
        project, fake_herdr, "--preset", "cc-codex-agy", "--only-role", "engineer",
        "--only-role", "writer", "--write-scope", "engineer=work", "--write-scope", "writer=work/writing",
    )
    assert result.returncode != 0
    assert "overlap" in result.stderr.lower()
    commands = json.loads(fake_herdr["state"].read_text())["commands"]
    assert not any(command[:2] == ["agent", "start"] for command in commands)


def test_changed_task_skills_recovery_refreshes_context_without_overwriting_human_input(project, fake_herdr):
    first = start(project, fake_herdr, "--only-role", "main", "--model", "main=original-model", "--task", "Initial authorized task.")
    assert first.returncode == 0, first.stderr
    original_role = json.loads(first.stdout)["roles"]["main"]
    original_packet = Path(original_role["context"]["packet"])
    original_text = original_packet.read_text()
    recovery = project / "CURRENT.md"
    recovery.write_text("The user's current result is authoritative.\n")
    state = json.loads(fake_herdr["state"].read_text())
    state["visible_input"] = "› unfinished human draft"
    fake_herdr["state"].write_text(json.dumps(state))
    result = start(
        project, fake_herdr, "--task", "Updated authorized task.", "--skill", "research-lit",
        "--recovery", "CURRENT.md", "--model", "main=must-not-replace-live-model",
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["actions"][0]["action"] == "context_updated"
    assert value["actions"][0]["delivery"] == "visible_notice"
    role = value["roles"]["main"]
    refreshed = Path(role["context"]["packet"])
    assert refreshed != original_packet
    assert original_packet.read_text() == original_text
    assert "Updated authorized task." in refreshed.read_text()
    assert str(recovery) in refreshed.read_text()
    assert {Path(path).parent.name for path in role["context"]["skill_files"]} >= {"project-agent", "research-lit"}
    assert role["requested_model"] == "original-model"
    assert role["pending_context"] == str(refreshed)
    state = json.loads(fake_herdr["state"].read_text())
    assert state["visible_input"] == "› unfinished human draft"
    assert len(state["submissions"]) == 1
    assert sum(command[:2] == ["agent", "start"] for command in state["commands"]) == 1


def test_explicit_human_owner_is_adopted_without_prompt_or_model_replacement(project, fake_herdr):
    state = json.loads(fake_herdr["state"].read_text())
    state["agents"]["human-owner"] = {
        "name": "human-owner", "pane_id": "w3:p4", "agent": "codex", "agent_status": "idle",
        "pid": 4321, "argv": ["codex", "--cd", str(project), "--model", "human-model"],
        "cwd": str(project.parent),
    }
    state["visible_input"] = "› unfinished human draft"
    fake_herdr["state"].write_text(json.dumps(state))
    result = start(project, fake_herdr, "--only-role", "main", "--owner", "human-owner", "--model", "main=other-model")
    assert result.returncode == 0, result.stderr
    role = json.loads(result.stdout)["roles"]["main"]
    assert role["pane_id"] == "w3:p4"
    assert role["automation_owned"] is False
    packet = Path(role["context"]["packet"]).read_text()
    assert "The runtime sets ARIS_REPO" not in packet
    assert os.environ["SUPERARIS_ARIS_REPO"] in packet
    state = json.loads(fake_herdr["state"].read_text())
    assert state["visible_input"] == "› unfinished human draft"
    assert not any(command[:2] in (["agent", "start"], ["agent", "prompt"], ["agent", "read"])
                   for command in state["commands"])
    assert any(command[:2] == ["notification", "show"] for command in state["commands"])


def test_plain_reconnect_preserves_existing_assignment_and_context(project, fake_herdr):
    (project / "CURRENT.md").write_text("Current authorized task and recovery entry.\n")
    initial = start(
        project, fake_herdr, "--only-role", "main", "--task", "Keep this original assignment.",
        "--skill", "research-lit", "--recovery", "CURRENT.md",
        "--write-scope", "main=outputs/main", "--model", "main=original-model",
    )
    assert initial.returncode == 0, initial.stderr
    original = json.loads(initial.stdout)["roles"]["main"]
    state_before = json.loads(fake_herdr["state"].read_text())
    packet_before = Path(original["context"]["packet"]).read_bytes()
    result = start(project, fake_herdr)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["actions"][0]["action"] == "reused"
    role = value["roles"]["main"]
    assert role["inputs"] == original["inputs"]
    assert role["context"]["packet"] == original["context"]["packet"]
    assert role["requested_model"] == "original-model"
    assert Path(role["context"]["packet"]).read_bytes() == packet_before
    state_after = json.loads(fake_herdr["state"].read_text())
    assert state_after["submissions"] == state_before["submissions"]
    assert sum(c[:2] == ["notification", "show"] for c in state_after["commands"]) == 0


def test_historical_inactive_writer_still_owns_its_scope(project, fake_herdr):
    initial = start(
        project, fake_herdr, "--preset", "cc-codex-agy", "--only-role", "main",
        "--only-role", "writer", "--write-scope", "writer=paper",
    )
    assert initial.returncode == 0, initial.stderr
    original_state = json.loads(fake_herdr["state"].read_text())
    result = start(
        project, fake_herdr, "--preset", "cc-codex-agy", "--only-role", "engineer",
        "--write-scope", "engineer=paper/figs",
    )
    assert result.returncode != 0
    assert "overlap" in result.stderr.lower()
    state = json.loads(fake_herdr["state"].read_text())
    assert state["agents"] == original_state["agents"]
    launch = json.loads((project / ".aris/workbench/launch.json").read_text())
    assert "engineer" not in launch["roles"]


def test_adding_engineer_alone_updates_existing_main_exclusion(project, fake_herdr):
    initial = start(project, fake_herdr, "--only-role", "main", "--task", "Main's original authorized task.")
    assert initial.returncode == 0, initial.stderr
    original = json.loads(initial.stdout)["roles"]["main"]
    result = start(
        project, fake_herdr, "--preset", "cc-codex", "--only-role", "engineer",
        "--write-scope", "engineer=work/engineering", "--role-task", "engineer=Implement the scoped module.",
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    role = value["roles"]["main"]
    assert role["context"]["packet"] != original["context"]["packet"]
    packet = Path(role["context"]["packet"]).read_text()
    assert "Main's original authorized task." in packet
    assert str(project / "work/engineering") in packet
    assert "excluded" in packet.lower()
    assert any(action["role"] == "main" and action["action"] == "context_updated" for action in value["actions"])
    assert any(action["role"] == "engineer" and action["action"] == "started" for action in value["actions"])


def test_unknown_prompt_delivery_is_durable_and_reentry_does_not_resend(project, fake_herdr):
    initial = start(project, fake_herdr, "--only-role", "main", "--automation-owned", "--task", "Initial assignment.")
    assert initial.returncode == 0, initial.stderr
    state = json.loads(fake_herdr["state"].read_text())
    state["lose_next_prompt_response"] = True
    fake_herdr["state"].write_text(json.dumps(state))
    failed = start(project, fake_herdr, "--task", "Updated assignment with uncertain submission.")
    assert failed.returncode != 0
    launch_file = project / ".aris/workbench/launch.json"
    uncertain = json.loads(launch_file.read_text())["roles"]["main"]
    assert uncertain["delivery"]["phase"] == "unknown"
    packet = uncertain["context"]["packet"]
    assert Path(packet).is_file()
    state = json.loads(fake_herdr["state"].read_text())
    submissions = list(state["submissions"])
    assert len(submissions) == 2
    result = start(project, fake_herdr)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["actions"][0]["action"] == "pending_unknown"
    assert value["roles"]["main"]["delivery"]["phase"] == "unknown"
    assert value["roles"]["main"]["context"]["packet"] == packet
    assert json.loads(fake_herdr["state"].read_text())["submissions"] == submissions


def test_explicit_human_control_handoff_revokes_automation_after_identity_check(project, fake_herdr):
    result = start(project, fake_herdr, "--only-role", "main", "--automation-owned")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["roles"]["main"]["automation_owned"] is True
    before = json.loads(fake_herdr["state"].read_text())
    result = invoke(
        "control", project, "--role", "main", "--mode", "human",
        "--herdr-bin", fake_herdr["binary"], env=fake_herdr["env"],
    )
    assert result.returncode == 0, result.stderr
    launch = json.loads((project / ".aris/workbench/launch.json").read_text())
    assert launch["roles"]["main"]["automation_owned"] is False
    after = json.loads(fake_herdr["state"].read_text())
    assert after["submissions"] == before["submissions"]
    added_commands = after["commands"][len(before["commands"]):]
    assert any(command[:2] == ["agent", "get"] for command in added_commands)
    assert any(command[:2] == ["pane", "process-info"] for command in added_commands)


def test_resolved_unknown_delivery_preserves_human_draft_revocation_on_reentry(project, fake_herdr):
    initial = start(project, fake_herdr, "--only-role", "main", "--automation-owned", "--task", "Initial assignment.")
    assert initial.returncode == 0, initial.stderr
    state = json.loads(fake_herdr["state"].read_text())
    state["lose_next_prompt_response"] = True
    fake_herdr["state"].write_text(json.dumps(state))
    failed = start(project, fake_herdr, "--task", "Assignment requiring delivery reconciliation.")
    assert failed.returncode != 0
    launch_file = project / ".aris/workbench/launch.json"
    assert json.loads(launch_file.read_text())["roles"]["main"]["delivery"]["phase"] == "unknown"
    evidence = project / "CURRENT.md"
    evidence.write_text("Operator checked the actual receipt and selected not-delivered.\n")
    resolved = invoke(
        "resolve-delivery", project, "--role", "main", "--resolution", "not-delivered",
        "--evidence", "CURRENT.md", env=fake_herdr["env"],
    )
    assert resolved.returncode == 0, resolved.stderr
    assert json.loads(launch_file.read_text())["roles"]["main"]["delivery"]["phase"] == "prepared"
    state = json.loads(fake_herdr["state"].read_text())
    state["visible_input"] = "› unfinished human draft after delivery reconciliation"
    submissions = list(state["submissions"])
    fake_herdr["state"].write_text(json.dumps(state))
    result = start(project, fake_herdr)
    assert result.returncode == 0, result.stderr
    role = json.loads(launch_file.read_text())["roles"]["main"]
    assert role["delivery"]["phase"] == "visible_notice"
    assert role["delivery"]["receipt"]["revoke_automation"] is True
    assert role["automation_owned"] is False
    state = json.loads(fake_herdr["state"].read_text())
    assert state["submissions"] == submissions
    assert state["visible_input"] == "› unfinished human draft after delivery reconciliation"
    state["visible_input"] = "› Ask Codex to do anything"
    fake_herdr["state"].write_text(json.dumps(state))
    for options in ((), ("--task", "A later explicitly authorized assignment.")):
        result = start(project, fake_herdr, *options)
        assert result.returncode == 0, result.stderr
        assert json.loads(launch_file.read_text())["roles"]["main"]["automation_owned"] is False
        assert json.loads(fake_herdr["state"].read_text())["submissions"] == submissions
