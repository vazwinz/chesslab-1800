from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app import db as dbmod
from app.config import settings

FIXTURES = Path(__file__).parent / "fixtures"
PUZZLE_FIXTURE = FIXTURES / "TEST_ONLY_lichess_format_puzzles.csv.zst"
PGN_FIXTURE = FIXTURES / "TEST_ONLY_games.pgn"

HAS_ENGINE = bool(shutil.which(settings.stockfish_path) or Path(settings.stockfish_path).exists())
needs_engine = pytest.mark.skipif(not HAS_ENGINE, reason="Stockfish not found (set STOCKFISH_PATH)")


@pytest.fixture()
def db_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    dbmod.configure(url)
    dbmod.init_db()
    yield url


@pytest.fixture()
def db(db_url):
    s = dbmod.SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def puzzles_db(db):
    from app.services.importer import import_puzzles

    import_puzzles(db, PUZZLE_FIXTURE)
    return db


@pytest.fixture()
def client(db_url):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client_with_puzzles(db_url):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.importer import import_puzzles

    with dbmod.SessionLocal() as s:
        import_puzzles(s, PUZZLE_FIXTURE)
    with TestClient(app) as c:
        yield c
