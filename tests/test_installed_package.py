"""Run this suite after installing a wheel, rather than an editable checkout."""
from importlib import metadata, resources
from pathlib import Path

import superaris
import pytest

from superaris.context import prepare_context


def test_product_import_and_resources_come_from_installed_distribution():
    origin = Path(superaris.__file__).resolve()
    assert "site-packages" in origin.parts or "dist-packages" in origin.parts
    assert metadata.version("superaris") == superaris.__version__
    product = resources.files("superaris")
    for host in ("codex", "claude"):
        skill = product / "resources" / host / "project-agent" / "SKILL.md"
        assert skill.is_file()
        assert "project-agent" in str(skill)


@pytest.mark.parametrize("harness", ["codex", "claude", "agy"])
def test_packaged_product_skill_precedes_canonical_fixture_fallback(tmp_path, harness):
    project = tmp_path / "project"
    project.mkdir()
    prepared = prepare_context(project, "main", harness, "Wait for the user's assignment.", [])
    host = "codex" if harness == "codex" else "claude"
    expected = resources.files("superaris") / "resources" / host / "project-agent" / "SKILL.md"
    actual = Path(prepared["skill_index"]["project-agent"])
    assert actual.read_bytes() == expected.read_bytes()
    assert str(expected.parent) in Path(prepared["packet"]).read_text()
