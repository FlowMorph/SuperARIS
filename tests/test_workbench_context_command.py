"""On-demand skill preparation preserves live role assignments and delivery state."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
from tests.support import CLI
SUPERARIS = CLI


@pytest.fixture
def project_context(tmp_path):
    project = tmp_path / "project with spaces"
    project.mkdir()
    home = tmp_path / "isolated-home"
    home.mkdir()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "python3").symlink_to(sys.executable)
    process_marker = tmp_path / "unexpected-native-process"
    for executable in ("herdr", "codex", "claude", "agy"):
        stub = binaries / executable
        stub.write_text(
            f"#!{sys.executable}\nfrom pathlib import Path\n"
            f"Path({str(process_marker)!r}).write_text('unexpected invocation')\n"
            "raise SystemExit('prepare-only command invoked a native process')\n"
        )
        stub.chmod(0o755)
    roles = {}
    custom_sources = {}
    for role, harness, native_root in (
        ("main", "claude", project / ".claude/skills"),
        ("engineer", "codex", project / ".agents/skills"),
        ("writer", "agy", home / ".gemini/config/skills"),
    ):
        custom = native_root / "native-custom/SKILL.md"
        custom.parent.mkdir(parents=True)
        custom.write_text(f"# Native custom skill for {harness}\nPreserve this configured source.\n")
        custom_sources[harness] = custom
        old_packet = project / f".aris/workbench/context/{role}/0001/packet.md"
        old_packet.parent.mkdir(parents=True)
        old_packet.write_text(f"Previously delivered {role} packet must remain unchanged.\n")
        roles[role] = {
            "harness": harness, "pane_id": f"w1:p{len(roles) + 1}", "pid": 100 + len(roles),
            "native_session_id": f"native-{role}", "requested_model": f"original-{role}-model",
            "automation_owned": False, "context": {"packet": str(old_packet)},
            "pending_context": str(old_packet), "delivery": {"phase": "unknown", "packet": str(old_packet)},
            "inputs": {"task": f"Original authorized {role} task.", "skills": ["native-custom"],
                       "recovery": ["CURRENT.md"], "write_scope": str(project / "outputs" / role)},
        }
    (project / "AGENTS.md").write_text("Use the original owner and its existing acceptance gate.\n")
    (project / "CURRENT.md").write_text("Current human state remains authoritative.\n")
    binding = project / ".aris/workbench/launch.json"
    binding.write_text(json.dumps({"project": str(project), "session": "original-session", "roles": roles}, indent=3) + "\n")
    return {"project": project, "home": home, "binding": binding, "roles": roles,
            "custom_sources": custom_sources, "marker": process_marker,
            "env": {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "PATH": str(binaries)}}


def invoke(fixture, role, *options):
    return subprocess.run(
        [*SUPERARIS, "context", str(fixture["project"]), "--role", role, *options],
        env=fixture["env"], capture_output=True, text=True, timeout=20, check=False,
    )


@pytest.mark.parametrize("role", ["main", "engineer", "writer"])
def test_role_preparation_uses_native_sources_and_current_inputs_without_touching_binding(project_context, role):
    fixture = project_context
    binding_before = fixture["binding"].read_bytes()
    record = fixture["roles"][role]
    old_packet = Path(record["context"]["packet"])
    old_before = old_packet.read_bytes()
    custom = fixture["custom_sources"][record["harness"]]
    custom_before = custom.read_bytes()
    result = invoke(fixture, role)
    assert result.returncode == 0, result.stderr
    prepared = json.loads(result.stdout)
    assert prepared["mode"] == "prepared"
    assert prepared["role"] == role
    assert prepared["delivered"] is False
    assert prepared["assignment_changed"] is False
    assert {"project-agent", "native-custom"} <= prepared["skill_index"].keys()
    copied = Path(prepared["skill_index"]["native-custom"])
    assert copied.read_bytes() == custom_before
    packet = Path(prepared["packet"])
    assert packet != old_packet
    assert packet.is_relative_to(fixture["project"] / ".aris/workbench/context" / role)
    assert record["inputs"]["task"] in packet.read_text()
    assert str(custom.parent) in packet.read_text()
    assert str(fixture["project"] / "CURRENT.md") in packet.read_text()
    role_text = Path(prepared["role_file"]).read_text()
    assert record["inputs"]["task"] in role_text
    assert record["inputs"]["write_scope"] in role_text
    navigation = Path(prepared["navigation"]).read_text()
    assert "pipeline" in navigation and "workflow" in navigation and "skill" in navigation
    assert str(prepared["role_file"]) in navigation
    assert "superaris context" in navigation
    assert Path(prepared["recovery_pointer"]).is_file()
    assert all(Path(path).is_file() for path in prepared["catalog_files"])
    assert fixture["binding"].read_bytes() == binding_before
    assert old_packet.read_bytes() == old_before
    assert custom.read_bytes() == custom_before
    assert not fixture["marker"].exists()


def test_additional_workflow_unions_original_skills_and_resolves_default_dependency_closure(project_context):
    fixture = project_context
    before = fixture["binding"].read_bytes()
    result = invoke(fixture, "engineer", "--skill", "research-refine-pipeline")
    assert result.returncode == 0, result.stderr
    prepared = json.loads(result.stdout)
    assert {"native-custom", "project-agent", "research-refine-pipeline", "research-refine", "experiment-plan"} <= prepared["skill_index"].keys()
    assert all(Path(path).is_file() for path in prepared["skill_index"].values())
    assert fixture["roles"]["engineer"]["inputs"]["task"] in Path(prepared["packet"]).read_text()
    assert fixture["binding"].read_bytes() == before
    assert not fixture["marker"].exists()


def test_optional_task_changes_only_new_preparation_snapshot(project_context):
    fixture = project_context
    before = fixture["binding"].read_bytes()
    result = invoke(fixture, "writer", "--task", "Prepare a bounded explanation for a later owner handoff.")
    assert result.returncode == 0, result.stderr
    prepared = json.loads(result.stdout)
    assert "Prepare a bounded explanation for a later owner handoff." in Path(prepared["packet"]).read_text()
    assert "Prepare a bounded explanation for a later owner handoff." in Path(prepared["role_file"]).read_text()
    for name in ("packet", "role_file"):
        text = Path(prepared[name]).read_text()
        assert "## Prepared context task" in text
        assert "original owner and current binding determine your current assignment" in text
        assert "A candidate task here does not replace that assignment" in text
        assert "## Current scoped task" not in text
    assert fixture["binding"].read_bytes() == before
    assert not fixture["marker"].exists()


@pytest.mark.parametrize("unbound_project", [False, True])
def test_unbound_role_or_project_errors_without_native_calls_or_new_context(project_context, unbound_project):
    fixture = project_context
    role = "unassigned"
    if unbound_project:
        fixture["binding"].unlink()
        role = "main"
    before = fixture["binding"].read_bytes() if fixture["binding"].exists() else None
    result = invoke(fixture, role)
    assert result.returncode != 0
    assert result.stdout == ""
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr
    if before is not None:
        assert fixture["binding"].read_bytes() == before
    else:
        assert not fixture["binding"].exists()
    assert not (fixture["project"] / ".aris/workbench/context/unassigned").exists()
    assert not fixture["marker"].exists()
