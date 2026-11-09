"""Download your games from Chess.com's public API (no login, no key): the list of monthly
archives, then each month as PGN. https://www.chess.com/news/view/published-data-api"""
from __future__ import annotations

import re

from ..version import __version__

API = "https://api.chess.com/pub/player/{user}/games/archives"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,40}$")
TIMEOUT_S = 30.0


class ChessComError(RuntimeError):
    pass


def _client():
    import httpx

    return httpx.Client(timeout=httpx.Timeout(TIMEOUT_S, connect=8.0), follow_redirects=True,
                        headers={"User-Agent": f"AURA/{__version__} (app de treino de xadrez, uso pessoal)"})


def archives(username: str, api: str | None = None) -> list[str]:
    if not USERNAME_RE.match(username or ""):
        raise ChessComError("nome de usuário inválido")
    with _client() as c:
        r = c.get((api or API).format(user=username.lower()))
        if r.status_code == 404:
            raise ChessComError(f"usuário '{username}' não encontrado no Chess.com")
        r.raise_for_status()
        return list(r.json().get("archives") or [])


def month_pgn(archive_url: str) -> str:
    with _client() as c:
        r = c.get(archive_url.rstrip("/") + "/pgn")
        r.raise_for_status()
        return r.text
