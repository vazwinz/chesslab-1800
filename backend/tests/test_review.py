"""Game review: what analyze_game stores (criteria, highlights, Lichess accuracy) and that a game can
be analysed again after its mistakes became training exercises."""
from __future__ import annotations

import io

import chess
import chess.pgn
import pytest

from app.models import Attempt, Game, GameMistake
from app.services import judgement
from app.services.engine import StockfishService
from app.services.games import analyze_game, import_pgn

from .conftest import PGN_FIXTURE, needs_engine

SMOTHERED_PGN = """[Event "TEST-ONLY"]
[White "TestUser"]
[Black "Opponent"]
[Result "1-0"]
[SetUp "1"]
[FEN "5r1k/6pp/7N/3Q4/8/8/8/6K1 w - - 0 1"]

1. Qg8+ Rxg8 2. Nf7# 1-0
"""


@pytest.fixture()
def eng():
    e = StockfishService(threads=1)
    yield e
    e.close()


def _first_game(db) -> Game:
    gid = import_pgn(db, PGN_FIXTURE.read_text(), player_names=["TestUser"])["game_ids"][0]
    return db.get(Game, gid)


@needs_engine
def test_the_smothered_mate_sacrifice_is_stored_as_brilliant(db, eng):
    gid = import_pgn(db, SMOTHERED_PGN, player_names=["TestUser"])["game_ids"][0]
    m = analyze_game(db, db.get(Game, gid), eng, depth=12)
    assert m["criteria"] == judgement.CRITERIA
    assert [(h["ply"], h["kind"], h["san"]) for h in m["highlights"]] == [(0, "brilliant", "Qg8+")]
    assert m["brilliant"] == 1 and m["accuracy"] == 100.0


@needs_engine
def test_analysis_keeps_the_curve_think_times_and_refutation(db, eng):
    g = _first_game(db)  # TestUser has White; the fixture has clock comments on every move
    plies = len(list(chess.pgn.read_game(io.StringIO(g.pgn)).mainline()))
    m = analyze_game(db, g, eng, depth=8)
    assert len(m["wins"]) == plies + 1
    assert all(w is not None and 0 <= w <= 100 for w in m["wins"])
    assert isinstance(m["think"][2], float)  # White's second move, with a clock
    assert m["think"][1] is None  # Black's move: not yours
    assert set(m["phase_accuracy"]) == {"opening", "middlegame", "endgame"}
    assert m["deep"] == "pending"  # depth 8 is below the review depth
    ms = db.query(GameMistake).filter(GameMistake.game_id == g.id).all()
    assert ms and all(x.detail["refutation"][0] == x.move_uci for x in ms)


@needs_engine
def test_a_game_can_be_analysed_again_after_its_mistakes_became_exercises(db, eng):
    g = _first_game(db)
    analyze_game(db, g, eng, depth=8)
    m = db.query(GameMistake).filter(GameMistake.game_id == g.id).order_by(GameMistake.ply).first()
    assert m is not None
    db.add(Attempt(exercise_kind="game_position", game_mistake_id=m.id))
    db.commit()
    kept_id, kept_ply = m.id, m.ply
    analyze_game(db, g, eng, depth=8)  # used to fail: deleting a row an attempt points to
    again = db.get(GameMistake, kept_id)
    assert again is not None and again.ply == kept_ply and again.severity != "retired"


@needs_engine
def test_a_trained_position_that_is_no_longer_an_error_is_retired_and_hidden(db, eng):
    from app.routers.core import games_detail

    g = _first_game(db)
    analyze_game(db, g, eng, depth=8)
    # pretend the first move (1. Nf3, a fine move) had been stored as an error and trained
    b = chess.Board()
    fake = GameMistake(game_id=g.id, ply=0, fen_before=b.fen(), move_uci="g1f3", move_san="Nf3", best_uci="e2e4",
                       best_san="e4", eval_before_cp=30, eval_after_cp=20, cp_loss=10, win_pct_loss=6.0,
                       severity="inaccuracy", phase="opening", category="positional_misunderstanding", detail={}, pv=[])
    db.add(fake)
    db.flush()
    db.add(Attempt(exercise_kind="game_position", game_mistake_id=fake.id))
    db.commit()
    analyze_game(db, g, eng, depth=8)
    row = db.get(GameMistake, fake.id)
    assert row is not None and row.severity == "retired"
    assert all(x["ply"] != 0 for x in games_detail(g.id, db)["mistakes"])


def test_games_analysed_with_older_criteria_are_flagged_and_queued_again(client, monkeypatch):
    from app import db as dbmod
    from app.services import game_jobs

    queued: list[int] = []
    monkeypatch.setattr(game_jobs, "enqueue_analysis", lambda ids, depth=None: queued.extend(ids) or {"status": "running"})
    with dbmod.SessionLocal() as s:
        old = Game(fingerprint="old", pgn="", white="TestUser", black="X", result="1-0", user_color="white",
                   analyzed=True, metrics={"accuracy": 80})
        new = Game(fingerprint="new", pgn="", white="TestUser", black="Y", result="1-0", user_color="white",
                   analyzed=True, metrics={"accuracy": 80, "criteria": judgement.CRITERIA})
        never = Game(fingerprint="never", pgn="", white="TestUser", black="Z", result="1-0", user_color="white")
        s.add_all([old, new, never])
        s.commit()
        ids = {"old": old.id, "new": new.id, "never": never.id}
    stale = {g["id"]: g["stale"] for g in client.get("/api/games").json()}
    assert stale == {ids["old"]: True, ids["new"]: False, ids["never"]: False}
    r = client.post("/api/games/reanalyze-stale").json()
    assert queued == [ids["old"]] and r["count"] == 1
