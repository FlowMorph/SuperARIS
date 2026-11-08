"""Prepare isolated, host-correct skill context for a project role.

The launcher serializes calls with its launch lock. Context copies are disposable;
project state remains authoritative at its original paths.
"""

from pathlib import Path
import os
import re
from .platform import WINDOWS, command_line
import shutil

from .dependencies import productcommand, resolve_aris_repo


_PROJECT_FILES = (
    "AGENTS.override.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md", "NEXT_SESSION.md", "HANDOFF.md",
    "RESEARCH_BRIEF.md",
)
_STARTUP_FILES = {"codex": "AGENTS.md", "claude": "CLAUDE.md", "agy": "GEMINI.md"}
_ENTRY_BEGIN = b"<!-- ARIS workbench recovery: begin -->"
_ENTRY_END = b"<!-- ARIS workbench recovery: end -->"
_LEGACY_RECOVERY_BINDING = (
    "Current role/session transport pointers are in launch.json beside this file. Read the current role's "
    "context.packet and its navigation, role scope and selected-skill index. If no launch binding exists, "
    "context/<role>/LATEST_PREPARED.md locates the latest prepared context. A prepared packet is not proof "
    "of delivery, actual reading or accepted work. Re-read originals before continuing.\n\n"
)
_RECOVERY_BINDING = (
    "Current role/session transport pointers are in launch.json beside this file. Recover your actual role "
    "and active task from that binding and the original owner handoff. Always inspect "
    "context/<actual-role>/LATEST_PREPARED.md for the latest prepared navigation and skill resources, "
    "including when the binding still points to an older packet. Latest preparation is not an automatic "
    "task assignment or proof of delivery, actual reading or accepted work. Reconcile it with the current "
    "binding and original handoff before acting; preparation never replaces their task authority. "
    "Re-read originals before continuing.\n\n"
)


