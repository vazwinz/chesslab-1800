"""Jogar contra o computador: levels, the computer's move, the judge, the rating that follows you and
saving finished games (analysed like any other, without touching your real rating)."""
from __future__ import annotations

import random

import chess
import pytest

from app.services import game_jobs, play
from app.services.engine import StockfishService

from .conftest import needs_engine

AFTER_NF3 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"  # 1.e4 e5 2.Nf3, Black to move
BACK_RANK = "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"  # Rd8# is mate in one
SCHOLAR = ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"]


@pytest.fixture(scope="module")
def eng():
    svc = StockfishService(threads=1, hash_mb=32, role="play")
    yield svc
    svc.close()


@pytest.fixture()
def no_analysis(monkeypatch):
    queued = []
    monkeypatch.setattr(game_jobs, "enqueue_analysis", lambda ids, depth=None: queued.extend(ids) or {})
    return queued


def test_strength_grows_with_the_level():
    low, high = play.strength(400), play.strength(2500)
    assert low["depth"] == 2 and low["blunder"] > 0.15 and low["multipv"] > 1
    assert high["depth"] == 16 and high["blunder"] == 0 and high["multipv"] == 1
    temps = [play.strength(e)["temperature"] for e, _ in play.LEVELS]
    assert temps == sorted(temps, reverse=True), "higher levels tolerate smaller losses"
    assert play.strength(1400)["blunder"] == 0, "no random blunders from ~1350 up"


def test_levels_names_and_the_automatic_level():
    assert play.level_name(400) == "Iniciante" and play.level_name(1010) == "Clube" and play.level_name(2600) == "Grande mestre"
    assert play.suggested_level(1012) == 1000 and play.suggested_level(1030) == 1050
    assert play.suggested_level(100) == 400 and play.suggested_level(4000) == 2500


@needs_engine
def test_the_computer_plays_legal_moves_at_every_level(eng):
    board = chess.Board(AFTER_NF3)
    for elo in (400, 800, 1200, 1600, 2000, 2500):
        for seed in range(3):
            r = play.engine_move(eng, board, elo, random.Random(seed))
            assert chess.Move.from_uci(r["move"]) in board.legal_moves, (elo, r)


@needs_engine
def test_the_top_level_finds_mate_and_low_levels_sometimes_do_not_play_the_best_move(eng):
    board = chess.Board(BACK_RANK)
    assert play.engine_move(eng, board, 2500, random.Random(1))["move"] == "d1d8"
    start = chess.Board()
    picks = {play.engine_move(eng, start, 400, random.Random(s))["move"] for s in range(12)}
    assert len(picks) >= 3, "a 400-level opponent is not a deterministic best-move machine"


@needs_engine
def test_judge_flags_a_hung_queen_and_names_the_punishment(eng):
    board = chess.Board(AFTER_NF3)
    j = play.judge(eng, board, chess.Move.from_uci("d8h4"))
    assert j["verdict"] == "blunder" and j["user_san"] == "Qh4" and j["reply_uci"] == "f3h4"
    assert j["win_pct_loss"] >= 30 and j["best_uci"] != "d8h4"
    ok = play.judge(eng, board, chess.Move.from_uci(j["best_uci"]))
    assert ok["verdict"] == "best" and ok["win_pct_loss"] == 0


def test_a_win_raises_your_level_and_a_helped_game_does_not_count(client, no_analysis):
    st = client.get("/api/play/state").json()
    assert st["rating"] == 800 and st["games"] == 0 and st["suggested_level"] == 800
    assert [lv["elo"] for lv in st["levels"]][0] == 400
    r = client.post("/api/play/finish", json={"start_fen": chess.STARTING_FEN, "moves": SCHOLAR, "user_color": "white",
                                               "level": 800, "result": "1-0", "reason": "xeque-mate"}).json()
    assert r["rated"] and r["score"] == 1.0 and r["rating_after"] > r["rating_before"] and r["next_level"] > 800
    assert no_analysis == [r["game_id"]], "the game goes to the analysis queue like any other"
    helped = client.post("/api/play/finish", json={"start_fen": chess.STARTING_FEN, "moves": ["e2e4", "e7e5"],
                                                    "user_color": "white", "level": 800, "result": "0-1",
                                                    "reason": "abandono", "helped": True}).json()
    assert not helped["rated"] and helped["rating_after"] == r["rating_after"]
    st = client.get("/api/play/state").json()
    assert st["games"] == 1 and st["wins"] == 1 and len(st["history"]) == 1


def test_a_finished_game_is_saved_for_review_without_your_rating(client, no_analysis):
    r = client.post("/api/play/finish", json={"start_fen": chess.STARTING_FEN, "moves": SCHOLAR, "user_color": "black",
                                               "level": 1200, "result": "1-0", "reason": "xeque-mate",
                                               "time_control": "600+5", "opening": "Italiana"}).json()
    g = client.get(f"/api/games/{r['game_id']}").json()
    assert g["black"] == "Você" and g["white"] == "AURA 1200 (Intermediário)" and g["user_color"] == "black"
    assert g["user_elo"] is None and g["opponent_elo"] == 1200, "only the computer's rating is recorded"
    assert g["moves_uci"] == SCHOLAR and g["time_class"] == "rapid" and r["score"] == 0.0
    listed = next(x for x in client.get("/api/games").json() if x["id"] == r["game_id"])
    assert listed["source"] == "aura"


def test_finish_refuses_illegal_games(client, no_analysis):
    r = client.post("/api/play/finish", json={"start_fen": chess.STARTING_FEN, "moves": ["e2e5"], "user_color": "white",
                                               "level": 800, "result": "0-1"})
    assert r.status_code == 422
    assert client.post("/api/play/finish", json={"start_fen": chess.STARTING_FEN, "moves": [], "user_color": "white",
                                                  "level": 300, "result": "0-1"}).status_code == 422


def test_starts_offer_openings_endgames_and_your_mistakes(client):
    s = client.get("/api/play/starts").json()
    assert len(s["openings"]) >= 10 and all(chess.Board(o["fen"]).is_valid() for o in s["openings"])
    assert any(o["name"] == "Siciliana" for o in s["openings"]) and len(s["endgames"]) >= 5
    assert s["mistakes"] == [] and s["repertoire"] == []


@needs_engine
def test_move_and_judge_endpoints(client):
    r = client.post("/api/play/move", json={"fen": AFTER_NF3, "level": 1600}).json()
    assert chess.Move.from_uci(r["move"]) in chess.Board(AFTER_NF3).legal_moves
    j = client.post("/api/play/judge", json={"fen": AFTER_NF3, "move": "d8h4"}).json()
    assert j["verdict"] == "blunder"
    assert client.post("/api/play/judge", json={"fen": AFTER_NF3, "move": "e2e4"}).status_code == 422
    mate = "6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1"
    assert client.post("/api/play/move", json={"fen": "3R2k1/5ppp/8/8/8/8/5PPP/6K1 b - - 1 1", "level": 800}).status_code == 409
    assert client.post("/api/play/move", json={"fen": mate, "level": 9000}).status_code == 422


def test_play_preferences(client):
    p = client.get("/api/prefs").json()
    assert p["play_alarm"] == "forte" and p["play_hints"] == 3 and p["play_auto_level"] is True
    assert client.put("/api/prefs", json={"play_alarm": "gritar"}).status_code == 422
    p = client.put("/api/prefs", json={"play_hints": 9, "play_level": 50, "play_clock": "10+5"}).json()
    assert p["play_hints"] == 5 and p["play_level"] == 400 and p["play_clock"] == "10+5"
