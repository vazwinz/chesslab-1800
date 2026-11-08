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


@dataclass
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{(BACKEND_DIR / 'data' / 'chesslab.db').as_posix()}")
    )
    stockfish_path: str = field(default_factory=lambda: os.getenv("STOCKFISH_PATH", _default_stockfish()))
    engine_default_depth: int = field(default_factory=lambda: int(os.getenv("ENGINE_DEPTH", "16")))
    engine_max_depth: int = field(default_factory=lambda: int(os.getenv("ENGINE_MAX_DEPTH", "30")))
    engine_max_time: float = field(default_factory=lambda: float(os.getenv("ENGINE_MAX_TIME", "10")))
    engine_threads: int = field(default_factory=lambda: int(os.getenv("ENGINE_THREADS", "1")))
    engine_hash_mb: int = field(default_factory=lambda: int(os.getenv("ENGINE_HASH_MB", "64")))
    # depth used when classifying mistakes in imported games (lower = faster import)
    game_analysis_depth: int = field(default_factory=lambda: int(os.getenv("GAME_ANALYSIS_DEPTH", "12")))
    # names/usernames that identify YOU in imported PGNs (comma separated)
    player_names: list[str] = field(default_factory=lambda: _list(os.getenv("CHESSLAB_PLAYER_NAMES", "")))
    cors_origins: list[str] = field(
        default_factory=lambda: _list(os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"))
    )
    frontend_dist: Path = field(
        default_factory=lambda: Path(os.getenv("FRONTEND_DIST", str(BACKEND_DIR.parent / "frontend" / "dist")))
    )
    # Optional AI coach adapter (disabled unless configured)
    coach_provider: str = field(default_factory=lambda: os.getenv("COACH_PROVIDER", "none"))
    coach_api_key: str = field(default_factory=lambda: os.getenv("COACH_API_KEY", ""))
    coach_model: str = field(default_factory=lambda: os.getenv("COACH_MODEL", ""))
    coach_base_url: str = field(default_factory=lambda: os.getenv("COACH_BASE_URL", ""))


settings = Settings()