def _name(value: str, kind: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise ValueError(f"Invalid {kind}: {value!r}; use a single directory name")
    return value


def _within(path: Path, root: Path, kind: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{kind} escapes allowed root {root}: {path}")
    return resolved


def _check_tree(source: Path) -> None:
    # Copy bundled resources, never follow a link into another skill or outside
    # the source tree. Ordinary relative references retain their copied layout.
    for entry in source.rglob("*"):
        if entry.is_symlink():
            target = _within(entry, source, "Skill resource")
            if not target.exists() or target.is_dir():
                raise ValueError(f"Unsupported skill resource symlink: {entry}")


def _dependency_closure(repo: Path, skills: list[str]) -> list[str]:
    """Use the installer's catalog, rather than maintaining a second graph."""
    catalog = repo / "tools/skill-groups.tsv"
    requires = {}
    if catalog.is_file():
        for line in catalog.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) >= 4 and fields[0] == "skill":
                requires[fields[1]] = [] if fields[3] == "-" else fields[3].split(",")
    selected = list(dict.fromkeys(["project-agent", *(_name(s, "skill") for s in skills)]))
    for skill in selected:
        for dependency in requires.get(skill, []):
            dependency = _name(dependency, "catalog dependency")
            if dependency not in selected:
                selected.append(dependency)
    return selected


def _native_roots(project: Path, harness: str) -> list[Path]:
    home = Path.home()
    if harness == "codex":
        return [project / ".agents/skills", home / ".codex/skills", home / ".agents/skills"]
    if harness == "claude":
        return [project / ".claude/skills", home / ".claude/skills"]
    # AGY must never mistake a Codex .agents mirror for its own native source.
    return [home / ".gemini/config/skills"]


def _startup_entry(project: Path, harness: str) -> tuple[Path, Path]:
    """Wire the native project instruction convention without replacing user text."""
    entry = project / _STARTUP_FILES[harness]
    if harness == "codex":
        override = project / "AGENTS.override.md"
        if override.exists() or override.is_symlink():
            actual_override = _within(override, project, "Native startup override")
            if actual_override.is_file() and actual_override.stat().st_size:
                entry = override
    source = _within(entry, project, "Native startup entry")
    original = source.read_bytes() if source.exists() else b""
    block = _ENTRY_BEGIN + (
        "\n## ARIS project recovery\n\n"
        "At startup or after compact/restart, read the project recovery pointer "
        "[.aris/workbench/RECOVERY.md](.aris/workbench/RECOVERY.md) from the project root. "
        "Recover your current role, task, original owner and authorization from the original project instructions "
        "and current .aris/workbench/launch.json binding; do not infer a role from this shared entry. "
        "Then read that role's navigation, scope, current project state and required SKILL.md/resources before authorized action. "
        "LATEST_PREPARED.md locates preparation, not an active or delivered task. Compare it with the current owner "
        "and binding before using it. Preserve original goals, paused state, budgets, model/MCP routes, reviewer "
        "freshness and merge authorization.\n"
    ).encode("utf-8") + _ENTRY_END
    count_begin, count_end = original.count(_ENTRY_BEGIN), original.count(_ENTRY_END)
    if count_begin != count_end or count_begin > 1:
        raise ValueError(f"Native startup entry has ambiguous ARIS managed markers: {entry}")
    if count_begin:
        pattern = re.escape(_ENTRY_BEGIN) + b".*?" + re.escape(_ENTRY_END)
        updated, replaced = re.subn(pattern, lambda match: block, original, count=1, flags=re.DOTALL)
        if replaced != 1:
            raise ValueError(f"Native startup entry has misplaced ARIS managed markers: {entry}")
    else:
        updated = original + (b"\n\n" if original else b"") + block + b"\n"
    if updated != original:
        source.write_bytes(updated)
    return entry, source


def _navigation(project, role, harness, task, scopes, repo, run, skill_index, originals):
    """Project-local navigation snapshots, without installing native instructions."""
    catalog_dir = run / "catalog"
    catalog_dir.mkdir()
    catalog_source = repo / "tools/skill-groups.tsv"
    catalog = catalog_dir / "skill-groups.tsv"
    if catalog_source.is_file():
        shutil.copyfile(catalog_source, catalog)
    else:
        catalog.write_text("# Canonical catalog unavailable in this checkout; only the selected index is available.\n", encoding="utf-8")
    groups = []
    for line in catalog.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) >= 4 and fields[0] == "group":
            groups.append(f"- **{fields[2]}**: {fields[3]}")
    stages = "\n".join(groups) or "Consult the available selected-skill index; this checkout has no stage catalog."
    documentation = catalog_dir / "SKILLS_CATALOG.md"
    docs_source = repo / "docs/SKILLS_CATALOG.md"
    docs_text = docs_source.read_text(encoding="utf-8") if docs_source.is_file() else "# Selected skills\n\nSee the navigation and packet index.\n"

    def local_link(match):
        target = match.group(1)
        if target.startswith(("https://", "http://", "#")):
            return match.group(0)
        skill_match = re.fullmatch(r"\.\./skills/([^/]+)/SKILL\.md", target)
        if skill_match and skill_match.group(1) in skill_index:
            target = os.path.relpath(skill_index[skill_match.group(1)], catalog_dir)
        elif target.startswith("../skills/shared-references/"):
            shared_file = run / "skills/shared-references" / target.rsplit("/", 1)[1]
            target = os.path.relpath(shared_file, catalog_dir) if shared_file.is_file() else "../navigation.md#capabilities-and-tools"
        else:
            target = "../navigation.md#on-demand-skills" if skill_match else "../navigation.md#capabilities-and-tools"
        return f"]({target})"

    adapted = re.sub(r"\]\(([^)]+)\)", local_link, docs_text)
    documentation.write_text(
        f"> Navigation snapshot from `{docs_source}`. Selected skill links resolve to this role's copies; "
        "other skill links lead to on-demand preparation. Descriptions of external tools do not establish their availability.\n\n" + adapted,
        encoding="utf-8",
    )
    recovery_pointer = _within(project / ".aris/workbench/RECOVERY.md", project, "Recovery pointer")
    if not recovery_pointer.exists():
        recovery_pointer.write_text(
            "# ARIS project recovery\n\n"
            "Project goal: use the original project instructions or the user's current goal. "
            "If neither specifies a goal, the project goal is not yet specified; do not start a research pipeline.\n\n"
            "After compact or restart, re-read current AGENTS.override.md, AGENTS.md, CLAUDE.md, GEMINI.md, NEXT_SESSION.md, "
            "HANDOFF.md and RESEARCH_BRIEF.md when present, plus their original task/wiki/memory links. "
            "Those originals own goals, decisions, phase, owners, next steps and acceptance; update them through their existing owner.\n\n"
            + _RECOVERY_BINDING +
            "This is a recovery pointer, not a second task ledger. Preserve paused Goals, original model/MCP routes, "
            "fresh reviewer requirements, budgets, ownership and merge authorization. The selected harness's native "
            "project instruction convention points here through a small managed block. File wiring does not prove "
            "that a running session has re-read the entry or navigation; use its actual read evidence separately.\n",
            encoding="utf-8",
        )
    if not recovery_pointer.is_file():
        raise ValueError(f"Recovery pointer is not a file: {recovery_pointer}")
    previous_recovery = recovery_pointer.read_bytes()
    refreshed_recovery = previous_recovery.replace(_LEGACY_RECOVERY_BINDING.encode(), _RECOVERY_BINDING.encode(), 1)
    if refreshed_recovery != previous_recovery:
        # Migrate only the exact generated legacy paragraph; user notes and all
        # other original text remain byte-for-byte intact.
        recovery_pointer.write_bytes(refreshed_recovery)
    local_recovery = run / "recovery.md"
    originals_text = "\n".join(f"- `{path}`" for path in originals) or "- No existing project instruction/state files found. Read the user's task below; no broader project goal is inferred."
    local_recovery.write_text(
        f"# Recover this role\n\nRead the stable project recovery pointer `{recovery_pointer}`, then current originals:\n\n{originals_text}\n\n"
        f"This prepared role task is recorded in `{run / 'packet.md'}`; selected skills and source provenance are there too. "
        "Read the current binding/original handoff before resuming; newer user decisions and owner assignments take precedence. "
        "A previous packet remains an immutable preparation snapshot.\n",
        encoding="utf-8",
    )
    responsibility = {
        "main": "Organize the project goal and authorized next steps, assign ownership, collect real artifacts and apply the original acceptance gates.",
        "engineer": "Implement and run authorized experiments or checks; produce artifacts, reproducible evidence and factual handoffs for the owner.",
        "writer": "Write substantial prose and organize explanations within the owner's established facts, formulas and citation boundaries; hand technical claims back for acceptance.",
        "figures": "Prepare requested figures using the original evidence and visual contracts; preserve editable sources and verify the exported artifact.",
    }.get(role, "Use the task and original owner handoff to determine your role; request clarification if the responsibility is not specified.")
    role_file = run / "role.md"
    scope_text = "\n".join(f"- `{scope}`" for scope in scopes) or "- No write scope supplied; use existing authorization before editing."
    role_file.write_text(
        f"# Role: {role}\n\n{responsibility}\n\nHarness: {harness}. Roles and models are configured separately; this role name does not select a vendor. "
        "The specific task and original owner instructions override these default responsibility descriptions.\n\n"
        f"## Prepared context task\n\n{task}\n\n"
        "This is a preparation snapshot; the original owner and current binding determine your current assignment. "
        "A candidate task here does not replace that assignment.\n\n"
        f"## Authorized write scope\n\n{scope_text}\n\n"
        "Keep other writers' scopes exclusive. A temporary MCP worker receives only its bounded task inputs; "
        "an independent reviewer retains its required fresh context and isolation.\n",
        encoding="utf-8",
    )
    command = command_line([*productcommand(), "context", str(project), "--role", role, "--skill", "SKILL_NAME"])
    navigation = run / "navigation.md"
    local_index = "\n".join(f"- {name}: `{path}`" for name, path in skill_index.items())
    navigation.write_text(
        "# ARIS navigation for every role\n\n"
        "ARIS provides research workflows, project memory and evidence-based acceptance. "
        "Use a **pipeline** for an authorized complete research lifecycle, a **workflow** for one connected stage, "
        "or an individual **skill** for a bounded task. The main owner can delegate any of those granularities; "
        "opening this navigation starts none of them.\n\n"
        f"First read `{role_file}` for your responsibility, scoped task and write boundaries, and `{local_recovery}` "
        "for the project goal/current-state originals. Read the exact required SKILL.md and referenced resources before executing its workflow.\n\n"
        f"## Stages and capabilities\n\n{stages}\n\n"
        f"The local catalog `{documentation}` describes skills and external dependencies. The verbatim canonical "
        f"selection/dependency catalog is `{catalog}` (source `{catalog_source}`). These are navigation and descriptions, not all skill bodies.\n\n"
        f"## Skills prepared for this role\n\n{local_index}\n\n"
        "When a workflow invokes a named child skill, use this exact index; native slash/menu discovery is optional. "
        "Only the requested skills and default dependency closure have been copied.\n\n"
        "## On-demand skills\n\n"
        "Choose the skill by name from the local catalog. The command-capable project owner can prepare it through "
        "the existing source resolver, host customization precedence and catalog dependency closure:\n\n"
        f"```{'powershell' if WINDOWS else 'sh'}\n{command}\n```\n\n"
        + ("These examples execute in PowerShell. A CLI launched from PowerShell may still expose only a Bash tool; "
           "invoke PowerShell explicitly or use the equivalent syntax for the actual shell. Do not paste `&`/`$env:` syntax into Bash.\n\n" if WINDOWS else "")
        +
        "Replace SKILL_NAME with the chosen catalog name. This preparation preserves the role's current task, recovery "
        "and scopes by default and returns a new packet; it does not send native input or execute the skill. "
        "Read the returned packet/index and then the actual skill before doing authorized work. If your read domain "
        "or file-only tools cannot execute/access this repository command, hand the named skill request to the main "
        "owner through the existing task channel and read the prepared project-local packet when returned. "
        "Users need not reconstruct command parameters or install another skill set.\n\n"
        "## Capabilities and tools\n\n"
        "Catalog entries describe possible tools, not verified accounts, MCP services, GPUs or reviewer availability. "
        "Check the selected skill's actual requirements and use the existing owner for unsupported execution. "
        + ("For PowerShell helpers, set `$env:ARIS_REPO = '" + str(repo).replace("'", "''") + "'` and invoke Python helpers with `&` and the installed Python interpreter in that same shell. " if WINDOWS else "Set the packet's ARIS_REPO explicitly in the same helper invocation. ") + "Preserve original MCP routes, reviewer "
        "freshness, budgets, paused Goals and publication/merge permissions. Local files or submitted messages do not "
        "prove native loading, actual reading or permanent model memory. After compact/restart, re-read recovery, "
        "the current role packet and its required skills.\n",
        encoding="utf-8",
    )
    latest = run.parent / "LATEST_PREPARED.md"
    if latest.is_symlink():
        raise ValueError(f"Prepared context pointer must not be a symlink: {latest}")
    latest.write_text(
        f"# Latest prepared {role} context\n\nPacket: `{run / 'packet.md'}`\n\nNavigation: `{navigation}`\n\n"
        "Preparation does not establish delivery or actual reading. Compare the current launch.json binding and original handoff before resuming.\n",
        encoding="utf-8",
    )
    return {"navigation": str(navigation), "catalog_files": [str(catalog), str(documentation)],
            "recovery_pointer": str(recovery_pointer), "role_file": str(role_file), "recovery_file": str(local_recovery)}


