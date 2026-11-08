"""Explicit or lazily fetched, commit-pinned canonical ARIS dependency."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile
from urllib.request import urlopen


ARIS_COMMIT = "2901234ad2954cd2388ced8d3aed2ed9de42803a"
ARIS_URL = f"https://codeload.github.com/wanshuiyin/Auto-claude-code-research-in-sleep/tar.gz/{ARIS_COMMIT}"


def productcommand() -> list[str]:
    """Use the installed interpreter, never a helper from the ARIS checkout."""
    return [sys.executable, "-m", "superaris"]


def _validate_repo(path: Path) -> Path:
    path = path.expanduser().resolve()
    directories = ("skills", "skills/shared-references", "skills/skills-codex",
                   "skills/skills-codex/shared-references")
    files = ("tools/skill-groups.tsv", "docs/SKILLS_CATALOG.md", "LICENSE")
    missing = [name for name in directories if not (path / name).is_dir()]
    missing += [name for name in files if not (path / name).is_file()]
    if missing:
        raise ValueError(f"Invalid ARIS checkout {path}; missing: {', '.join(missing)}. "
                         "Select a complete checkout with --aris-repo or SUPERARIS_ARIS_REPO.")
    return path


def _extract_archive(archive: Path, destination: Path) -> Path:
    """Extract one repository root; links cannot escape that archive root."""
    destination = destination.resolve()
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        roots = set()
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not name.parts:
                raise ValueError(f"Unsafe path in ARIS archive: {member.name}")
            roots.add(name.parts[0])
        if len(roots) != 1:
            raise ValueError("ARIS archive must contain one repository directory")
        repository = destination / next(iter(roots))
        for member in members:
            target = destination / member.name
            if not target.resolve().is_relative_to(repository):
                raise ValueError(f"ARIS archive path escapes its repository: {member.name}")
            if member.issym() or member.islnk():
                link = Path(member.linkname)
                resolved = ((target.parent / link) if member.issym() else (destination / link)).resolve()
                if link.is_absolute() or not resolved.is_relative_to(repository):
                    raise ValueError(f"ARIS archive link escapes its repository: {member.name}")
            elif not (member.isdir() or member.isfile()):
                raise ValueError(f"Unsupported ARIS archive entry: {member.name}")
        # Write regular files before links, so extraction cannot traverse a
        # previously created archive symlink while writing a later file.
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as incoming, target.open("wb") as output:
                    shutil.copyfileobj(incoming, output)
                target.chmod(member.mode & 0o777)
        for member in members:
            if member.issym() or member.islnk():
                target = destination / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if member.issym():
                    target.symlink_to(member.linkname)
                else:
                    os.link(destination / member.linkname, target)
                try:
                    if not target.resolve().is_relative_to(repository):
                        raise ValueError(f"ARIS archive link chain escapes its repository: {member.name}")
                except RuntimeError as exc:
                    raise ValueError(f"ARIS archive contains a cyclic link: {member.name}") from exc
    return repository


def resolve_aris_repo(explicit: str | Path | None = None) -> Path:
    """Resolve canonical ARIS only at an action boundary, never during import.

    Ambient ARIS_REPO and ~/.aris/repo are intentionally not discovery inputs.
    The private cache is populated from the fixed public codeload URL only when
    no explicit checkout or SuperARIS-specific environment override is supplied.
    """
    configured = explicit if explicit is not None else os.environ.get("SUPERARIS_ARIS_REPO")
    if configured is not None and str(configured):
        return _validate_repo(Path(configured))
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache").expanduser()
    parent = base / "superaris/aris"
    cached = parent / ARIS_COMMIT
    parent.mkdir(parents=True, exist_ok=True)
    with (parent / f"{ARIS_COMMIT}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if cached.exists():
            try:
                return _validate_repo(cached)
            except ValueError as exc:
                raise RuntimeError(f"Cached ARIS is incomplete at {cached}. Remove that cache entry or set "
                                   f"SUPERARIS_ARIS_REPO to a complete checkout. {exc}") from exc
        try:
            with tempfile.TemporaryDirectory(prefix=".aris-download-", dir=parent) as staging:
                staging = Path(staging)
                archive = staging / "aris.tar.gz"
                with urlopen(ARIS_URL, timeout=60) as incoming, archive.open("wb") as output:
                    shutil.copyfileobj(incoming, output)
                extracted = _extract_archive(archive, staging / "unpacked")
                _validate_repo(extracted)
                extracted.rename(cached)
        except (OSError, ValueError, tarfile.TarError) as exc:
            raise RuntimeError(f"Could not prepare pinned ARIS {ARIS_COMMIT}: {exc}. Check network access to "
                               f"{ARIS_URL}, or select a complete local checkout with --aris-repo or "
                               "SUPERARIS_ARIS_REPO. No project or global skills were installed.") from exc
    return cached.resolve()
