"""New-version notice: asks GitHub Releases of the public repository for the latest release.

Never raises: offline, timeouts, a private/missing repository or GitHub's rate limit all end
in {"available": False, ...}. Results are cached in the database (6 h after a success,
30 min after a failure) so opening the app does not wait on the network.

The result also says which file of the release fits this computer (`download_url`: the Windows
installer, the Linux tarball, or the release page elsewhere) and, under `install`, whether this
copy can update itself in place ("Atualizar agora", see updater.py)."""
from __future__ import annotations

import os
import platform as _platform
import re
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..models import KV
from ..version import __version__
from . import prefs

CACHE_KEY = "update_check"
OK_TTL, FAIL_TTL = timedelta(hours=6), timedelta(minutes=30)
TIMEOUT_S = 4.0
WINDOWS_ASSET = re.compile(r"^AURA-Setup-[0-9][\w.\-]*\.exe$", re.IGNORECASE)
LINUX_ASSET = re.compile(r"^AURA-linux-x64\.tar\.gz$", re.IGNORECASE)
SUMS_ASSET = "SHA256SUMS"
GITHUB_API = "https://api.github.com"


def parse_version(v: str | None) -> tuple[int, ...] | None:
    m = re.match(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?", v or "")
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def api_base() -> str:
    """GitHub's API, or a stand-in for tests (AURA_UPDATE_API, e.g. a local server)."""
    return (os.getenv("AURA_UPDATE_API") or GITHUB_API).rstrip("/")


def allowed_download(url: str | None, repo: str) -> bool:
    """Files are only downloaded from the repository's own releases (or the test stand-in)."""
    if not url:
        return False
    if os.getenv("AURA_UPDATE_API"):
        return url.startswith(api_base() + "/")
    return url.startswith(f"https://github.com/{repo}/releases/download/")


def pick_asset(assets: list[dict], platform: str | None = None, machine: str | None = None) -> dict | None:
    """The release file for this computer: the installer on Windows, the tarball on 64-bit
    Intel/AMD Linux, nothing elsewhere (macOS and ARM Linux have no build)."""
    platform = sys.platform if platform is None else platform
    machine = (_platform.machine() if machine is None else machine).lower()
    if platform == "win32":
        rx = WINDOWS_ASSET
    elif platform.startswith("linux") and machine in ("x86_64", "amd64"):
        rx = LINUX_ASSET
    else:
        return None
    return next((a for a in assets if rx.match(a.get("name") or "")), None)


def _fetch(repo: str) -> dict:
    import httpx

    r = httpx.get(f"{api_base()}/repos/{repo}/releases/latest", timeout=TIMEOUT_S,
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
    assets = [{"name": a.get("name"), "url": a.get("browser_download_url"), "size": a.get("size")}
              for a in j.get("assets") or []]
    return {"ok": True, "latest": (j.get("tag_name") or "").lstrip("vV"), "name": j.get("name") or j.get("tag_name"),
            "page_url": j.get("html_url"), "assets": assets,
            "published_at": j.get("published_at"), "notes": (j.get("body") or "")[:2000]}


def check(db: Session, force: bool = False, fetch=None) -> dict:
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
        res = (fetch or _fetch)(settings.update_repo)
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
    from . import updater

    out = {**base, "enabled": True, "checked_at": res.get("checked_at"), "ok": bool(res.get("ok")),
           "last_attempt": updater.last_attempt()}
    if not res.get("ok"):
        return {**out, "error": res.get("error")}
    latest, cur = parse_version(res.get("latest")), parse_version(__version__)
    available = bool(latest and cur and latest > cur)
    assets = res.get("assets") or []
    asset = pick_asset(assets)
    if asset and not allowed_download(asset.get("url"), settings.update_repo):
        asset = None
    sums = next((a for a in assets if a.get("name") == SUMS_ASSET), None)
    if sums and not allowed_download(sums.get("url"), settings.update_repo):
        sums = None
    install = updater.install_offer(available, asset, sums)
    return {**out, "available": available, "latest": res.get("latest"),
            "download_url": (asset or {}).get("url") or res.get("page_url"),
            "page_url": res.get("page_url"), "notes": res.get("notes") if available else None,
            "install": install}
