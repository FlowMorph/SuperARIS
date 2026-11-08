"""Context copies preserve host resources and leave authoritative inputs alone."""

import importlib.util
from pathlib import Path

import pytest


from superaris import context as context_module
from superaris.context import prepare_context


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    repo = tmp_path / "repo"
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("actual project instructions")
    for host, label in ((repo / "skills", "mainline"), (repo / "skills/skills-codex", "codex")):
        selected = host / "project-agent"
        (selected / "scripts").mkdir(parents=True)
        (selected / "references").mkdir()
        (selected / "assets").mkdir()
        (selected / "SKILL.md").write_text(label + " ./references/guide.md ../shared-references/contract.md")
        (selected / "scripts/run.py").write_text("print('resource')")
        (selected / "references/guide.md").write_text("guide")
        (selected / "assets/icon.svg").write_text("<svg/>")
        (host / "shared-references").mkdir()
        (host / "shared-references/contract.md").write_text(label + " contract")
        (host / "unselected").mkdir()
        (host / "unselected/SKILL.md").write_text("not selected")
    native_roots = context_module._native_roots
    monkeypatch.setattr(context_module, "_native_roots", lambda selected_project, harness: [
        *native_roots(selected_project, harness),
        repo / ("skills/skills-codex" if harness == "codex" else "skills"),
    ])
    return project, repo


@pytest.mark.parametrize("harness,label", [("codex", "codex"), ("claude", "mainline"), ("agy", "mainline")])
def test_correct_host_and_whole_selected_resources(inputs, harness, label):
    project, repo = inputs
    result = prepare_context(project, "owner", harness, "Continue the task", ["project-agent"], repo=repo)
    skill = Path(result["skill_files"][0])
    assert skill.is_absolute() and skill.read_text().startswith(label)
    assert (skill.parent / "scripts/run.py").is_file()
    assert (skill.parent / "references/guide.md").read_text() == "guide"
    assert (skill.parent / "assets/icon.svg").is_file()
    assert (skill.parent.parent / "shared-references/contract.md").read_text() == label + " contract"
    assert not (skill.parent.parent / "unselected").exists()
    packet = Path(result["packet"])
    assert packet.parent.name == "0001"
    assert str(packet) in result["prompt"]
    assert str(repo) in packet.read_text()
    assert "paused Goal remains paused" in packet.read_text()


