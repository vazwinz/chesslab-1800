"""Central configuration. Every value can be overridden with an environment variable
(or a `.env`-style file loaded by your shell). See docs/CONFIGURATION.md."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _default_stockfish() -> str:
    for name in ("stockfish", "stockfish.exe"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in ("/usr/games/stockfish", "/usr/local/bin/stockfish", "/opt/homebrew/bin/stockfish"):
        if Path(candidate).exists():
            return candidate
    return "stockfish"


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _data_dir() -> str:
    return os.getenv("CHESSLAB_DATA_DIR", str(BACKEND_DIR / "data"))


@dataclass
class Settings:
    data_dir: str = field(default_factory=_data_dir)
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{(Path(_data_dir()) / 'chesslab.db').as_posix()}")
    )
    stockfish_path: str = field(default_factory=lambda: os.getenv("STOCKFISH_PATH", _default_stockfish()))
    engine_default_depth: int = field(default_factory=lambda: int(os.getenv("ENGINE_DEPTH", "16")))
    engine_max_depth: int = field(default_factory=lambda: int(os.getenv("ENGINE_MAX_DEPTH", "30")))
    engine_max_time: float = field(default_factory=lambda: float(os.getenv("ENGINE_MAX_TIME", "10")))
    # threads for the analysis-board/coach engine; 0 = automatic (half the CPU cores, at most 4)
    engine_threads: int = field(default_factory=lambda: int(os.getenv("ENGINE_THREADS", "0")))
    engine_hash_mb: int = field(default_factory=lambda: int(os.getenv("ENGINE_HASH_MB", "64")))
    # depth used when classifying mistakes in imported games (lower = faster import)
    game_analysis_depth: int = field(default_factory=lambda: int(os.getenv("GAME_ANALYSIS_DEPTH", "12")))
    # names/usernames that identify YOU in imported PGNs (comma separated)
    player_names: list[str] = field(default_factory=lambda: _list(os.getenv("CHESSLAB_PLAYER_NAMES", "")))
    cors_origins: list[str] = field(
        default_factory=lambda: _list(os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"))
    )
    # Host headers the server answers to (anything else is refused: protects against DNS rebinding)
    allowed_hosts: list[str] = field(
        default_factory=lambda: _list(os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost,::1,testserver"))
    )
    frontend_dist: Path = field(
        default_factory=lambda: Path(os.getenv("FRONTEND_DIST", str(BACKEND_DIR.parent / "frontend" / "dist")))
    )
    # depth Stockfish uses for the "Explicar" coach (rules and optional AI both start from these facts)
    coach_depth: int = field(default_factory=lambda: int(os.getenv("COACH_DEPTH", "18")))
    # public GitHub repository whose Releases announce new versions (empty = never check)
    update_repo: str = field(default_factory=lambda: os.getenv("AURA_UPDATE_REPO", "vazwinz/chesslab-1800"))


settings = Settings()
