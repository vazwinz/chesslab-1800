"""The warning of the day: the kind of mistake you missed most in today's session of "Seus erros de
partida", said in one line with the count behind it; the next day it shows again with its trend."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import chess

from app.models import Attempt, Game, GameMistake, utcnow
from app.services import alerts

TODAY = date.today()


def _mistake(db, category: str, played: date = TODAY, fp: str | None = None, criteria: int = 2) -> GameMistake:
    g = Game(fingerprint=fp or f"{category}-{played}-{datetime.now().timestamp()}", pgn="", white="TestUser",
             black="Rival", result="0-1", user_color="white", source="chess.com", played_on=played,
             analyzed=True, metrics={"criteria": criteria})
    db.add(g)
    db.flush()
    m = GameMistake(game_id=g.id, ply=10, fen_before=chess.STARTING_FEN, move_uci="f2f3", move_san="f3",
                    best_uci="e2e4", best_san="e4", eval_before_cp=30, eval_after_cp=-160, cp_loss=190,
                    win_pct_loss=20.0, severity="mistake", phase="opening", category=category)
    db.add(m)
    db.commit()
    return m


def _answer(db, m: GameMistake, correct: bool, when: datetime | None = None) -> None:
    when = when or utcnow()
    db.add(Attempt(exercise_kind="game_position", game_mistake_id=m.id, mode="daily_review", correct=correct,
                   served_at=when, finished_at=when))
    db.commit()


def test_the_headlines_are_the_eight_the_owner_chose():
    assert alerts.HEADLINES["impulsive_decision"] == "Seus lances estão impulsivos."
    assert alerts.HEADLINES["missed_opponent_threat"] == "Você está ignorando as ameaças dele."
    assert len(alerts.HEADLINES) == 8


def test_the_alert_is_the_most_frequent_missed_kind_with_its_count(db):
    for _ in range(2):
        _answer(db, _mistake(db, "missed_opponent_threat"), False)
    _answer(db, _mistake(db, "tactical_blindness"), False)
    _answer(db, _mistake(db, "impulsive_decision"), True)
    a = alerts.alert(db, TODAY)
    assert (a["category"], a["count"], a["wrong"]) == ("missed_opponent_threat", 2, 3)
    assert a["text"] == "Você está ignorando as ameaças dele."


def test_no_alert_without_a_wrong_answer(db):
    _answer(db, _mistake(db, "tactical_blindness"), True)
    assert alerts.alert(db, TODAY) is None


def test_yesterdays_alert_shows_today_with_its_trend(db):
    _answer(db, _mistake(db, "impulsive_decision"), False, utcnow() - timedelta(days=1))
    a = alerts.latest(db, TODAY)
    assert a["category"] == "impulsive_decision" and a["day"] == (TODAY - timedelta(days=1)).isoformat()
    assert set(a["trend"]) == {"before", "after", "games_before", "games_after"}
    assert alerts.latest(db, TODAY - timedelta(days=1)) is None  # nothing earlier than that day


def test_trend_counts_the_kind_before_the_alert_and_after_it(db):
    day = TODAY - timedelta(days=3)  # the alert's day: its own games count as "before"
    for i in range(3):
        _mistake(db, "missed_opponent_threat", played=day - timedelta(days=1), fp=f"b{i}")
    _mistake(db, "missed_opponent_threat", played=day, fp="same-day")
    _mistake(db, "missed_opponent_threat", played=day + timedelta(days=1), fp="a0")
    _mistake(db, "tactical_blindness", played=day + timedelta(days=1), fp="a1")
    _mistake(db, "missed_opponent_threat", played=day - timedelta(days=1), fp="old", criteria=1)  # older judging
    t = alerts.trend(db, "missed_opponent_threat", day)
    assert (t["before"], t["after"]) == (4, 1)
    assert (t["games_before"], t["games_after"]) == (4, 2)


def test_alert_api(client, db):
    assert client.get("/api/alert").json() == {"today": None, "active": None}
    _answer(db, _mistake(db, "impulsive_decision"), False)
    assert client.get("/api/alert").json()["today"]["text"] == "Seus lances estão impulsivos."
    assert client.get("/api/rule").status_code == 404  # the if-then rule is gone