def test_original_state_referenced_and_native_installations_untouched(inputs):
    project, repo = inputs
    recovery = project / "state/current.md"
    recovery.parent.mkdir()
    recovery.write_text("live state, not a snapshot")
    native = project / ".agents/skills/local/SKILL.md"
    native.parent.mkdir(parents=True)
    native.write_text("native customized skill")
    before = {str(p.relative_to(project)): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    result = prepare_context(project, "writer", "codex", "Draft", ["project-agent"],
                             recovery=["state/current.md"], repo=repo, write_scope=["drafts"])
    packet = Path(result["packet"]).read_text()
    assert set(result["project_files"]) == {str(project / "AGENTS.md"), str(recovery)}
    assert str(recovery) in packet and str(project / "drafts") in packet
    assert "live state, not a snapshot" not in packet
    for name, content in before.items():
        actual = (project / name).read_bytes()
        assert actual.startswith(content) if name == "AGENTS.md" else actual == content
    assert not (project / ".claude").exists()


def test_new_context_observes_changed_sources_and_keeps_previous_copy(inputs):
    project, repo = inputs
    first = prepare_context(project, "owner", "codex", "first", ["project-agent"], repo=repo)
    source = repo / "skills/skills-codex/project-agent/SKILL.md"
    source.write_text("new source")
    (project / "AGENTS.md").write_text("new project instructions")
    second = prepare_context(project, "owner", "codex", "second", ["project-agent"], repo=repo)
    assert Path(second["packet"]).parent.name == "0002"
    assert Path(first["skill_files"][0]).read_text().startswith("codex")
    assert Path(second["skill_files"][0]).read_text() == "new source"
    assert "new project instructions" not in Path(second["packet"]).read_text()
    assert Path(second["project_files"][0]).read_text().startswith("new project instructions")


@pytest.mark.parametrize("override", [
    {"skills": ["missing"]}, {"skills": ["../project-agent"]},
    {"role": "../outside"}, {"recovery": ["../outside.md"]},
    {"recovery": ["missing.md"]}, {"write_scope": ["../outside"]},
    {"harness": "unknown"},
])
def test_invalid_inputs_fail_before_creating_context(inputs, override):
    project, repo = inputs
    args = dict(project=project, role="owner", harness="codex", task="task", skills=["project-agent"], repo=repo)
    args.update(override)
    with pytest.raises(ValueError):
        prepare_context(**args)
    assert not (project / ".aris").exists()


def test_codex_never_falls_back_to_mainline(inputs):
    project, repo = inputs
    (repo / "skills/skills-codex/project-agent/SKILL.md").unlink()
    with pytest.raises(ValueError, match="missing for codex"):
        prepare_context(project, "owner", "codex", "task", ["project-agent"], repo=repo)


@pytest.mark.parametrize("location", ["project", "recovery", "resource", "destination"])
def test_symlink_cannot_expand_read_or_write_scope(inputs, tmp_path, location):
    project, repo = inputs
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "private.md"
    secret.write_text("outside content")
    kwargs = {}
    if location == "project":
        (project / "CLAUDE.md").symlink_to(secret)
    elif location == "recovery":
        (project / "recovery.md").symlink_to(secret)
        kwargs["recovery"] = ["recovery.md"]
    elif location == "resource":
        (repo / "skills/skills-codex/project-agent/references/link.md").symlink_to(secret)
    else:
        (project / ".aris").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes allowed root"):
        prepare_context(project, "owner", "codex", "task", ["project-agent"], repo=repo, **kwargs)
    assert list(outside.iterdir()) == [secret]


def test_absolute_recovery_inside_project_and_duplicate_skill_are_supported(inputs):
    project, repo = inputs
    result = prepare_context(project, "owner", "codex", "task", ["project-agent", "project-agent"],
                             recovery=[str(project / "AGENTS.md")], repo=repo)
    assert len(result["skill_files"]) == len(result["project_files"]) == 1


@pytest.mark.parametrize("harness,native", [("codex", ".agents/skills"), ("claude", ".claude/skills")])
def test_same_name_native_customization_is_actually_selected(inputs, harness, native):
    project, repo = inputs
    source = project / native / "project-agent"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("actual custom coordination")
    (source / "references").mkdir()
    (source / "references/custom.md").write_text("custom resource")
    (source.parent / "shared-references").mkdir()
    (source.parent / "shared-references/local.md").write_text("custom contract")
    result = prepare_context(project, "owner", harness, "task", [], repo=repo)
    copied = Path(result["skill_index"]["project-agent"])
    assert copied.read_text() == "actual custom coordination"
    assert (copied.parent / "references/custom.md").read_text() == "custom resource"
    assert (copied.parent.parent / "shared-references/local.md").read_text() == "custom contract"
    assert str(source) in Path(result["packet"]).read_text()
    assert (source / "SKILL.md").read_text() == "actual custom coordination"


def test_global_precedence_and_installer_directory_symlink(inputs):
    project, repo = inputs
    global_root = Path.home() / ".codex/skills"
    global_root.mkdir(parents=True)
    fallback = Path.home() / ".agents/skills/project-agent"
    fallback.mkdir(parents=True)
    (fallback / "SKILL.md").write_text("lower-priority global")
    external = repo / "installed-custom"
    external.mkdir()
    (external / "SKILL.md").write_text("symlinked installed custom")
    (global_root / "project-agent").symlink_to(external, target_is_directory=True)
    result = prepare_context(project, "owner", "codex", "task", [], repo=repo)
    assert Path(result["skill_index"]["project-agent"]).read_text() == "symlinked installed custom"
    packet = Path(result["packet"]).read_text()
    assert str(external) in packet and str(global_root / "project-agent") in packet


def test_agy_ignores_codex_and_claude_native_collisions(inputs):
    project, repo = inputs
    for relative in (".agents/skills/project-agent", ".claude/skills/project-agent"):
        source = project / relative
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("wrong harness")
    result = prepare_context(project, "owner", "agy", "task", [], repo=repo)
    assert Path(result["skill_index"]["project-agent"]).read_text().startswith("mainline")
    agy = Path.home() / ".gemini/config/skills/project-agent"
    agy.mkdir(parents=True)
    (agy / "SKILL.md").write_text("AGY explicit native")
    result = prepare_context(project, "owner", "agy", "task", [], repo=repo)
    assert Path(result["skill_index"]["project-agent"]).read_text() == "AGY explicit native"


def test_catalog_closure_and_named_index_are_reachable(inputs):
    project, repo = inputs
    (repo / "tools").mkdir()
    (repo / "tools/skill-groups.tsv").write_text(
        "skill\tpaper-writing\tpaper\tpaper-write,paper-compile\tworkflow\n"
        "skill\tpaper-write\tpaper\tpaper-plan\tchild\n"
        "skill\tpaper-plan\tpaper\t-\tleaf\n"
        "skill\tpaper-compile\tpaper\tpaper-plan\tshared leaf\n"
    )
    for name in ("paper-writing", "paper-write", "paper-compile", "paper-plan"):
        source = repo / "skills/skills-codex" / name
        source.mkdir()
        (source / "SKILL.md").write_text(name)
    first = prepare_context(project, "owner", "codex", "task", ["paper-writing"], repo=repo)
    assert set(first["skill_index"]) == {"project-agent", "paper-writing", "paper-write", "paper-compile", "paper-plan"}
    packet = Path(first["packet"]).read_text()
    for name, copied in first["skill_index"].items():
        assert f"{name}: `{copied}`" in packet
        assert Path(copied).is_file()
    assert str(repo / "tools") in packet
    if context_module.WINDOWS:
        assert "$env:ARIS_REPO" in packet and "in that same shell" in packet
    else:
        assert "set ARIS_REPO=" in packet and "explicitly in that same invocation" in packet
    assert "Do not assume a reused or adopted native process inherited a launcher environment" in packet
    source = repo / "skills/skills-codex/paper-write/SKILL.md"
    source.write_text("changed child")
    second = prepare_context(project, "owner", "codex", "task", ["paper-writing"], repo=repo)
    assert Path(first["skill_index"]["paper-write"]).read_text() == "paper-write"
    assert Path(second["skill_index"]["paper-write"]).read_text() == "changed child"


def test_missing_catalog_dependency_fails_before_copy(inputs):
    project, repo = inputs
    (repo / "tools").mkdir()
    (repo / "tools/skill-groups.tsv").write_text("skill\tproject-agent\tmeta\tmissing-child\tfixture\n")
    with pytest.raises(ValueError, match="missing-child"):
        prepare_context(project, "owner", "codex", "task", [], repo=repo)
    assert not (project / ".aris").exists()


def _catalog_fixture(repo):
    (repo / "tools").mkdir(exist_ok=True)
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "tools/skill-groups.tsv").write_text(
        "group\tlit\tLiterature\tFind and read papers\n"
        "group\texperiments\tExperiments\tImplement and evaluate methods\n"
        "group\tpaper\tWriting\tDraft, illustrate and compile papers\n"
        "skill\tproject-agent\tmeta\t-\tProject coordination\n"
        "skill\tpaper-writing\tpaper\tpaper-write\tWriting workflow\n"
        "skill\tpaper-write\tpaper\t-\tDraft paper sections\n"
    )
    (repo / "docs/SKILLS_CATALOG.md").write_text(
        "# Canonical fixture catalog\n\n"
        "[project-agent](../skills/project-agent/SKILL.md)\n"
        "[paper-writing](../skills/paper-writing/SKILL.md)\n"
        "[Codex mirror](../skills/skills-codex/)\n"
        "[contract](../skills/shared-references/contract.md)\n"
    )
    for host in (repo / "skills", repo / "skills/skills-codex"):
        for name in ("paper-writing", "paper-write"):
            source = host / name
            source.mkdir()
            (source / "SKILL.md").write_text(f"FULL_BODY_{name}")


