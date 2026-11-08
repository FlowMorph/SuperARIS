"""Native subprocess checks: these run unchanged on Windows, macOS and Linux."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest


def wait_file(path, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return path.read_text(encoding="utf-8")
        time.sleep(.05)
    pytest.fail(f"test-owned process did not create {path.name}")


def child(code, *args):
    return subprocess.Popen([sys.executable, "-c", code, *map(str, args)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


LOCK_CHILD = '''
import sys, time
from pathlib import Path
from superaris.platform import FileLock, LockBusy
try:
    with FileLock(Path(sys.argv[1]), blocking=False):
        Path(sys.argv[2]).write_text("held", encoding="utf-8")
        if len(sys.argv) > 3:
            time.sleep(60)
except LockBusy:
    sys.exit(23)
'''


def test_lock_is_exclusive_between_processes_and_recovers_after_owner_death(tmp_path):
    lock = tmp_path / "锁 with spaces.lock"
    ready = tmp_path / "ready"
    owner = child(LOCK_CHILD, lock, ready, "hold")
    try:
        wait_file(ready)
        contender = child(LOCK_CHILD, lock, tmp_path / "forbidden")
        out, err = contender.communicate(timeout=10)
        assert contender.returncode == 23, (out, err)
        assert not (tmp_path / "forbidden").exists()
    finally:
        owner.terminate()
        owner.communicate(timeout=10)
    successor = child(LOCK_CHILD, lock, tmp_path / "successor")
    out, err = successor.communicate(timeout=10)
    assert successor.returncode == 0, (out, err)
    assert (tmp_path / "successor").read_text() == "held"


def test_lock_context_releases_after_exception(tmp_path):
    from superaris.platform import FileLock
    path = tmp_path / "exception.lock"
    with pytest.raises(RuntimeError):
        with FileLock(path):
            raise RuntimeError("intentional fixture failure")
    contender = child(LOCK_CHILD, path, tmp_path / "released")
    out, err = contender.communicate(timeout=10)
    assert contender.returncode == 0, (out, err)


def test_detached_child_survives_launcher_and_receives_late_file(tmp_path):
    # No inherited pipes: communicate() must finish when the launcher exits.
    inbox, result = tmp_path / "late inbox", tmp_path / "late result"
    worker = '''import pathlib, sys, time
inbox, result = map(pathlib.Path, sys.argv[1:])
for _ in range(200):
    if inbox.exists():
        result.write_text(inbox.read_text(encoding="utf-8"), encoding="utf-8")
        break
    time.sleep(.05)
else:
    sys.exit(2)
'''
    launcher = '''import subprocess, sys
from superaris.platform import detached_process_options
p = subprocess.Popen([sys.executable, "-c", sys.argv[1], *sys.argv[2:]],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    **detached_process_options())
print(p.pid)
'''
    parent = child(launcher, worker, inbox, result)
    out, err = parent.communicate(timeout=10)
    assert parent.returncode == 0, err
    assert int(out.strip()) != parent.pid
    inbox.write_text("late 中文 report after parent exit", encoding="utf-8")
    assert wait_file(result) == "late 中文 report after parent exit"


def test_command_line_preserves_native_arguments(tmp_path):
    from superaris.platform import command_line
    target = tmp_path / "argv with 中文 spaces.json"
    script = tmp_path / "capture argv.py"
    script.write_text("import json, pathlib, sys\npathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]), encoding='utf-8')\n", encoding="utf-8")
    arguments = ["two words", "中文", "O'Brien", "$env:PATH", "semi;colon", 'a"quote', "tail\\"]
    command = command_line([sys.executable, str(script), str(target), *arguments])
    if os.name == "nt":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        assert shell, "native Windows command test requires PowerShell"
        invocation = [shell, "-NoProfile", "-NonInteractive", "-Command", command]
    else:
        invocation = ["/bin/sh", "-c", command]
    completed = subprocess.run(invocation, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(target.read_text(encoding="utf-8")) == arguments


def make_fake_executable(directory, source):
    """Real argv-preserving executable; .cmd reparses multiline native args."""
    if os.name == "nt":
        from io import BytesIO
        from zipfile import ZipFile
        from pip._vendor.distlib.scripts import ScriptMaker
        maker = ScriptMaker(None, str(directory))
        archive = BytesIO()
        with ZipFile(archive, "w") as bundle:
            bundle.writestr("__main__.py", source.encode("utf-8"))
        executable = directory / "fake herdr transport.exe"
        executable.write_bytes(maker._get_launcher("t") + maker._get_shebang("utf-8") + archive.getvalue())
    else:
        executable = directory / "fake herdr transport"
        executable.write_text(f"#!{sys.executable}\n" + source, encoding="utf-8")
        executable.chmod(0o755)
    return executable


@pytest.fixture
def native_receiver_project(tmp_path):
    from superaris import receiver
    from tests.test_workbench_receiver import FAKE_TRANSPORT, ReceiverProject
    directory = tmp_path / "receiver 中文 with spaces"
    directory.mkdir()
    class SingleOwnerProject(ReceiverProject):
        def invoke(self, command, *options):
            if command == "start":
                options = (*options, "--only-role", "main")
            return super().invoke(command, *options)
    fixture = SingleOwnerProject(directory)
    fixture.binary = make_fake_executable(directory, FAKE_TRANSPORT)
    try:
        yield fixture
    finally:
        receiver.stop(fixture.project)
        deadline = time.monotonic() + 15
        while receiver.status(fixture.project)["managed_process_alive"] and time.monotonic() < deadline:
            time.sleep(.05)
        assert not receiver.status(fixture.project)["managed_process_alive"]


def test_fake_executable_preserves_multiline_native_argv(native_receiver_project):
    fixture = native_receiver_project
    body = "First line 中文\nSecond line with spaces and 'quotes'\nThird line"
    completed = subprocess.run([str(fixture.binary), "--session", "isolated-test", "notification", "show",
                                "test title", "--body", body], env=fixture.env,
                               capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    assert fixture.commands()[-1] == ["notification", "show", "test title", "--body", body]


@pytest.mark.parametrize("attach", [False, True])
def test_real_receiver_lifetime_and_report_deduplication(native_receiver_project, attach):
    from tests.test_workbench_receiver import test_receiver_survives_launcher_exit_and_collects_late_report_once
    fixture = native_receiver_project
    test_receiver_survives_launcher_exit_and_collects_late_report_once(fixture, attach)
    reused = fixture.invoke("receiver", "--action", "start", "--herdr-bin", fixture.binary)
    assert reused["action"] == "reused"


def test_real_receiver_explicit_stop_restart_and_single_child(native_receiver_project):
    from tests.test_workbench_receiver import test_explicit_stop_stays_disabled_until_receiver_start_and_reuses_one_child
    test_explicit_stop_stays_disabled_until_receiver_start_and_reuses_one_child(native_receiver_project)


@pytest.mark.parametrize("change", ["binding-owner", "live-occupant", "server-loss"])
def test_real_receiver_preserves_owner_identity_on_loss(native_receiver_project, change):
    from tests.test_workbench_receiver import test_receiver_ends_on_original_owner_or_fake_server_loss_without_rebinding
    test_receiver_ends_on_original_owner_or_fake_server_loss_without_rebinding(native_receiver_project, change)


@pytest.fixture
def ndjson_server(tmp_path):
    """Actual local IPC on either OS; Windows uses public Win32 byte pipes."""
    import threading
    import uuid
    from contextlib import contextmanager

    @contextmanager
    def serve(handler):
        errors = []
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes as w
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.CreateNamedPipeW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.LPVOID]
            api.CreateNamedPipeW.restype = w.HANDLE
            api.ConnectNamedPipe.argtypes = [w.HANDLE, w.LPVOID]
            api.CloseHandle.argtypes = [w.HANDLE]
            api.DisconnectNamedPipe.argtypes = [w.HANDLE]
            api.FlushFileBuffers.argtypes = [w.HANDLE]
            for name in ("ReadFile", "WriteFile"):
                getattr(api, name).argtypes = [w.HANDLE, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD), w.LPVOID]
            endpoint = "\\\\.\\pipe\\superaris-test-" + uuid.uuid4().hex
            handle = api.CreateNamedPipeW(endpoint, 3, 0, 1, 65536, 65536, 0, None)
            assert handle != ctypes.c_void_p(-1).value
            def run():
                try:
                    connected = api.ConnectNamedPipe(handle, None)
                    if not connected and ctypes.get_last_error() != 535:
                        raise ctypes.WinError(ctypes.get_last_error())
                    def read():
                        data = bytearray()
                        while not data.endswith(b"\n"):
                            buf, n = ctypes.create_string_buffer(1), w.DWORD()
                            assert api.ReadFile(handle, buf, 1, ctypes.byref(n), None)
                            data.extend(buf.raw[:n.value])
                        return bytes(data)
                    def send(data):
                        n = w.DWORD()
                        assert api.WriteFile(handle, data, len(data), ctypes.byref(n), None)
                        assert n.value == len(data)
                    handler(read, send)
                    api.FlushFileBuffers(handle)
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    api.DisconnectNamedPipe(handle)
                    api.CloseHandle(handle)
        else:
            import socket
            import tempfile
            endpoint = str(Path(tempfile.gettempdir()) / ("sa-" + uuid.uuid4().hex + ".sock"))
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(endpoint)
            listener.listen(1)
            listener.settimeout(10)
            def run():
                try:
                    with listener.accept()[0] as connection:
                        with connection.makefile("rb") as stream:
                            handler(stream.readline, connection.sendall)
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    listener.close()
                    Path(endpoint).unlink(missing_ok=True)
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        try:
            yield endpoint
        finally:
            worker.join(timeout=10)
            assert not worker.is_alive(), "test-owned IPC server did not exit"
            assert not errors, errors
    return serve


def test_native_transport_fragmentation_and_eof(ndjson_server):
    from superaris.transport import connect
    def handler(read, send):
        assert json.loads(read()) == {"method": "ping"}
        send(b'{"result":')
        time.sleep(.02)
        send(b'{"type":"pong"}}\n{"second":true}\n')
    with ndjson_server(handler) as endpoint, connect(endpoint, 2) as connection:
        connection.sendall(b'{"method":"ping"}\n')
        assert json.loads(connection.readline()) == {"result": {"type": "pong"}}
        assert json.loads(connection.readline()) == {"second": True}
        assert connection.readline() == b""


def test_native_transport_idle_read_has_bounded_timeout(ndjson_server):
    from superaris.transport import connect
    def handler(read, send):
        assert read() == b"ready\n"
        time.sleep(.6)
    with ndjson_server(handler) as endpoint, connect(endpoint, .15) as connection:
        connection.sendall(b"ready\n")
        began = time.monotonic()
        with pytest.raises(TimeoutError):
            connection.readline()
        assert time.monotonic() - began < 2


def test_herdr_events_uses_ndjson_and_surfaces_events_lost(ndjson_server):
    from superaris.client import Herdr, HerdrError
    subscriptions = [{"type": "pane.agent_status_changed", "pane_id": "w1:p1"}]
    def handler(read, send):
        request = json.loads(read())
        assert request["method"] == "events.subscribe"
        assert request["params"] == {"subscriptions": subscriptions}
        send((json.dumps({"id": request["id"], "result": {"type": "subscribed"}}) + "\n").encode())
        send(b'{"event":{"type":"events_lost","count":3}}\n')
    with ndjson_server(handler) as endpoint:
        client = Herdr("isolated-wire-test")
        client._socket = endpoint
        stream = client.events(subscriptions, timeout=2)
        assert next(stream)["result"]["type"] == "subscribed"
        assert next(stream)["event"]["type"] == "events_lost"
        with pytest.raises(HerdrError):
            next(stream)
