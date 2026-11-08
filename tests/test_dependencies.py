"""Dependency selection is explicit, lazy and pinned; tests never use network."""

import io
import os
from pathlib import Path
import subprocess
import tarfile

import pytest

from superaris import dependencies
from tests.support import CLI, make_aris_repo


def forbidden_network(*args, **kwargs):
    pytest.fail("this dependency path must not fetch from the network")


def test_help_and_plan_do_not_resolve_a_configured_invalid_dependency(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    cache = tmp_path / "cache"
    environment = {**os.environ, "SUPERARIS_ARIS_REPO": str(tmp_path / "missing-aris"),
                   "XDG_CACHE_HOME": str(cache)}
    for arguments in (["--help"], ["start", str(project), "--plan"]):
        result = subprocess.run([*CLI, *arguments], env=environment, cwd=tmp_path,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
    assert not cache.exists()
    assert not (project / ".aris").exists()


def test_explicit_repo_wins_over_environment_without_fetch(tmp_path, monkeypatch):
    explicit = make_aris_repo(tmp_path / "selected")
    environment = make_aris_repo(tmp_path / "environment")
    monkeypatch.setenv("SUPERARIS_ARIS_REPO", str(environment))
    monkeypatch.setattr(dependencies, "urlopen", forbidden_network)
    assert dependencies.resolve_aris_repo(explicit) == explicit
    assert dependencies.resolve_aris_repo() == environment


def test_invalid_explicit_repo_does_not_silently_fall_back(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPERARIS_ARIS_REPO", str(make_aris_repo(tmp_path / "valid-environment")))
    monkeypatch.setattr(dependencies, "urlopen", forbidden_network)
    with pytest.raises(ValueError, match="Invalid ARIS checkout"):
        dependencies.resolve_aris_repo(tmp_path / "incomplete")


def test_existing_pinned_cache_is_used_without_ambient_aris_pointer(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPERARIS_ARIS_REPO", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cached = make_aris_repo(tmp_path / "cache/superaris/aris" / dependencies.ARIS_COMMIT)
    wrong = tmp_path / "wrong"
    monkeypatch.setenv("ARIS_REPO", str(wrong))
    pointer = Path.home() / ".aris/repo"
    pointer.parent.mkdir(exist_ok=True)
    pointer.write_text(str(wrong))
    monkeypatch.setattr(dependencies, "urlopen", forbidden_network)
    assert dependencies.resolve_aris_repo() == cached


def test_incomplete_pinned_cache_reports_actionable_error_without_refetch(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPERARIS_ARIS_REPO", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cached = tmp_path / "cache/superaris/aris" / dependencies.ARIS_COMMIT
    cached.mkdir(parents=True)
    monkeypatch.setattr(dependencies, "urlopen", forbidden_network)
    with pytest.raises(RuntimeError, match="Cached ARIS is incomplete"):
        dependencies.resolve_aris_repo()


def test_lazy_fetch_uses_fixed_commit_then_reuses_cache(tmp_path, monkeypatch):
    source = make_aris_repo(tmp_path / "archive-source")
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(source, arcname="canonical-aris")
    payload = archive.read_bytes()
    calls = []

    def fetch(url, **kwargs):
        calls.append((url, kwargs))
        return io.BytesIO(payload)

    monkeypatch.delenv("SUPERARIS_ARIS_REPO", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(dependencies, "urlopen", fetch)
    resolved = dependencies.resolve_aris_repo()
    assert resolved.name == dependencies.ARIS_COMMIT
    assert calls == [(dependencies.ARIS_URL, {"timeout": 60})]
    assert dependencies.ARIS_COMMIT in dependencies.ARIS_URL
    assert dependencies.resolve_aris_repo() == resolved
    assert len(calls) == 1


def test_archive_parent_traversal_is_rejected_before_writing_outside(tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("canonical-aris/../../outside.txt")
        member.size = 4
        stream.addfile(member, io.BytesIO(b"oops"))
    with pytest.raises(ValueError, match="Unsafe path"):
        dependencies._extract_archive(archive, tmp_path / "unpacked")
    assert not (tmp_path / "outside.txt").exists()