@pytest.mark.parametrize("role,harness,scope,label", [
    ("main", "codex", "owner-notes", "codex"),
    ("engineer", "claude", "implementation", "mainline"),
    ("writer", "agy", "manuscript", "mainline"),
])
def test_every_role_has_local_navigation_catalog_recovery_and_scope(inputs, role, harness, scope, label):
    import re
    project, repo = inputs
    _catalog_fixture(repo)
    result = prepare_context(project, role, harness, "Read navigation then wait", ["project-agent"],
                             repo=repo, write_scope=[scope])
    packet = Path(result["packet"])
    local_root = packet.parent
    navigation = Path(result["navigation"])
    text = navigation.read_text()
    for path in (navigation, Path(result["role_file"]), Path(result["recovery_file"]),
                 *map(Path, result["catalog_files"])):
        assert path.is_relative_to(local_root) and path.is_file()
    assert "**pipeline**" in text and "**workflow**" in text and "**skill**" in text
    assert "Literature" in text and "Experiments" in text and "Writing" in text
    if context_module.WINDOWS:
        assert f"'--role' '{role}' '--skill' 'SKILL_NAME'" in text
        assert "```powershell" in text and "Do not paste `&`/`$env:` syntax into Bash" in text
    else:
        assert f"--role {role} --skill SKILL_NAME" in text
    assert "-m superaris context" in text
    assert "file-only tools" in text and "hand the named skill request to the main owner" in text
    assert str(navigation) in packet.read_text()
    assert str(Path(result["recovery_file"])) in packet.read_text()
    role_text = Path(result["role_file"]).read_text()
    assert str(project / scope) in role_text and "Read navigation then wait" in role_text
    assert "Roles and models are configured separately" in role_text
    assert Path(result["skill_index"]["project-agent"]).read_text().startswith(label)
    assert Path(result["catalog_files"][0]).read_bytes() == (repo / "tools/skill-groups.tsv").read_bytes()
    adapted = Path(result["catalog_files"][1])
    for target in re.findall(r"\]\(([^)]+)\)", adapted.read_text()):
        assert (adapted.parent / target.split("#", 1)[0]).resolve().is_file()
    assert "FULL_BODY_paper-writing" not in text + adapted.read_text()
    assert not (local_root / "skills/paper-writing").exists()
    assert "not establish delivery or actual reading" in (local_root.parent / "LATEST_PREPARED.md").read_text()


