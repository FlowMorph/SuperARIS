"""Herdr installation and existing-server checks without real system mutation."""

import json
import subprocess

import pytest

from superaris import client as transport


def test_missing_herdr_no_install_never_invokes_installer_or_server(tmp_path, monkeypatch):
    monkeypatch.setattr(transport.shutil, "which", lambda name: None)

    def forbidden(*args, **kwargs):
        pytest.fail("--no-install must not run Homebrew, a server, or another process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    log = tmp_path / "generated" / "server.log"
    with pytest.raises(transport.HerdrError, match="--no-install"):
        transport.Herdr("isolated-test").ensure(log, install=False)
    assert not log.parent.exists()


def test_installer_uses_existing_homebrew_and_exact_package_argv(monkeypatch):
    monkeypatch.setattr(transport, "WINDOWS", False)
    monkeypatch.setattr(transport.shutil, "which", lambda name: "/existing/brew" if name == "brew" else None)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    transport.install_herdr()
    assert calls == [(["/existing/brew", "install", "herdr"], {"check": False})]


@pytest.mark.parametrize("stale", [False, True])
def test_existing_session_socket_is_probed_without_server_restart(tmp_path, monkeypatch, stale):
    socket = tmp_path / "existing-session.sock"
    socket.touch()
    monkeypatch.setattr(transport.shutil, "which", lambda name: "/existing/herdr" if name == "herdr" else None)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        assert argv[:3] == ["herdr", "--session", "isolated-test"]
        assert not kwargs.get("shell", False)
        if argv[3:] == ["status"]:
            return subprocess.CompletedProcess(argv, 0, f"socket: {socket}\n", "")
        assert argv[3:] == ["api", "snapshot"]
        if stale:
            return subprocess.CompletedProcess(argv, 1, "", "existing socket is unavailable")
        return subprocess.CompletedProcess(argv, 0, json.dumps({"result": {"snapshot": {"agents": []}}}), "")

    def forbidden(*args, **kwargs):
        pytest.fail("an existing session socket is not permission to restart its server")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    log = tmp_path / "generated" / "server.log"
    if stale:
        with pytest.raises(transport.HerdrError, match="socket is unavailable"):
            transport.Herdr("isolated-test").ensure(log)
    else:
        transport.Herdr("isolated-test").ensure(log)
    assert calls == [
        ["herdr", "--session", "isolated-test", "status"],
        ["herdr", "--session", "isolated-test", "api", "snapshot"],
    ]
    assert socket.exists()
    assert not log.parent.exists()


def test_windows_installer_uses_official_command_and_process_local_path(tmp_path, monkeypatch):
    monkeypatch.setattr(transport, "WINDOWS", True)
    monkeypatch.setattr(transport.shutil, "which", lambda name: "powershell.exe" if name == "powershell" else None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("PATH", "original-path")
    alias = tmp_path / "Programs/Herdr/bin"
    alias.mkdir(parents=True)
    (alias / "herdr.exe").write_bytes(b"fake installed executable")
    calls = []
    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, "run", fake_run)
    transport.install_herdr()
    assert calls == [["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                      "irm https://herdr.dev/install.ps1 | iex"]]
    assert transport.os.environ["PATH"].startswith(str(alias) + transport.os.pathsep)