def prepare_context(
    project: Path,
    role: str,
    harness: str,
    task: str,
    skills: list[str],
    recovery: list[str] | None = None,
    repo: Path | None = None,
    write_scope: list[str] | None = None,
) -> dict:
    """Copy selected skills and write a packet pointing to actual project state.

    Recovery paths are project-relative or absolute within the project. Explicit
    missing inputs are errors. No Git repository or native skill installation is
    required. Source validation precedes allocation of a sequential run folder.
    """
    project = Path(project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")
    role = _name(role, "role")
    if harness not in {"codex", "claude", "agy"}:
        raise ValueError(f"Unsupported harness: {harness!r}")
    repo = Path(repo).expanduser().resolve() if repo is not None else resolve_aris_repo()
    host_root = repo / "skills" / "skills-codex" if harness == "codex" else repo / "skills"
    host_root = _within(host_root, repo, "Skill host directory")
    selected = _dependency_closure(repo, skills)
    roots = _native_roots(project, harness)
    sources = []
    for skill in selected:
        candidates = [root / skill for root in roots]
        if skill == "project-agent":
            resource_host = "codex" if harness == "codex" else "claude"
            candidates.append(Path(__file__).resolve().parent / "resources" / resource_host / skill)
        candidates.append(host_root / skill)
        chosen = next((candidate for candidate in candidates if candidate.exists() or candidate.is_symlink()), candidates[-1])
        # Installers legitimately symlink a whole skill to an ARIS checkout.
        # Resolve that source; _check_tree still constrains bundled asset links.
        source = chosen.resolve()
        if not source.is_dir() or not (source / "SKILL.md").is_file():
            raise ValueError(f"Requested skill {skill!r} is missing for {harness}: {source / 'SKILL.md'}")
        _check_tree(source)
        adjacent_shared = source.parent / "shared-references"
        installed_shared = chosen.parent / "shared-references"
        source_shared = next((p.resolve() for p in (installed_shared, adjacent_shared) if p.is_dir()), host_root / "shared-references")
        if not source_shared.is_dir():
            raise ValueError(f"Shared references are missing for {harness}: {source_shared}")
        _check_tree(source_shared)
        sources.append((skill, source, chosen, source_shared))
    shared = _within(host_root / "shared-references", host_root, "Shared references")
    if sources and not shared.is_dir():
        raise ValueError(f"Shared references are missing for {harness}: {shared}")
    if sources:
        _check_tree(shared)
    parent_shared = repo / "skills/shared-references" if harness == "codex" else shared
    parent_shared = _within(parent_shared, repo, "Parent shared references")
    if not parent_shared.is_dir():
        raise ValueError(f"Parent shared references are missing: {parent_shared}")
    _check_tree(parent_shared)

    originals = []
    recovery_files = []
    for filename in _PROJECT_FILES:
        candidate = project / filename
        if candidate.exists() or candidate.is_symlink():
            resolved = _within(candidate, project, "Project file")
            if not resolved.is_file():
                raise ValueError(f"Project input is not a file: {candidate}")
            originals.append(resolved)
    for filename in recovery or []:
        candidate = Path(filename).expanduser()
        # Reject lexical traversal too, so a typo cannot be normalized away.
        if ".." in candidate.parts:
            raise ValueError(f"Recovery path traversal is not allowed: {filename}")
        resolved = _within(candidate if candidate.is_absolute() else project / candidate, project, "Recovery file")
        if not resolved.is_file():
            raise ValueError(f"Recovery file does not exist: {resolved}")
        if resolved not in originals:
            originals.append(resolved)
        if resolved not in recovery_files:
            recovery_files.append(resolved)

    scopes = []
    for scope in write_scope or []:
        candidate = Path(scope).expanduser()
        if ".." in candidate.parts:
            raise ValueError(f"Write scope traversal is not allowed: {scope}")
        resolved = _within(candidate if candidate.is_absolute() else project / candidate, project, "Write scope")
        if str(resolved) not in scopes:
            scopes.append(str(resolved))

    context_root = _within(project / ".aris" / "workbench" / "context" / role, project, "Context directory")
    context_root.mkdir(parents=True, exist_ok=True)
    run_number = max((int(p.name) for p in context_root.iterdir() if p.name.isdecimal()), default=0) + 1
    run = context_root / f"{run_number:04d}"
    run.mkdir()
    copied = run / "skills"
    copied.mkdir()
    skill_files = []
    skill_index = {}
    provenance = []
    shared_groups = {shared: copied}
    shutil.copytree(shared, copied / "shared-references")
    # Canonical Codex research-refine also references ../../shared-references
    # from its skill directory. Preserve that actual source-relative depth.
    shutil.copytree(parent_shared, run / "shared-references")
    for skill, source, chosen, source_shared in sources:
        if source_shared not in shared_groups:
            group = copied / f"source-{len(shared_groups):03d}"
            group.mkdir()
            shutil.copytree(source_shared, group / "shared-references")
            shared_groups[source_shared] = group
        destination = shared_groups[source_shared] / skill
        shutil.copytree(source, destination)
        skill_files.append(str(destination / "SKILL.md"))
        skill_index[skill] = str(destination / "SKILL.md")
        provenance.append(f"- {skill}: selected `{chosen}`; resolved source `{source}` → copy `{destination}`; shared references `{source_shared}`")

    startup_entry, startup_source = _startup_entry(project, harness)
    if startup_source not in originals:
        originals.append(startup_source)
    navigation = _navigation(project, role, harness, task, scopes, repo, run, skill_index, originals)
    packet = run / "packet.md"
    original_lines = "\n".join(f"- `{path}`" for path in originals) or "- No standard project or recovery files found."
    recovery_lines = "\n".join(f"- `{path}`" for path in recovery_files) or "- No explicit recovery files supplied."
    scope_lines = "\n".join(f"- `{path}`" for path in scopes) or "- No write scope supplied; obtain scope from the existing project authorization before editing."
    skill_lines = "\n".join(f"- {name}: `{path}`" for name, path in skill_index.items())
    precedence = " → ".join(f"`{root}/<name>`" for root in roots)
    precedence += " → bundled SuperARIS project-agent (for that product skill only)"
    precedence += f" → `{host_root}/<name>`"
    packet.write_text(
        f"# ARIS project role context\n\nRole: {role}\nHarness: {harness}\nProject: `{project}`\n"
        f"Source ARIS checkout: `{repo}`\n\n## Prepared context task\n\n{task}\n\n"
        "This is a preparation snapshot; the original owner and current binding determine your current assignment. "
        "A candidate task here does not replace that assignment.\n\n"
        f"## Required startup and recovery reads\n\nRead common ARIS navigation `{navigation['navigation']}`, "
        f"your role and write scope `{navigation['role_file']}`, and project recovery `{navigation['recovery_file']}` first. "
        "Then read current original project goal/state and the selected skills below. Re-read these inputs after compact or restart.\n\n"
        f"Native project startup entry: `{startup_entry}` (actual file `{startup_source}`). "
        "Its managed recovery block follows this harness's project instruction convention and preserves user text. "
        "File wiring and a current session's actual read evidence are separate.\n\n"
        f"## Read actual project state\n\n{original_lines}\n\n"
        "Read these originals before acting. They remain authoritative; this packet does not duplicate their contents. "
        "On recovery, read their current contents and reconcile real artifacts with the existing owner.\n\n"
        f"## Explicit recovery inputs\n\n{recovery_lines}\n\n"
        f"## Authorized write scope\n\n{scope_lines}\n\n"
        f"## Load selected skills\n\n{skill_lines}\n\n"
        "Always read project-agent coordination material. Other named entries include the selected workflows' "
        "default dependency closure from the canonical skill catalog. When a workflow invokes a skill by name, "
        "read its exact copied SKILL.md from this index; native slash-command discovery is not required. "
        "Optional skills outside this index require another context preparation or a capable owner.\n\n"
        "Read each selected SKILL.md and the referenced scripts, references and assets as needed. "
        "Their relative directory layout is preserved here, including host-specific shared-references. "
        "Copies record source content at preparation time; they do not replace installed skills.\n\n"
        f"### Source provenance\n\n" + ("\n".join(provenance) or "- None.") + "\n\n"
        + f"Source precedence (first existing entry wins): {precedence}. Existing malformed entries are errors, not silent fallbacks.\n\n"
        + (f"Shared references source: `{shared}`\n\n" if sources else "")
        + f"Parent-depth shared references source: `{parent_shared}` → `{run / 'shared-references'}`.\n\n"
        + f"Canonical dependency catalog: `{repo / 'tools/skill-groups.tsv'}`. Canonical helper root: `{repo / 'tools'}`. "
        + (f"For PowerShell, set $env:ARIS_REPO to {str(repo)!r} before invoking the Python helper with & in that same shell. " if WINDOWS else f"Before each helper shell invocation, set ARIS_REPO={repo} explicitly in that same invocation. ")
        +
        "Do not assume a reused or adopted native process inherited a launcher environment. "
        "The main owner executes canonical tools through the original skill helper resolver. A role or file-only MCP author "
        "without command execution or outside-root access must report that limitation to the main owner, "
        "who executes the required original helper and returns actual results; a copied skill does not grant permissions.\n\n"
        + "## Existing operating boundaries\n\n"
        "Preserve the project's original MCP routes, author ownership, writer locks, frozen commands, "
        "budgets, model choices and reviewer freshness requirements. Existing reviewer isolation and acceptance "
        "gates still apply; a role session or idle/done event is not independent review or scientific acceptance. "
        "A paused Goal remains paused; context preparation does not start or resume a Goal, production batch "
        "or paid model call. Follow existing user authorization for commits, publication and merges; preparing "
        "this packet grants no new merge authorization. Do not overwrite other owners' files or modify global "
        "or project native skill installations. Use the main owner's existing receipt and follow-up mechanism; "
        "this packet introduces no transport commands or new task schema.\n",
        encoding="utf-8",
    )
    return {
        **navigation,
        "startup_files": [str(startup_entry)],
        "startup_entry": str(startup_entry),
        "startup_source": str(startup_source),
        "packet": str(packet),
        "skill_files": skill_files,
        "skill_index": skill_index,
        "project_files": [str(path) for path in originals],
        "prompt": f"Read the ARIS role packet at {packet} first. Follow its required common navigation, role scope and project recovery reads, then current originals and selected skills before acting.",
    }
