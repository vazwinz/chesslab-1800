"""New-version notice: asks GitHub Releases of the public repository for the latest release.

Never raises: offline, timeouts, a private/missing repository or GitHub's rate limit all end
in {"available": False, ...}. Results are cached in the database (6 h after a success,
30 min after a failure) so opening the app does not wait on the network."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..models import KV
from ..version import __version__
from . import prefs

CACHE_KEY = "update_check"
OK_TTL, FAIL_TTL = timedelta(hours=6), timedelta(minutes=30)
TIMEOUT_S = 4.0
ASSET_RE = re.compile(r"^AURA-Setup-.*\.exe$", re.IGNORECASE)


def parse_version(v: str | None) -> tuple[int, ...] | None:
    m = re.match(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?", v or "")
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fetch(repo: str) -> dict:
    import httpx

    r = httpx.get(f"https://api.github.com/repos/{repo}/releases/latest", timeout=TIMEOUT_S,
                  headers={"Accept": "application/vnd.github+json", "User-Agent": f"AURA/{__version__}"},
                  follow_redirects=True)
    if r.status_code == 404:
        return {"ok": False, "error": "nenhuma versão publicada (ou repositório privado)"}
    if r.status_code in (403, 429):
        return {"ok": False, "error": "limite de consultas do GitHub; tento de novo mais tarde"}
    r.raise_for_status()
    j = r.json()
    if j.get("draft") or j.get("prerelease"):
        return {"ok": False, "error": "a última versão é de teste"}
    asset = next((a for a in j.get("assets") or [] if ASSET_RE.match(a.get("name", ""))), None)
    return {"ok": True, "latest": (j.get("tag_name") or "").lstrip("vV"), "name": j.get("name") or j.get("tag_name"),
            "page_url": j.get("html_url"), "download_url": (asset or {}).get("browser_download_url") or j.get("html_url"),
            "published_at": j.get("published_at"), "notes": (j.get("body") or "")[:2000]}


def check(db: Session, force: bool = False, fetch=_fetch) -> dict:
    base = {"current": __version__, "available": False, "repo": settings.update_repo}
    if not settings.update_repo or not prefs.get_prefs(db).get("update_check", True):
        return {**base, "enabled": False}
    kv = db.get(KV, CACHE_KEY)
    cached = dict(kv.value) if kv else None
    if cached and not force:
        try:
            age = _now() - datetime.fromisoformat(cached["checked_at"])
            if age < (OK_TTL if cached.get("ok") else FAIL_TTL) and cached.get("for_version") == __version__:
                return _result(base, cached)
        except (KeyError, ValueError):
            pass
    try:
        res = fetch(settings.update_repo)
    except Exception as exc:  # offline, DNS, TLS, timeout, bad JSON...
        res = {"ok": False, "error": "sem conexão com o GitHub", "exception": type(exc).__name__}
    res = {**res, "checked_at": _now().isoformat(), "for_version": __version__}
    if kv is None:
        db.add(KV(key=CACHE_KEY, value=res))
    else:
        kv.value = res
    db.commit()
    return _result(base, res)


def _result(base: dict, res: dict) -> dict:
    out = {**base, "enabled": True, "checked_at": res.get("checked_at"), "ok": bool(res.get("ok"))}
    if not res.get("ok"):
        return {**out, "error": res.get("error")}
    latest, cur = parse_version(res.get("latest")), parse_version(__version__)
    available = bool(latest and cur and latest > cur)
    return {**out, "available": available, "latest": res.get("latest"), "download_url": res.get("download_url"),
            "page_url": res.get("page_url"), "notes": res.get("notes") if available else None}