def test_blank_project_gets_stable_recovery_and_selected_native_pointer(inputs):
    project, repo = inputs
    (project / "AGENTS.md").unlink()
    result = prepare_context(project, "main", "codex", "Await a project goal", [], repo=repo)
    pointer = Path(result["recovery_pointer"])
    assert pointer == project / ".aris/workbench/RECOVERY.md"
    assert "project goal is not yet specified" in pointer.read_text()
    assert "launch.json" in pointer.read_text()
    assert "LATEST_PREPARED.md" in pointer.read_text()
    assert (project / "AGENTS.md").is_file()
    assert not (project / "CLAUDE.md").exists()
    assert not (project / "GEMINI.md").exists()
    assert not (project / ".agents").exists()
    assert not (project / ".aris/workbench/launch.json").exists()
    # The stable pointer can contain user notes; preparing another role preserves it.
    pointer.write_text(pointer.read_text() + "\nUser-supplied recovery note.\n")
    before = pointer.read_bytes()
    writer = prepare_context(project, "writer", "agy", "Wait for facts", [], repo=repo)
    assert writer["recovery_pointer"] == str(pointer)
    assert pointer.read_bytes() == before


def test_on_demand_selection_uses_original_resolver_and_keeps_prior_packet(inputs):
    project, repo = inputs
    _catalog_fixture(repo)
    original_state = project / "NEXT_SESSION.md"
    original_state.write_text("The existing task owner and decisions remain authoritative.")
    before = {name: (project / name).read_bytes() for name in ("AGENTS.md", "NEXT_SESSION.md")}
    custom = project / ".agents/skills/paper-write"
    custom.mkdir(parents=True)
    (custom / "SKILL.md").write_text("CUSTOM_PAPER_WRITE")
    initial = prepare_context(project, "writer", "codex", "Draft the authorized section", ["project-agent"],
                              recovery=["NEXT_SESSION.md"], repo=repo, write_scope=["manuscript"])
    prior_packet = Path(initial["packet"]).read_bytes()
    prepared = prepare_context(project, "writer", "codex", "Draft the authorized section", ["paper-writing"],
                               recovery=["NEXT_SESSION.md"], repo=repo, write_scope=["manuscript"])
    assert set(prepared["skill_index"]) == {"project-agent", "paper-writing", "paper-write"}
    assert Path(prepared["skill_index"]["paper-write"]).read_text() == "CUSTOM_PAPER_WRITE"
    assert str(project / "manuscript") in Path(prepared["role_file"]).read_text()
    assert str(original_state) in Path(prepared["recovery_file"]).read_text()
    assert Path(initial["packet"]).read_bytes() == prior_packet
    latest = Path(prepared["packet"]).parent.parent / "LATEST_PREPARED.md"
    assert prepared["packet"] in latest.read_text()
    for name, content in before.items():
        actual = (project / name).read_bytes()
        assert actual.startswith(content) if name == "AGENTS.md" else actual == content


