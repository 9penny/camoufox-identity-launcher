from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import uuid
from ctypes import wintypes
from pathlib import Path


APP_DIR = Path(os.environ["LOCALAPPDATA"]) / "CamoufoxIdentityLauncher"
CONFIG_PATH = APP_DIR / "identities.json"
PROFILES_DIR = APP_DIR / "profiles"
LOGS_DIR = APP_DIR / "logs"


class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_crypt32.CryptProtectData.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
_crypt32.CryptProtectData.restype = wintypes.BOOL
_crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
_crypt32.CryptUnprotectData.restype = wintypes.BOOL
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _dpapi(data: bytes, decrypt: bool) -> bytes:
    source, buffer = _blob(data)
    output = Blob()
    method = _crypt32.CryptUnprotectData if decrypt else _crypt32.CryptProtectData
    args = (ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(output)) if decrypt else (
        ctypes.byref(source), "Camoufox Identity Launcher", None, None, None, 0x1, ctypes.byref(output))
    if not method(*args):
        raise OSError(ctypes.get_last_error(), "Windows DPAPI failed")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        _kernel32.LocalFree(output.pbData)


def encrypt(value: str) -> str:
    return base64.b64encode(_dpapi(value.encode("utf-8"), False)).decode("ascii") if value else ""


def decrypt(value: str) -> str:
    return _dpapi(base64.b64decode(value), True).decode("utf-8") if value else ""


def ensure_dirs() -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def load_identities() -> list[dict]:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        return []
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("身份配置格式错误")
    for item in data:
        item["password"] = decrypt(item.pop("password_dpapi", ""))
    return data


def save_identities(identities: list[dict]) -> None:
    ensure_dirs()
    data = []
    for item in identities:
        record = dict(item)
        record["password_dpapi"] = encrypt(record.pop("password", ""))
        data.append(record)
    temp = CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, CONFIG_PATH)


def new_id() -> str:
    return uuid.uuid4().hex


def profile_dir(identity_id: str) -> Path:
    # Never let config data escape the managed profile tree.
    if len(identity_id) != 32 or any(c not in "0123456789abcdef" for c in identity_id):
        raise ValueError("身份 ID 无效")
    return PROFILES_DIR / identity_id


def delete_profile(identity_id: str) -> None:
    path = profile_dir(identity_id)
    if path.exists():
        shutil.rmtree(path)
