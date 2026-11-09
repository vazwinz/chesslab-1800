"""Today's routine: which steps there are, how they count by themselves, the light day, the days
planned by 0.4.0 and the mistakes of the last games coming back first."""
from __future__ import annotations

from datetime import date, timedelta

import chess
import pytest

from app import db as dbmod
from app.models import Attempt, Game, GameMistake, PlanBlock, TrainingSession, utcnow
from app.services import game_jobs, trainer

ENDGAME = "8/8/8/4k3/8/8/8/3QK3 w - - 0 1"


@pytest.fixture()
def no_analysis(monkeypatch):
    monkeypatch.setattr(game_jobs, "enqueue_analysis", lambda ids, depth=None: {})


def _attempts(kind: str, n: int) -> None:
    with dbmod.SessionLocal() as s:
        sess = TrainingSession(kind=kind)
        s.add(sess)
        s.flush()
        for _ in range(n):
            s.add(Attempt(session_id=sess.id, finished_at=utcnow(), correct=True))
        s.commit()


def _routine(c) -> tuple[dict, dict]:
    r = c.get("/api/routine/today").json()
    return r, {s["key"]: s for s in r["steps"]}


def test_an_empty_database_still_has_the_games(client):
    r, steps = _routine(client)
    assert list(steps) == ["games"] and r["current"] == "games" and not r["finished"]
    assert steps["games"]["target"] == 3 and steps["games"]["to"] == "/jogar" and steps["games"]["unit"] == "partidas"


def test_the_routine_counts_by_itself_and_ends_with_the_games(client_with_puzzles):
    c = client_with_puzzles
    r, steps = _routine(c)
    keys = list(steps)
    assert keys[0] == "loop" and keys[-1] == "games", "no game mistakes yet, nothing due for review"
    assert "own_mistakes" not in keys and "retention" not in keys
    assert steps["loop"]["target"] == 15 and r["current"] == "loop"
    assert r["minutes_left"] == sum(s["minutes"] for s in r["steps"])
    _attempts("loop", 7)
    _attempts("mixed", 9)  # another mode does not count for the loop step
    r, steps = _routine(c)
    assert steps["loop"]["done"] == 7 and not steps["loop"]["completed"]
    _attempts("loop", 8)
    r, steps = _routine(c)
    assert steps["loop"]["completed"] and r["current"] == keys[1]
    assert r["streak_days"] == 1


def test_only_real_games_count(client, no_analysis):
    base = {"start_fen": chess.STARTING_FEN, "user_color": "white", "level": 800, "result": "0-1", "reason": "abandono"}
    assert client.post("/api/play/finish", json={**base, "moves": ["e2e4", "e7e5"]}).status_code == 200
    client.post("/api/play/finish", json={**base, "moves": ["e2e4"]})  # resigned straight away
    client.post("/api/play/finish", json={**base, "start_fen": ENDGAME, "moves": ["d1d2", "e5e4"], "practice": True})
    client.post("/api/play/finish", json={**base, "moves": ["d2d4", "d7d5"], "helped": True})  # a hint: still a game
    r, steps = _routine(client)
    assert steps["games"]["done"] == 2 and not steps["games"]["completed"]
    client.post("/api/play/finish", json={**base, "moves": ["c2c4", "e7e5"]})
    r, steps = _routine(client)
    assert steps["games"]["completed"] and r["finished"] and r["current"] is None


def _mistake() -> None:
    with dbmod.SessionLocal() as s:
        g = Game(fingerprint=f"m-{utcnow().timestamp()}", pgn="", white="Você", black="AURA 800 (Novato)", user_color="white")
        s.add(g)
        s.flush()
        s.add(GameMistake(game_id=g.id, ply=0, fen_before=chess.STARTING_FEN, move_uci="f2f3", move_san="f3", best_uci="e2e4",
                          best_san="e4", eval_before_cp=30, eval_after_cp=-60, cp_loss=90, win_pct_loss=12.0, severity="mistake",
                          phase="opening", category="tactical_blindness"))
        s.commit()


def test_a_light_day_keeps_what_is_done_and_brings_nothing_new(client_with_puzzles):
    c = client_with_puzzles
    first, _ = _routine(c)
    keys = [s["key"] for s in first["steps"]]
    _attempts("loop", 15)
    _mistake()  # a game analysed after the day was planned: its mistake waits for tomorrow
    light = c.post("/api/routine/today/light", json={"light": True}).json()
    steps = {s["key"]: s for s in light["steps"]}
    assert light["light_day"] and steps["loop"]["completed"] and steps["loop"]["target"] == 15
    assert steps["games"]["target"] == 1 and "endgame" not in steps and "openings" not in steps
    assert "own_mistakes" not in steps and list(steps) == ["loop", "games"]
    full = c.post("/api/routine/today/light", json={"light": False}).json()
    assert not full["light_day"] and [s["key"] for s in full["steps"]] == keys
    assert {s["key"]: s for s in full["steps"]}["games"]["target"] == 3


def test_a_day_planned_by_0_4_0_gives_way_to_the_routine(client):
    today = date.today()
    with dbmod.SessionLocal() as s:
        s.add_all([PlanBlock(day=today, key="tactics", title="Padrões táticos", minutes=40, completed=True, completed_at=utcnow()),
                   PlanBlock(day=today, key="games", title="Partidas sérias", minutes=45),
                   PlanBlock(day=today, key="openings", title="Preparação de aberturas", minutes=25),
                   PlanBlock(day=today - timedelta(days=1), key="analysis", title="Análise dos erros", minutes=10, completed=True)])
        s.commit()
    r, steps = _routine(client)
    assert list(steps) == ["games"] and steps["games"]["title"] == "Partidas contra o AURA" and steps["games"]["target"] == 3
    with dbmod.SessionLocal() as s:
        left = sorted(b.title for b in s.query(PlanBlock).filter(PlanBlock.day == today))
    assert left == ["Padrões táticos", "Partidas contra o AURA"], "ticked blocks stay for the calendar, unticked ones go"
    assert client.get("/api/routine/consistency").json()["streak_days"] == 2


def test_the_mistakes_of_the_last_games_come_first(db):
    g = Game(fingerprint="routine-test", pgn="", white="Você", black="AURA 800 (Novato)", user_color="white")
    db.add(g)
    db.flush()
    common = dict(game_id=g.id, ply=0, fen_before=chess.STARTING_FEN, move_uci="f2f3", move_san="f3", best_uci="e2e4",
                  best_san="e4", eval_before_cp=30, eval_after_cp=-60, cp_loss=90, win_pct_loss=12.0, severity="mistake",
                  phase="opening", category="tactical_blindness")
    old = GameMistake(**common, created_at=utcnow() - timedelta(days=10))
    new = GameMistake(**common, created_at=utcnow() - timedelta(hours=20))
    sess = TrainingSession(kind="own_mistakes")
    db.add_all([old, new, sess])
    db.commit()
    ex = trainer._own_mistake(db, sess, "standard")
    assert db.get(Attempt, ex["attempt_id"]).game_mistake_id == new.id
    db.commit()
    assert [m.id for m in trainer.own_mistake_pool(db)] == [old.id], "a position just shown waits three days"