@pytest.mark.parametrize("harness,filename", [("codex", "AGENTS.md"), ("claude", "CLAUDE.md"), ("agy", "GEMINI.md")])
def test_native_startup_entry_preserves_user_text_idempotently(inputs, harness, filename):
    project, repo = inputs
    (project / "AGENTS.md").unlink()
    entry = project / filename
    prefix = b"# User project instructions\r\nKeep the original owner and routes.\r\n<!-- user custom block -->\r\n"
    entry.write_bytes(prefix)
    first = prepare_context(project, "writer", harness, "Read then wait", [], repo=repo)
    initial = entry.read_bytes()
    assert initial.startswith(prefix)
    assert initial.count(context_module._ENTRY_BEGIN) == initial.count(context_module._ENTRY_END) == 1
    assert first["startup_files"] == [str(entry)]
    assert str(entry) in Path(first["packet"]).read_text()
    assert ".aris/workbench/RECOVERY.md" in initial.decode()
    assert Path(first["recovery_pointer"]).is_file()
    assert "do not infer a role from this shared entry" in initial.decode()
    suffix = b"\nUser addition AFTER managed block.\n"
    entry.write_bytes(initial + suffix)
    second = prepare_context(project, "engineer", harness, "Still wait", [], repo=repo)
    assert entry.read_bytes() == initial + suffix
    assert entry.read_bytes().count(context_module._ENTRY_BEGIN) == 1
    assert second["startup_files"] == first["startup_files"]
    for other in {"AGENTS.md", "CLAUDE.md", "GEMINI.md"} - {filename}:
        assert not (project / other).exists()


