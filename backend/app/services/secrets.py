"""Where the optional AI coach's API key lives: only on this computer, in `secrets.json` inside the
AURA data folder, never in the database, the backups or any API response.

On Windows the key is encrypted with DPAPI (CryptProtectData, tied to your Windows user), so a
copy of the file on another PC or account cannot be read. Elsewhere the file is plain JSON
readable only by your user (chmod 600). The key is also bound to the address it was saved for:
if the AI address changes, the key is dropped instead of being sent to the new host."""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from ..config import settings

log = logging.getLogger(__name__)
FILE_NAME = "secrets.json"
_ENTROPY = b"AURA coach api key v1"


def _path() -> Path:
    d = Path(settings.data_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / FILE_NAME


# ------------------------------------------------------------------ Windows DPAPI (ctypes, no deps)
def _dpapi(data: bytes, protect: bool) -> bytes:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(b: bytes):
        buf = ctypes.create_string_buffer(b, len(b))
        return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(BLOB), ctypes.c_void_p, ctypes.POINTER(BLOB), ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(BLOB)]
    fn.restype = wintypes.BOOL
    src, _keep1 = blob(data)
    ent, _keep2 = blob(_ENTROPY)
    out = BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    if not fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise OSError(f"DPAPI falhou (código {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def _encode(key: str) -> dict:
    if sys.platform == "win32":
        try:
            return {"scheme": "dpapi", "value": base64.b64encode(_dpapi(key.encode(), True)).decode()}
        except Exception as exc:  # pragma: no cover - Windows only
            log.warning("DPAPI unavailable, storing the key unencrypted: %s", exc)
    return {"scheme": "plain", "value": key}


def _decode(rec: dict) -> str | None:
    try:
        if rec.get("scheme") == "dpapi":  # pragma: no cover - Windows only
            return _dpapi(base64.b64decode(rec["value"]), False).decode()
        return rec.get("value") or None
    except Exception as exc:
        log.warning("stored API key cannot be read (%s); it must be saved again", exc)
        return None


def _read() -> dict:
    p = _path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    p = _path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    tmp.replace(p)


def origin_of(url: str) -> str:
    u = urlsplit(url.strip())
    return f"{u.scheme.lower()}://{(u.hostname or '').lower()}{':' + str(u.port) if u.port else ''}"


def save_api_key(key: str, base_url: str) -> dict:
    key = key.strip()
    data = _read()
    data["coach_api_key"] = {**_encode(key), "bound_to": origin_of(base_url), "hint": key[-4:] if len(key) >= 8 else "",
                             "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _write(data)
    return key_status(base_url)


def delete_api_key() -> None:
    data = _read()
    if data.pop("coach_api_key", None) is not None:
        _write(data)


def get_api_key(base_url: str) -> str | None:
    """The key, but only for the address it was saved for."""
    rec = _read().get("coach_api_key")
    if not rec or rec.get("bound_to") != origin_of(base_url):
        return None
    return _decode(rec)


def key_status(base_url: str | None = None) -> dict:
    rec = _read().get("coach_api_key")
    if not rec:
        return {"has_key": False}
    usable = base_url is None or rec.get("bound_to") == origin_of(base_url)
    return {"has_key": bool(usable), "hint": rec.get("hint", ""), "bound_to": rec.get("bound_to"),
            "storage": "criptografada com o seu usuário do Windows (DPAPI)" if rec.get("scheme") == "dpapi"
            else "arquivo local, legível só pelo seu usuário", "saved_at": rec.get("saved_at")}
