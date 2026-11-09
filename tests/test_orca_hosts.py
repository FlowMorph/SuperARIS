"""Workbench selection/discovery and a real-interface shaped Orca CLI boundary."""
import json
from pathlib import Path
import subprocess

import pytest

from superaris import hosts
from superaris.cli import make_plan, parser
from superaris.orca import Orca, OrcaError
from superaris.state import directory, write


def test_old_missing_host_is_herdr_and_cannot_be_switched(tmp_path):
    write(directory(tmp_path) / "launch.json", {"session": "old", "roles": {}})
    plan = make_plan(parser().parse_args(["start", str(tmp_path), "--plan"]))
    assert plan["host"] == "herdr" and not plan["will_mutate"]
    before = (directory(tmp_path) / "launch.json").read_bytes()
    with pytest.raises(ValueError, match="belongs to herdr"):
        make_plan(parser().parse_args(["start", str(tmp_path), "--host", "orca", "--plan"]))
    assert (directory(tmp_path) / "launch.json").read_bytes() == before


def test_new_orca_plan_and_canonical_pending_arguments_are_offline(tmp_path):
    args = parser().parse_args(["start", str(tmp_path), "--host", "orca", "--orca-bin", "chosen-orca", "--plan"])
    plan = make_plan(args)
    assert plan["host"] == "orca" and len(plan["roles"]) == 3
    assert not (tmp_path / ".aris").exists()
    resumed = parser().parse_args(args.start_arguments)
    assert resumed.host == "orca" and resumed.orca_bin == "chosen-orca"


def test_orca_binding_is_inherited_without_explicit_host(tmp_path):
    write(directory(tmp_path) / "launch.json", {"host": "orca", "session": "original", "roles": {}})
    assert make_plan(parser().parse_args(["start", str(tmp_path), "--plan"]))["host"] == "orca"
    with pytest.raises(ValueError, match="belongs to orca"):
        make_plan(parser().parse_args(["start", str(tmp_path), "--host", "herdr", "--plan"]))


def test_mac_existing_bundle_is_used_without_install_or_path_change(tmp_path, monkeypatch):
    monkeypatch.setattr(hosts.sys, "platform", "darwin")
    monkeypatch.setattr(hosts.shutil, "which", lambda _: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("ORCA_CLI_INSTALL_PATH", raising=False)
    bundle = tmp_path / "Applications/Orca.app"
    launcher = bundle / "Contents/Resources/bin/orca"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("fake official launcher")
    found = hosts.discover_orca()
    assert found["cli"] == str(launcher) and found["source"] == "bundled"
    launcher.unlink()
    assert hosts.discover_orca()["app"] == str(bundle)
    assert "Settings" in hosts.orca_missing_action(hosts.discover_orca())


def test_linux_does_not_misidentify_gnome_orca(monkeypatch):
    monkeypatch.setattr(hosts.sys, "platform", "linux")
    queries = []
    monkeypatch.setattr(hosts.shutil, "which", lambda value: queries.append(value) or ("/usr/bin/orca" if value == "orca" else None))
    monkeypatch.delenv("ORCA_CLI_INSTALL_PATH", raising=False)
    assert hosts.discover_orca()["cli"] is None
    assert queries == ["orca-ide"]


@pytest.fixture
def orca(tmp_path, monkeypatch):
    executable = tmp_path / "official orca"
    executable.write_bytes(b"fake executable")
    return Orca(tmp_path, str(executable))


def test_actual_release_shaped_status_is_read_only_and_local(orca, monkeypatch):
    monkeypatch.setenv("ORCA_ENVIRONMENT", "foreign")
    monkeypatch.setenv("ORCA_PAIRING_CODE", "foreign-code")
    calls = []
    def run(argv, **options):
        calls.append((argv, options))
        return subprocess.CompletedProcess(argv, 0, json.dumps({"ok": True, "result": {
            "target": {"kind": "local"}, "runtime": {"reachable": False, "runtimeId": None}}}), "")
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(OrcaError, match="Open Orca"):
        orca.ensure_ready()
    assert len(calls) == 1
    argv, options = calls[0]
    assert argv[1:] == ["status", "--json"] and options["encoding"] == "utf-8"
    assert "ORCA_ENVIRONMENT" not in options["env"] and "ORCA_PAIRING_CODE" not in options["env"]


def test_native_error_recovery_data_survives_without_retry(orca, monkeypatch):
    calls = []
    native = {"ok": False, "error": {"code": "unknown", "message": "Inspect original receipt", "data": {"requestId": "native-request"}}}
    def run(argv, **options):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, json.dumps(native), "")
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(OrcaError) as caught:
        orca.call("terminal", "send", "--terminal", "recorded")
    assert caught.value.response == native and len(calls) == 1


def test_screen_rejects_accumulated_history(orca, monkeypatch):
    monkeypatch.setattr(orca, "call", lambda *a: {"result": {"terminal": {"source": "stream", "tail": ["›"]}}})
    with pytest.raises(OrcaError, match="current rendered screen"):
        orca.read_screen("recorded")


def test_relative_orca_executable_and_pending_argv_survive_project_cwd(tmp_path, monkeypatch):
    import os
    from tests.test_windows_runtime import executable
    (tmp_path / "bin").mkdir()
    binary = executable(tmp_path / "bin/official-orca", 'import json\nprint(json.dumps({"ok": True,"result":{"target":{"kind":"local"},"runtime":{"reachable":False,"runtimeId":None}}}))')
    project = tmp_path / "different project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    relative = os.path.relpath(binary, tmp_path)
    found = hosts.discover_orca(relative)
    assert Path(found["cli"]).is_absolute()
    assert Orca(project, relative).status()["runtime"]["reachable"] is False
    args = parser().parse_args(["start", str(project), "--host", "orca", "--orca-bin", relative, "--plan"])
    assert Path(args.orca_bin) == binary.resolve()
    monkeypatch.chdir(project)
    restored = parser().parse_args(args.start_arguments)
    assert Path(restored.orca_bin) == binary.resolve()
    assert Orca(project, restored.orca_bin).status()["target"]["kind"] == "local"
