"""Herdr's public NDJSON transport: Unix sockets or native Windows pipes."""
from __future__ import annotations

from contextlib import contextmanager
import os
import socket
import time


class WindowsPipe:
    """Overlapped Win32 I/O, so idle subscriptions have a real bounded timeout."""
    def __init__(self, endpoint: str, timeout: float):
        import ctypes
        from ctypes import wintypes as w
        self.c, self.w, self.timeout = ctypes, w, timeout
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
        self.api.CreateFileW.restype = w.HANDLE
        self.api.CreateEventW.argtypes = [w.LPVOID, w.BOOL, w.BOOL, w.LPCWSTR]
        self.api.CreateEventW.restype = w.HANDLE
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.api.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        self.api.WaitNamedPipeW.argtypes = [w.LPCWSTR, w.DWORD]
        self.api.CancelIoEx.argtypes = [w.HANDLE, w.LPVOID]
        self.api.GetOverlappedResult.argtypes = [w.HANDLE, w.LPVOID, ctypes.POINTER(w.DWORD), w.BOOL]
        for name in ("ReadFile", "WriteFile"):
            getattr(self.api, name).argtypes = [w.HANDLE, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD), w.LPVOID]
        class Overlapped(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                        ("Offset", w.DWORD), ("OffsetHigh", w.DWORD), ("hEvent", w.HANDLE)]
        self.Overlapped = Overlapped
        self.buffer = b""
        deadline = time.monotonic() + timeout
        while True:
            self.handle = self.api.CreateFileW(endpoint, 0xC0000000, 0, None, 3, 0x40000000, None)
            if self.handle != ctypes.c_void_p(-1).value:
                break
            error = ctypes.get_last_error()
            if error != 231 or time.monotonic() >= deadline:  # ERROR_PIPE_BUSY
                raise ctypes.WinError(error)
            self.api.WaitNamedPipeW(endpoint, max(1, int((deadline - time.monotonic()) * 1000)))

    def _io(self, writing: bool, data):
        c, w = self.c, self.w
        buffer = c.create_string_buffer(data) if writing else c.create_string_buffer(65536)
        count = w.DWORD()
        event = self.api.CreateEventW(None, True, False, None)
        if not event:
            raise c.WinError(c.get_last_error())
        operation = self.Overlapped(hEvent=event)
        try:
            function = self.api.WriteFile if writing else self.api.ReadFile
            success = function(self.handle, buffer, len(data) if writing else 65536, c.byref(count), c.byref(operation))
            error = c.get_last_error() if not success else 0
            if not success and error == 997:  # ERROR_IO_PENDING
                wait = self.api.WaitForSingleObject(event, max(1, int(self.timeout * 1000)))
                if wait != 0:
                    self.api.CancelIoEx(self.handle, c.byref(operation))
                    # Cancellation must finish before the buffer/OVERLAPPED die.
                    self.api.GetOverlappedResult(self.handle, c.byref(operation), c.byref(count), True)
                    if wait == 258:
                        raise TimeoutError("Herdr named-pipe read timed out")
                    raise c.WinError(c.get_last_error())
                success = self.api.GetOverlappedResult(self.handle, c.byref(operation), c.byref(count), False)
                error = c.get_last_error() if not success else 0
            if not success:
                if not writing and error in (109, 232, 233):
                    return buffer.raw[:count.value]  # disconnected read end => EOF
                if writing or error != 234:  # ERROR_MORE_DATA is a read fragment
                    raise c.WinError(error)
            return count.value if writing else buffer.raw[:count.value]
        finally:
            self.api.CloseHandle(event)

    def sendall(self, data: bytes):
        while data:
            count = self._io(True, data)
            if not count:
                raise OSError("Herdr named pipe closed during write")
            data = data[count:]

    def readline(self):
        while b"\n" not in self.buffer:
            data = self._io(False, None)
            if not data:
                result, self.buffer = self.buffer, b""
                return result
            self.buffer += data
        line, self.buffer = self.buffer.split(b"\n", 1)
        return line + b"\n"

    def close(self):
        self.api.CloseHandle(self.handle)


@contextmanager
def connect(endpoint: str, timeout: float):
    if os.name == "nt":
        connection = WindowsPipe(endpoint, timeout)
        try:
            yield connection
        finally:
            connection.close()
    else:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(endpoint)
            with connection.makefile("rb") as stream:
                class Channel:
                    sendall = connection.sendall
                    readline = stream.readline
                yield Channel()


def endpoint_exists(endpoint: str) -> bool:
    if os.name != "nt":
        from pathlib import Path
        return Path(endpoint).exists()
    import ctypes
    from ctypes import wintypes as w
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.WaitNamedPipeW.argtypes = [w.LPCWSTR, w.DWORD]
    if api.WaitNamedPipeW(endpoint, 1):
        return True
    error = ctypes.get_last_error()
    if error in (2, 3):
        return False
    # Busy, timeout or access denied indicates an existing endpoint. Never
    # restart an existing server merely because this client cannot access it.
    return True
