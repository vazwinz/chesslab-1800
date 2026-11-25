"""The rule of the day ("se… então") and the note on the time spent on a move that decided a game."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import chess

from app.models import Attempt, Game, GameMistake, utcnow
from app.services import moments, rules

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


def test_the_templates_are_the_eight_of_the_design():
    assert rules.TEMPLATES["missed_opponent_threat"] == "Se ele acabou de mexer, eu pergunto o que esse lance ameaça."
    assert len(rules.TEMPLATES) == 8


def test_suggestion_is_the_most_frequent_missed_category(db):
    for _ in range(2):
        _answer(db, _mistake(db, "missed_opponent_threat"), False)
    _answer(db, _mistake(db, "tactical_blindness"), False)
    _answer(db, _mistake(db, "impulsive_decision"), True)
    s = rules.suggestion(db, TODAY)
    assert s["category"] == "missed_opponent_threat"
    assert s["text"] == rules.TEMPLATES["missed_opponent_threat"]


def test_no_suggestion_without_a_wrong_answer(db):
    _answer(db, _mistake(db, "tactical_blindness"), True)
    assert rules.suggestion(db, TODAY) is None


def test_active_rule_is_the_one_accepted_on_an_earlier_day(db):
    rules.accept(db, "Se tem xeque, eu olho.", "tactical_blindness", day=TODAY - timedelta(days=1))
    rules.accept(db, "Se ele mexeu, eu pergunto.", "missed_opponent_threat", day=TODAY)  # for tomorrow
    a = rules.active(db, TODAY)
    assert a["text"] == "Se tem xeque, eu olho." and a["category"] == "tactical_blindness"
    assert rules.active(db, TODAY + timedelta(days=1))["category"] == "missed_opponent_threat"


def test_accepting_twice_the_same_day_keeps_one(db):
    rules.accept(db, "A", "tactical_blindness", day=TODAY)
    rules.accept(db, "B", "tactical_blindness", day=TODAY)
    assert [r["text"] for r in rules.history(db)] == ["B"]


def test_trend_counts_the_category_before_and_after(db):
    day = TODAY - timedelta(days=3)
    for i in range(3):
        _mistake(db, "missed_opponent_threat", played=day - timedelta(days=2), fp=f"b{i}")
    _mistake(db, "missed_opponent_threat", played=day + timedelta(days=1), fp="a0")
    _mistake(db, "tactical_blindness", played=day + timedelta(days=1), fp="a1")
    _mistake(db, "missed_opponent_threat", played=day - timedelta(days=2), fp="old", criteria=1)  # older judging
    t = rules.trend(db, "missed_opponent_threat", day)
    assert (t["before"], t["after"]) == (3, 1)
    assert (t["games_before"], t["games_after"]) == (3, 2)


def test_time_note_only_for_fast_decisive_moves():
    assert moments.time_note("decisive", 3.0, 20.0) == "Você pensou 3 s no lance que decidiu a partida."
    assert moments.time_note("missed", 8.0, 20.0) == "Você pensou 8 s na chance que ele te deu."
    assert moments.time_note("common", 1.0, 20.0) is None
    assert moments.time_note("decisive", 30.0, 20.0) is None
    assert moments.time_note("decisive", None, 20.0) is None
    assert moments.time_note("decisive", 1.4, None) == "Você pensou 1,4 s no lance que decidiu a partida."


def test_rule_api_accepts_and_removes_todays_rule(client):
    assert client.get("/api/rule").json() == {"suggestion": None, "today": None, "active": None}
    r = client.put("/api/rule", json={"text": "Se ele mexeu, eu pergunto o que ameaça.", "category": "missed_opponent_threat"}).json()
    assert r["today"]["text"] == "Se ele mexeu, eu pergunto o que ameaça." and r["active"] is None
    assert client.delete("/api/rule").json()["today"] is None
