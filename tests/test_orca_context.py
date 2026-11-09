"""Offline packet reachability for Orca, including custom skill precedence."""
import json
from pathlib import Path

import pytest

from superaris.context import prepare_context
from tests.support import make_aris_repo


@pytest.fixture
def project_and_repo(tmp_path):
    project = tmp_path / "research project 中文"
    project.mkdir()
    (project / "CURRENT.md").write_text("Original task owner and paused Goal remain authoritative.\n", encoding="utf-8")
    return project, make_aris_repo(tmp_path / "aris source")


@pytest.mark.parametrize("harness", ["codex", "claude", "agy"])
def test_explicit_orca_packet_reaches_host_instructions_before_binding(project_and_repo, harness):
    project, repo = project_and_repo
    prepared = prepare_context(project, "writer", harness, "Read existing results", [], repo=repo,
                               workbench_host="orca")
    packet = Path(prepared["packet"]).read_text(encoding="utf-8")
    navigation = Path(prepared["navigation"]).read_text(encoding="utf-8")
    host = Path(prepared["host_reference"])
    assert prepared["workbench_host"] == "orca"
    assert str(host) in packet and str(host) in navigation
    assert "Workbench host: orca" in packet
    assert "Workbench host: **orca**" in navigation
    assert "terminal handle" in host.read_text(encoding="utf-8")
    assert "native coordinator" in host.read_text(encoding="utf-8")
    assert "independent reviewer" in host.read_text(encoding="utf-8")
    assert "personal preferences" in host.read_text(encoding="utf-8")
    assert not (project / ".aris/workbench/launch.json").exists()


@pytest.mark.parametrize("bound_host,expected", [("orca", "orca"), ("herdr", "herdr"), (None, "herdr")])
def test_context_recovers_bound_host_without_rewriting_binding(project_and_repo, bound_host, expected):
    project, repo = project_and_repo
    binding = project / ".aris/workbench/launch.json"
    binding.parent.mkdir(parents=True)
    record = {"roles": {}, "session": "original", **({"host": bound_host} if bound_host else {})}
    binding.write_text(json.dumps(record), encoding="utf-8")
    before = binding.read_bytes()
    result = prepare_context(project, "main", "codex", "Recover original task", [], repo=repo)
    assert result["workbench_host"] == expected
    assert bool(result["host_reference"]) is (expected == "orca")
    assert binding.read_bytes() == before


@pytest.mark.parametrize("harness,native_dir", [("codex", ".agents"), ("claude", ".claude"), ("agy", ".gemini/config")])
def test_custom_project_agent_preserved_while_orca_entry_remains_required(project_and_repo, harness, native_dir, monkeypatch):
    project, repo = project_and_repo
    native_root = project
    if harness == "agy":
        native_root = project.parent / "agy-home"
        monkeypatch.setenv("HOME", str(native_root))
        monkeypatch.setenv("USERPROFILE", str(native_root))
    skill = native_root / native_dir / "skills/project-agent/SKILL.md"
    skill.parent.mkdir(parents=True)
    custom = "# Existing custom project-agent\nUse the existing private task contract.\n"
    skill.write_text(custom, encoding="utf-8")
    # Native installed customizations retain source precedence, including their
    # required shared reference tree; the host entry is independent of copying.
    shared = skill.parent.parent / "shared-references"
    shared.mkdir()
    (shared / "contract.md").write_text("existing contract", encoding="utf-8")
    result = prepare_context(project, "main", harness, "Continue", ["project-agent"], repo=repo,
                             workbench_host="orca")
    assert Path(result["skill_index"]["project-agent"]).read_text(encoding="utf-8") == custom
    assert skill.read_text(encoding="utf-8") == custom
    assert str(result["host_reference"]) in Path(result["packet"]).read_text(encoding="utf-8")


def test_unknown_host_rejected_before_context_allocation(project_and_repo):
    project, repo = project_and_repo
    with pytest.raises(ValueError, match="Unsupported workbench host"):
        prepare_context(project, "main", "codex", "Continue", [], repo=repo, workbench_host="other")
    assert not (project / ".aris/workbench/context").exists()
