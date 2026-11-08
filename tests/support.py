"""Run the installed product rather than a repository-local launcher."""
import sys
from pathlib import Path

CLI = [sys.executable, "-m", "superaris"]


def make_aris_repo(path: Path) -> Path:
    """Small public dependency fixture; it contains no actual research/models."""
    for host in (path / "skills", path / "skills/skills-codex"):
        shared = host / "shared-references"
        shared.mkdir(parents=True, exist_ok=True)
        for name in ("contract.md", "reviewer-backends.md", "output-versioning.md", "output-manifest.md", "output-language.md"):
            (shared / name).write_text(f"# Synthetic {name}\n")
        for name in ("project-agent", "research-lit", "paper-write", "research-refine-pipeline", "research-refine", "experiment-plan"):
            skill = host / name
            skill.mkdir(exist_ok=True)
            (skill / "SKILL.md").write_text(f"# Synthetic {name}\nNo external tools or models are invoked by this fixture.\n")
    tools = path / "tools"
    tools.mkdir(exist_ok=True)
    (tools / "skill-groups.tsv").write_text(
        "group\tresearch\tResearch\tSynthetic stage\n"
        "skill\tproject-agent\tmeta\t-\tCoordination\n"
        "skill\tresearch-lit\tresearch\t-\tRead papers\n"
        "skill\tpaper-write\tresearch\t-\tWrite prose\n"
        "skill\tresearch-refine-pipeline\tresearch\tresearch-refine,experiment-plan\tPipeline\n"
        "skill\tresearch-refine\tresearch\t-\tMethod planning\n"
        "skill\texperiment-plan\tresearch\t-\tExperiment planning\n"
    )
    docs = path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "SKILLS_CATALOG.md").write_text(
        "# Synthetic catalog\n\n[Research refine](../skills/research-refine/SKILL.md)\n"
    )
    (path / "LICENSE").write_text("Synthetic test fixture created for SuperARIS behavior tests.\n")
    return path
