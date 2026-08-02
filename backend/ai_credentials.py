"""Per-user encrypted storage for optional AI credentials.

Windows builds use DPAPI, so the stored bytes can only be decrypted by the
same Windows account.  The API never returns a stored secret to the frontend.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys


_MAGIC = b"BOOKBUDDY_AI_KEYS_V1\0"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class CredentialStorageUnavailable(RuntimeError):
    pass


if sys.platform == "win32":
    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _protect(data: bytes) -> bytes:
    if sys.platform != "win32":
        raise CredentialStorageUnavailable("Secure credential storage is unavailable on this platform")
    source_buffer = ctypes.create_string_buffer(data)
    source = _DataBlob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_char)))
    protected = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "BookBuddy AI credentials", None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(protected),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(protected.pbData, protected.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(protected.pbData)


def _unprotect(data: bytes) -> bytes:
    if sys.platform != "win32":
        raise CredentialStorageUnavailable("Secure credential storage is unavailable on this platform")
    source_buffer = ctypes.create_string_buffer(data)
    source = _DataBlob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_char)))
    clear = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(clear),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(clear.pbData, clear.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(clear.pbData)


def _clean_keys(values: list[str] | tuple[str, ...]) -> list[str]:
    return [value.strip() for value in values if isinstance(value, str) and value.strip()]


class EncryptedCredentialStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    @property
    def available(self) -> bool:
        return sys.platform == "win32"

    def read(self) -> dict[str, list[str]]:
        if not self.path.is_file():
            return {"api_keys": [], "vision_api_keys": []}
        payload = self.path.read_bytes()
        if not payload.startswith(_MAGIC):
            raise ValueError("Unsupported BookBuddy credential store")
        decoded = json.loads(_unprotect(payload[len(_MAGIC):]).decode("utf-8"))
        return {
            "api_keys": _clean_keys(decoded.get("api_keys", [])),
            "vision_api_keys": _clean_keys(decoded.get("vision_api_keys", [])),
        }

    def write(self, api_keys: list[str], vision_api_keys: list[str]) -> None:
        clear = json.dumps({
            "schema_version": "bookbuddy_ai_credentials_v1",
            "api_keys": _clean_keys(api_keys),
            "vision_api_keys": _clean_keys(vision_api_keys),
        }, separators=(",", ":")).encode("utf-8")
        protected = _MAGIC + _protect(clear)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("wb") as handle:
            handle.write(protected)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def delete(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
