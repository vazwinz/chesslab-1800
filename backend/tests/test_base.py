"""Base platform: chess legality, puzzle import, engine communication, persistence, API."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import chess
from sqlalchemy import func, select

from app.models import Puzzle, PuzzleTheme
from app.services import puzzles
from app.services.importer import import_puzzles, validate_puzzle

from .conftest import PUZZLE_FIXTURE, needs_engine


# ------------------------------------------------------------- legality
def test_special_moves_are_legal_via_python_chess():
    b = chess.Board("r3k2r/8/8/3pP3/8/8/8/R3K2R w KQkq d6 0 1")
    assert chess.Move.from_uci("e1g1") in b.legal_moves  # castling
    assert chess.Move.from_uci("e5d6") in b.legal_moves  # en passant
    b2 = chess.Board("8/4P3/8/8/8/8/k7/4K3 w - - 0 1")
    assert chess.Move.from_uci("e7e8n") in b2.legal_moves  # under-promotion
    assert not validate_puzzle(chess.STARTING_FEN, ["e2e4", "e7e5", "e1e3"])  # king can't jump


def test_fixture_import_streams_validates_and_is_incremental(db):
    job = import_puzzles(db, PUZZLE_FIXTURE)
    assert job.status == "done"
    assert job.invalid == 1  # the deliberately illegal row
    assert job.inserted >= 40
    n = db.execute(select(func.count()).select_from(Puzzle)).scalar()
    assert n == job.inserted
    assert db.execute(select(func.count()).select_from(PuzzleTheme)).scalar() > n
    job2 = import_puzzles(db, PUZZLE_FIXTURE)  # re-run: updates, no duplicates
    assert job2.inserted == 0 and job2.updated == n
    assert db.execute(select(func.count()).select_from(Puzzle)).scalar() == n


def test_every_imported_solution_is_legally_executable(puzzles_db):
    for p in puzzles_db.execute(select(Puzzle)).scalars():
        assert validate_puzzle(p.fen, p.moves.split()), p.id
        st = puzzles.puzzle_start(p)
        b = chess.Board(st["fen"])
        for mv in puzzles.solution_moves(p):
            assert chess.Move.from_uci(mv) in b.legal_moves
            b.push(chess.Move.from_uci(mv))


def test_import_script_refuses_test_fixture(tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "import_puzzles.py"
    r = subprocess.run([sys.executable, str(script), str(PUZZLE_FIXTURE), "--database-url",
                        f"sqlite:///{(tmp_path / 'x.db').as_posix()}"], capture_output=True, text=True)
    assert r.returncode == 2 and "TEST_ONLY" in r.stderr


def test_selection_respects_rating_theme_and_recent(puzzles_db):
    p = puzzles.select_puzzle(puzzles_db, 800, 3000)
    assert p is not None
    theme = p.themes.split()[0]
    q = puzzles.select_puzzle(puzzles_db, 800, 3000, themes=[theme])
    assert theme in q.themes.split()
    all_ids = {x.id for x in puzzles_db.execute(select(Puzzle)).scalars()}
    assert puzzles.select_puzzle(puzzles_db, 0, 4000, exclude=all_ids, widen=False) is None


def test_check_user_move_accepts_solution_and_rejects_others(puzzles_db):
    p = puzzles_db.execute(select(Puzzle)).scalars().first()
    sol = puzzles.solution_moves(p)
    r = puzzles.check_user_move(p, 0, [], sol[0])
    assert r["legal"] and r["correct"]
    st = puzzles.puzzle_start(p)
    b = chess.Board(st["fen"])
    wrong = next(m.uci() for m in b.legal_moves if m.uci() != sol[0] and not _mates(b, m))
    r2 = puzzles.check_user_move(p, 0, [], wrong)
    assert r2["legal"] and not r2["correct"]
    assert puzzles.check_user_move(p, 0, [], "a1a1")["legal"] is False


def _mates(b, m):
    c = b.copy()
    c.push(m)
    return c.is_checkmate()


# ------------------------------------------------------------- engine
@needs_engine
def test_stockfish_answers_over_uci():
    from app.services.engine import StockfishService

    eng = StockfishService()
    try:
        b = chess.Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
        lines = eng.analyse(b, depth=10, multipv=2)
        assert lines[0].move == "a1a8" and lines[0].mate == 1
        assert len(lines) == 2 and lines[0].pv_san[0] == "Ra8#"
        cmp = eng.compare_move(b, chess.Move.from_uci("a1a2"), depth=10)
        assert cmp["verdict"] in ("blunder", "mistake") and not cmp["is_best"]
        assert eng.status()["ok"] and "Stockfish" in eng.status()["name"]
    finally:
        eng.close()


@needs_engine
def test_engine_api_and_cache(client):
    body = {"fen": "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", "depth": 8, "multipv": 1}
    r1 = client.post("/api/engine/analyse", json=body).json()
    assert r1["lines"][0]["move"] == "a1a8" and r1["cached"] is False
    r2 = client.post("/api/engine/analyse", json=body).json()
    assert r2["cached"] is True
    assert client.post("/api/engine/analyse", json={"fen": "not a fen"}).status_code == 422
    assert client.get("/api/health").json()["engine"]["ok"]


def test_engine_missing_gives_clear_error():
    from app.services.engine import EngineUnavailable, StockfishService

    eng = StockfishService(path="/nonexistent/stockfish")
    try:
        eng.analyse(chess.Board())
        raise AssertionError("should fail")
    except EngineUnavailable as exc:
        assert "STOCKFISH_PATH" in str(exc)


# ------------------------------------------------------------- API + persistence
@needs_engine
def test_solve_flow_and_persistence_after_restart(client_with_puzzles, db_url):
    c = client_with_puzzles
    sid = c.post("/api/sessions", json={"kind": "mixed"}).json()["id"]
    ex = c.post(f"/api/sessions/{sid}/next").json()
    assert not {"solution_uci", "solution_san", "moves"} & set(ex)  # the answer never goes to the client
    from app import db as dbmod

    with dbmod.SessionLocal() as s:
        p = s.get(Puzzle, ex["puzzle_id"])
        sol = puzzles.solution_moves(p)
    res = None
    for i in range(0, len(sol), 2):
        res = c.post(f"/api/attempts/{ex['attempt_id']}/move", json={"uci": sol[i], "elapsed_ms": 4000}).json()
    assert res["finished"] and res["correct"]
    assert res["rating"]["after"] > res["rating"]["before"]
    # "restart": a brand-new app instance on the same database file
    from fastapi.testclient import TestClient

    from app.main import app

    dbmod.configure(db_url)
    with TestClient(app) as c2:
        d = c2.get("/api/dashboard").json()
        assert d["totals"]["attempts"] == 1 and d["totals"]["solved"] == 1
        assert d["rating"]["current"] == res["rating"]["after"]


def test_api_validation(client):
    assert client.post("/api/sessions", json={"kind": "nonsense"}).status_code == 422
    assert client.post("/api/attempts/999/move", json={"uci": "e2e4"}).status_code == 404
    sid = client.post("/api/sessions", json={"kind": "mixed"}).json()["id"]
    r = client.post(f"/api/sessions/{sid}/next")
    assert r.status_code == 409 and "Importe" in r.json()["detail"]  # empty DB: no fake puzzles


def test_dashboard_empty_has_no_fabricated_numbers(client):
    d = client.get("/api/dashboard").json()
    assert d["has_data"] is False
    assert d["totals"]["attempts"] == 0 and d["totals"]["accuracy"]["rate"] is None
    assert d["rating"]["series"] == []


def test_plan_and_openings(client):
    p = client.get("/api/plan/today").json()
    assert sum(b["minutes"] for b in p["blocks"]) == 180
    bid = p["blocks"][0]["id"]
    p2 = client.post(f"/api/plan/blocks/{bid}", json={"completed": True}).json()
    assert p2["blocks"][0]["completed"]
    assert client.get("/api/plan/consistency").json()["streak_days"] == 1
    light = client.post("/api/plan/today/regenerate", json={"light": True}).json()
    assert light["blocks"]  # completed block is kept, nothing silently deleted
    rid = client.post("/api/openings", json={"name": "Italian", "color": "white"}).json()["id"]
    line = client.post(f"/api/openings/{rid}/lines", json={"name": "Main", "moves": "1. e4 e5 2. Nf3 Nc6 3. Bc4"}).json()
    assert line["moves_san"] == ["e4", "e5", "Nf3", "Nc6", "Bc4"]
    assert client.post(f"/api/openings/{rid}/lines", json={"name": "bad", "moves": "1. e4 e5 2. Ke3"}).status_code == 422
    d = client.post(f"/api/openings/lines/{line['id']}/drill", json={"ply": 2, "uci": "b1c3"}).json()
    assert d["correct"] is False and d["expected_san"] == "Nf3"
    assert client.get("/api/openings/mistakes").json()[0]["expected_san"] == "Nf3"


@needs_engine
def test_endgame_positions_and_engine_reply(client):
    from app.services.endgames import POSITIONS, validate_positions

    assert validate_positions() == []
    pos = next(p for p in POSITIONS if p["id"] == "kq_k")
    r = client.post("/api/endgames/move", json={"position_id": "kq_k", "fen": pos["fen"], "uci": "h1h5", "depth": 8}).json()
    assert r["move"] and chess.Board(r["fen"]).turn == chess.WHITE


def test_incremental_import_updates_ratings_and_themes(db, tmp_path):
    import csv
    import io

    import zstandard

    import_puzzles(db, PUZZLE_FIXTURE)
    text = zstandard.ZstdDecompressor().decompress(PUZZLE_FIXTURE.read_bytes(), max_output_size=10**7).decode()
    rows = list(csv.reader(io.StringIO(text)))
    rows[1][3] = "2345"           # new rating in a newer dump
    rows[1][7] = "fork short"     # changed themes
    rows[2][3] = "999"            # rating only
    newer = tmp_path / "newer_dump.csv"
    with open(newer, "w", newline="") as fh:
        csv.writer(fh).writerows(rows[:3])
    job = import_puzzles(db, newer)
    assert job.updated == 2 and job.inserted == 0
    db.expire_all()
    p1, p2 = db.get(Puzzle, rows[1][0]), db.get(Puzzle, rows[2][0])
    assert p1.rating == 2345 and p1.themes == "fork short" and p2.rating == 999
    themes = {t.theme: t.rating for t in db.execute(select(PuzzleTheme).where(PuzzleTheme.puzzle_id == p1.id)).scalars()}
    assert themes == {"fork": 2345, "short": 2345}
    assert {t.rating for t in db.execute(select(PuzzleTheme).where(PuzzleTheme.puzzle_id == p2.id)).scalars()} == {999}
