from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .db import init_db
from .i18n import STATUS_TEXT, validation_message
from .routers import cognitive, core, extras
from .security import LocalOnlyMiddleware
from .version import __version__

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # runs the migrations; puzzle import is separate (Configurações / scripts/import_puzzles.py)
    yield
    from .services.engine import close_all

    close_all()


app = FastAPI(title="AURA (ChessLab 1800)", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
# added last = runs first: refuse foreign Host headers (DNS rebinding) and cross-site writes
app.add_middleware(LocalOnlyMiddleware, allowed_hosts=settings.allowed_hosts, allowed_origins=settings.cors_origins)
app.include_router(core.router)
app.include_router(cognitive.router)
app.include_router(extras.router)


# ---------------------------------------------------------------- errors in Portuguese
@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if not detail or detail == STATUS_TEXT.get(exc.status_code, {}).get("en"):
        detail = STATUS_TEXT.get(exc.status_code, {}).get("pt", "Erro")
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    errors = exc.errors()
    return JSONResponse({"detail": validation_message(errors), "errors": [
        {"loc": list(e.get("loc", [])), "type": e.get("type")} for e in errors]}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    log.exception("unexpected error")
    return JSONResponse({"detail": f"Erro inesperado no AURA ({type(exc).__name__}). Os detalhes estão no "
                                   "arquivo aura.log da pasta de dados."}, status_code=500)


# ---------------------------------------------------------------- built frontend
dist = settings.frontend_dist
if (dist / "index.html").exists():
    dist_root = dist.resolve()
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    def _index() -> HTMLResponse:
        html = (dist_root / "index.html").read_text(encoding="utf-8")
        try:  # apply the saved theme before the first paint (no light/dark flash)
            from .db import SessionLocal
            from .services import prefs

            with SessionLocal() as s:
                theme = prefs.get_prefs(s).get("theme")
            if theme in ("light", "dark"):
                html = html.replace("<html ", f'<html data-theme="{theme}" ', 1)
        except Exception:  # database not ready: the page falls back to the system theme
            pass
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404)
        if path:
            try:
                f = (dist_root / path).resolve()
            except (OSError, ValueError):
                f = None
            # only files that really live inside the built frontend (blocks ../, //etc, C:/...)
            if f is not None and f.is_relative_to(dist_root) and f.is_file():
                return FileResponse(f)
        return _index()
