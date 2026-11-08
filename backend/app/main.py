from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .routers import cognitive, core


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # creates tables only; puzzle import is a separate command (scripts/import_puzzles.py)
    yield
    from .services.engine import get_engine

    get_engine().close()


app = FastAPI(title="ChessLab 1800", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(core.router)
app.include_router(cognitive.router)

# Serve the built frontend (npm run build) from the same server when present.
dist = settings.frontend_dist
if (dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = dist / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(dist / "index.html")
