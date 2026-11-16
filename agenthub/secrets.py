"""Per-Windows-user encrypted credentials. No plaintext fallback."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import threading


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _protect(raw, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Secure key storage requires Windows DPAPI")
    buffer = ctypes.create_string_buffer(raw)
    source = _Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), "Local Agent Orchestrator", None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise RuntimeError("Windows could not access this user's encrypted key")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class SecretStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else {}

    def set(self, name, value):
        if not isinstance(name, str) or not name or len(name) > 100:
            raise ValueError("Invalid credential name")
        if not isinstance(value, str) or len(value) > 16384:
            raise ValueError("Invalid credential value")
        with self.lock:
            values = self._load()
            if value:
                values[name] = base64.b64encode(_protect(value.encode("utf-8"))).decode("ascii")
            else:
                values.pop(name, None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(values), encoding="utf-8")
            os.replace(temporary, self.path)

    def get(self, name):
        with self.lock:
            value = self._load().get(name)
            if not value:
                return None
            return _protect(base64.b64decode(value, validate=True), decrypt=True).decode("utf-8")

    def has(self, name):
        with self.lock:
            return bool(self._load().get(name))
