"""Local-only guard for the API server.

AURA serves its UI and API on 127.0.0.1. Two attacks still reach a local server from a web
page you happen to have open in your browser:

* DNS rebinding: evil.example resolves to 127.0.0.1, so the page becomes "same origin" with
  the app and could read responses. Defence: only accept requests whose Host header names
  this machine (127.0.0.1 / localhost / ::1).
* Cross-site requests that need no CORS preflight (a bare POST without a body). Defence:
  any state-changing request that carries an Origin header must come from the app itself
  (same host:port) or from an explicitly allowed dev origin (the Vite server).
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
DEFAULT_HOSTS = ("127.0.0.1", "localhost", "::1", "testserver")


def _hostname(host_header: str) -> str:
    h = host_header.strip().lower()
    if h.startswith("["):  # [::1]:8000
        return h[1:].split("]", 1)[0]
    if h.count(":") == 1:
        return h.split(":", 1)[0]
    return h


class LocalOnlyMiddleware:
    def __init__(self, app, allowed_hosts: tuple[str, ...] | list[str] = DEFAULT_HOSTS,
                 allowed_origins: tuple[str, ...] | list[str] = ()):
        self.app = app
        self.allowed_hosts = {h.lower() for h in allowed_hosts}
        self.allowed_origins = {o.rstrip("/").lower() for o in allowed_origins}

    async def _deny(self, send, status: int, message: str) -> None:
        body = json.dumps({"detail": message}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope.get("headers") or []}
        host = headers.get(b"host", b"").decode("latin-1")
        if _hostname(host) not in self.allowed_hosts:
            return await self._deny(send, 400, "Endereço não permitido: o AURA só aceita conexões deste computador.")
        if scope.get("method", "GET").upper() not in SAFE_METHODS:
            origin = headers.get(b"origin")
            if origin is not None:
                o = origin.decode("latin-1").strip().lower().rstrip("/")
                parts = urlsplit(o)
                same = o != "null" and parts.netloc == host.strip().lower()
                if not same and o not in self.allowed_origins:
                    return await self._deny(send, 403, "Pedido recusado: ele veio de outro site, não do AURA.")
        return await self.app(scope, receive, send)