@pytest.mark.parametrize("harness,filename", [("codex", "AGENTS.md"), ("claude", "CLAUDE.md"), ("agy", "GEMINI.md")])
def test_blank_native_entry_is_only_created_for_selected_host(inputs, harness, filename):
    project, repo = inputs
    (project / "AGENTS.md").unlink()
    context = prepare_context(project, "writer", harness, "Read navigation and wait", [], repo=repo)
    assert (project / filename).is_file()
    assert context["startup_entry"] == str(project / filename)
    assert context["startup_source"] in context["project_files"]
    for other in {"AGENTS.md", "CLAUDE.md", "GEMINI.md"} - {filename}:
        assert not (project / other).exists()


def test_native_startup_symlink_stays_in_project_and_preserves_link(inputs):
    project, repo = inputs
    actual = project / "instructions/original.md"
    actual.parent.mkdir()
    actual.write_bytes(b"Original project instruction bytes.\n")
    (project / "AGENTS.md").unlink()
    (project / "AGENTS.md").symlink_to(actual)
    context = prepare_context(project, "engineer", "codex", "Wait", [], repo=repo)
    assert (project / "AGENTS.md").is_symlink()
    assert context["startup_entry"] == str(project / "AGENTS.md")
    assert context["startup_source"] == str(actual)
    assert actual.read_bytes().startswith(b"Original project instruction bytes.\n")
    assert actual.read_bytes().count(context_module._ENTRY_BEGIN) == 1


def test_codex_uses_nonempty_native_override_without_changing_agents(inputs):
    project, repo = inputs
    original_agents = (project / "AGENTS.md").read_bytes()
    override = project / "AGENTS.override.md"
    original_override = b"User preferred native override.\n"
    override.write_bytes(original_override)
    first = prepare_context(project, "engineer", "codex", "Wait", [], repo=repo)
    assert first["startup_files"] == [str(override)]
    assert first["startup_source"] == str(override)
    assert (project / "AGENTS.md").read_bytes() == original_agents
    assert override.read_bytes().startswith(original_override)
    assert str(override) in first["project_files"]
    before = override.read_bytes()
    prepare_context(project, "writer", "codex", "Still wait", [], repo=repo)
    assert override.read_bytes() == before
    assert override.read_bytes().count(context_module._ENTRY_BEGIN) == 1


def test_codex_empty_override_leaves_it_untouched_and_uses_agents(inputs):
    project, repo = inputs
    override = project / "AGENTS.override.md"
    override.write_bytes(b"")
    result = prepare_context(project, "main", "codex", "Wait", [], repo=repo)
    assert result["startup_files"] == [str(project / "AGENTS.md")]
    assert override.read_bytes() == b""
    assert (project / "AGENTS.md").read_bytes().count(context_module._ENTRY_BEGIN) == 1


def test_bound_old_packet_still_discovers_latest_navigation_without_task_reassignment(inputs):
    project, repo = inputs
    first = prepare_context(project, "writer", "agy", "Existing authorized task", [], repo=repo)
    recovery = Path(first["recovery_pointer"])
    before = recovery.read_bytes().replace(context_module._RECOVERY_BINDING.encode(), context_module._LEGACY_RECOVERY_BINDING.encode())
    user_note = b"\nUser recovery note remains authoritative.\n"
    recovery.write_bytes(before + user_note)
    binding = project / ".aris/workbench/launch.json"
    binding.write_text('{"roles":{"writer":{"context":{"packet":"old-packet"},"delivery":{"phase":"unknown"}}}}')
    original_binding = binding.read_bytes()
    latest = prepare_context(project, "writer", "agy", "Prepared resources only", [], repo=repo)
    assert binding.read_bytes() == original_binding
    assert recovery.read_bytes() == before.replace(context_module._LEGACY_RECOVERY_BINDING.encode(), context_module._RECOVERY_BINDING.encode()) + user_note
    assert "Always inspect context/<actual-role>/LATEST_PREPARED.md" in recovery.read_text()
    assert "binding still points to an older packet" in recovery.read_text()
    assert "preparation never replaces their task authority" in recovery.read_text()
    pointer = Path(latest["packet"]).parent.parent / "LATEST_PREPARED.md"
    assert latest["navigation"] in pointer.read_text()
