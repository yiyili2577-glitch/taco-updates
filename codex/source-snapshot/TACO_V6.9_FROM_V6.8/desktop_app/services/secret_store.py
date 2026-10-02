import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path

from services.app_paths import AppPaths
from services.build_config import BuildConfig


class SecretStoreError(RuntimeError):
    pass


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class SecretStore:
    """Windows DPAPI 封裝。正式版不把授權 Token / SQL 密碼寫入 JSON 明碼。

    使用 LOCAL_MACHINE scope，讓同一台公司電腦上的不同 Windows 使用者都能使用
    同一份裝置授權；密文搬到另一台電腦無法直接解密。
    """

    FILE = "secrets.dpapi.json"

    @staticmethod
    def _file():
        return AppPaths.config_dir() / SecretStore.FILE

    @staticmethod
    def _load():
        p = SecretStore._file()
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _save(data):
        p = SecretStore._file(); p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)

    @staticmethod
    def _protect_windows(raw: bytes) -> bytes:
        in_buf = ctypes.create_string_buffer(raw)
        in_blob = _DATA_BLOB(len(raw), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_byte)))
        out_blob = _DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        CRYPTPROTECT_LOCAL_MACHINE = 0x4
        if not crypt32.CryptProtectData(ctypes.byref(in_blob), "TACO", None, None, None, CRYPTPROTECT_LOCAL_MACHINE, ctypes.byref(out_blob)):
            raise SecretStoreError("Windows DPAPI 加密失敗。")
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)

    @staticmethod
    def _unprotect_windows(raw: bytes) -> bytes:
        in_buf = ctypes.create_string_buffer(raw)
        in_blob = _DATA_BLOB(len(raw), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_byte)))
        out_blob = _DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            raise SecretStoreError("Windows DPAPI 解密失敗。")
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)

    @staticmethod
    def set_secret(key, value):
        key = str(key or "").strip(); value = str(value or "")
        if not key:
            raise ValueError("secret key 不可為空。")
        data = SecretStore._load()
        if sys.platform == "win32":
            encrypted = SecretStore._protect_windows(value.encode("utf-8"))
            data[key] = {"type": "dpapi", "value": base64.b64encode(encrypted).decode("ascii")}
        elif BuildConfig.is_development():
            # 僅為跨平台自動測試與開發。正式版在非 Windows 不允許明碼 fallback。
            data[key] = {"type": "dev_plain", "value": value}
        else:
            raise SecretStoreError("正式版 SecretStore 僅支援 Windows DPAPI。")
        SecretStore._save(data)

    @staticmethod
    def get_secret(key, default=""):
        item = SecretStore._load().get(str(key or ""), {})
        if not isinstance(item, dict):
            return default
        typ = item.get("type")
        try:
            if typ == "dpapi" and sys.platform == "win32":
                raw = base64.b64decode(item.get("value", ""))
                return SecretStore._unprotect_windows(raw).decode("utf-8")
            if typ == "dev_plain" and BuildConfig.is_development():
                return str(item.get("value", default))
        except Exception:
            return default
        return default

    @staticmethod
    def delete_secret(key):
        data = SecretStore._load(); data.pop(str(key or ""), None); SecretStore._save(data)
