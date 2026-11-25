"""The day's session of "Seus erros de partida": which moments, in which order, and when a
position comes back (the 1/3/7/21-day ladder)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from itertools import count

import pytest

from app.models import Attempt, Game, GameMistake, utcnow
from app.services import moments

TODAY = date(2026, 11, 25)
FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
_ids = count(1)


def _game(db, played: date = TODAY, wins: list | None = None, **metrics) -> Game:
    g = Game(fingerprint=f"g{next(_ids)}", pgn="1. e4 e5 *", white="TestUser", black=f"Opp{next(_ids)}",
             result="0-1", user_color="white", source="chess.com", played_on=played, analyzed=True,
             metrics={"criteria": 2, "deep": "done", **({"wins": wins} if wins is not None else {}), **metrics})
    db.add(g)
    db.commit()
    return g


def _mistake(db, g: Game, ply: int = 10, loss: float = 20.0, severity: str = "mistake",
             category: str = "tactical_blindness") -> GameMistake:
    m = GameMistake(game_id=g.id, ply=ply, fen_before=FEN, move_uci="e7e5", move_san="e5", best_uci="d7d5",
                    best_san="d5", eval_before_cp=0, eval_after_cp=-200, cp_loss=200, win_pct_loss=loss,
                    severity=severity, phase="opening", category=category)
    db.add(m)
    db.commit()
    return m


def _attempt(db, m: GameMistake, correct: bool, when: datetime, mode: str = "standard") -> None:
    db.add(Attempt(exercise_kind="game_position", game_mistake_id=m.id, mode=mode, correct=correct,
                   served_at=when, finished_at=when))
    db.commit()


# ------------------------------------------------------------------ kinds
def test_a_drop_that_never_comes_back_is_decisive():
    wins = [50, 55, 60, 52, 20, 18, 15, 10]
    assert moments.kind_of(wins, 3) == "decisive"


def test_a_drop_after_the_opponents_gift_is_a_missed_chance():
    wins = [50, 50, 48, 75, 60, 62, 61, 60]  # the opponent's move took you to 75; yours gave 15 back
    assert moments.kind_of(wins, 3) == "missed"


def test_a_drop_that_comes_back_later_is_common():
    wins = [50, 55, 60, 52, 20, 30, 45, 50]
    assert moments.kind_of(wins, 3) == "common"


def test_old_games_without_a_curve_are_common():
    assert moments.kind_of(None, 3) == "common"
    assert moments.kind_of([50, 50], 5) == "common"


# ------------------------------------------------------------------ ladder
def test_ladder_goes_1_3_7_21_and_masters_after_three_at_21():
    t0 = datetime(2026, 11, 1, 20, 0)
    h = []
    expected = [1, 3, 7, 21, 21, 21]
    for gap in expected:
        h.append((True, h[-1][1] + timedelta(days=prev) if h else t0))
        due, _ = moments.ladder(h)
        assert due == h[-1][1].date() + timedelta(days=gap)
        prev = gap
    h.append((True, h[-1][1] + timedelta(days=21)))  # the third correct answer at 21 days
    assert moments.ladder(h) == (None, 4)


def test_a_miss_brings_it_back_tomorrow_one_step_down():
    t0 = datetime(2026, 11, 1, 20, 0)
    h = [(True, t0), (True, t0 + timedelta(days=1)), (False, t0 + timedelta(days=4))]
    due, step = moments.ladder(h)
    assert due == date(2026, 11, 6) and step == 1


# ------------------------------------------------------------------ the session
def test_session_has_five_new_and_at_most_five_returns(db):
    for _ in range(6):
        g = _game(db)
        _mistake(db, g, ply=10)
        _mistake(db, g, ply=20, severity="blunder", loss=30.0)
    old = _game(db, played=TODAY - timedelta(days=30))
    for i in range(9):  # answered wrong 10 days ago: due long since
        _attempt(db, _mistake(db, old, ply=30 + i), False, datetime(2026, 11, 15, 20, 0))
    s = moments.build_session(db, TODAY, light=False)
    assert sum(i["source"] == "new" for i in s["items"]) == 5
    assert sum(i["source"] == "return" for i in s["items"]) == 5
    s = moments.build_session(db, TODAY + timedelta(days=1), light=True)
    assert sum(i["source"] == "return" for i in s["items"]) == 3


def test_no_more_than_two_moments_from_one_game(db):
    g = _game(db)
    for ply in (10, 12, 14, 16):
        _mistake(db, g, ply=ply, loss=40.0)
    other = _game(db)
    _mistake(db, other, ply=10, loss=5.0)
    s = moments.build_session(db, TODAY, light=False)
    assert sum(i["game_id"] == g.id for i in s["items"]) == 2
    assert any(i["game_id"] == other.id for i in s["items"])


def test_neighbours_differ_in_game_when_possible(db):
    a, b = _game(db), _game(db)
    for g in (a, b):
        _mistake(db, g, ply=10, loss=30.0)
        _mistake(db, g, ply=20, loss=29.0)
    items = moments.build_session(db, TODAY, light=False)["items"]
    games = [i["game_id"] for i in items]
    assert all(x != y for x, y in zip(games, games[1:]))


def test_decisive_moments_outrank_bigger_common_drops(db):
    wins = [50] * 10 + [52, 20] + [15] * 10  # ply 10 decided the game
    g = _game(db, wins=wins)
    decisive = _mistake(db, g, ply=10, loss=32.0)
    others = [_mistake(db, _game(db), ply=10, loss=40.0) for _ in range(5)]
    items = moments.build_session(db, TODAY, light=False)["items"]
    assert decisive.id in [i["mistake_id"] for i in items]
    assert next(i for i in items if i["mistake_id"] == decisive.id)["kind"] == "decisive"
    assert len(others) == 5


def test_a_started_session_does_not_change(db):
    m = _mistake(db, _game(db))
    first = moments.today_session(db, TODAY)
    _attempt(db, m, False, utcnow() + timedelta(seconds=1), mode="daily_review")  # you started it
    _mistake(db, _game(db))  # a game that arrives after that
    again = moments.today_session(db, TODAY)
    assert again["items"] == first["items"]
    assert moments.new_games_since(db, again) == 1
    more = moments.second_round(db, TODAY)
    assert len(more["items"]) == len(first["items"]) + 1
    assert moments.new_games_since(db, more) == 0


def test_an_untouched_session_takes_the_games_that_arrive_later(db):
    """The start screen plans the day before the Chess.com import has finished: an empty (or
    unanswered) session must not keep today's games out."""
    empty = moments.today_session(db, TODAY)
    assert empty["items"] == []
    m = _mistake(db, _game(db))
    again = moments.today_session(db, TODAY)
    assert [i["mistake_id"] for i in again["items"]] == [m.id]
    assert moments.new_games_since(db, again) == 0
    m2 = _mistake(db, _game(db), loss=50.0)  # still untouched: rebuilt again, best first
    assert moments.today_session(db, TODAY)["items"][0]["mistake_id"] == m2.id


def test_no_games_today_uses_returns_and_the_last_three_days(db):
    g = _game(db, played=TODAY - timedelta(days=3))
    m = _mistake(db, g)
    s = moments.build_session(db, TODAY, light=False)
    assert [i["mistake_id"] for i in s["items"]] == [m.id]


def test_history_before_the_feature_is_capped(db):
    old = _game(db, played=TODAY - timedelta(days=60))
    for i in range(40):
        _attempt(db, _mistake(db, old, ply=i), False, datetime(2026, 10, 1, 20, 0))
    s = moments.build_session(db, TODAY, light=False)
    assert len(s["items"]) == 5 and all(i["source"] == "return" for i in s["items"])


def test_unanswered_moments_of_yesterday_come_back_first(db):
    g = _game(db, played=TODAY - timedelta(days=1))
    m = _mistake(db, g, loss=10.0)
    moments.today_session(db, TODAY - timedelta(days=1))  # built, never answered
    _mistake(db, _game(db), loss=50.0)
    items = moments.today_session(db, TODAY)["items"]
    assert items[0]["mistake_id"] == m.id and items[0]["source"] == "return"


def test_retired_mistakes_never_come_back(db):
    old = _game(db, played=TODAY - timedelta(days=60))
    m = _mistake(db, old, severity="retired")
    _attempt(db, m, False, datetime(2026, 10, 1, 20, 0))
    assert moments.due_returns(db, TODAY, 5) == []


def test_review_stats_counts_returns_and_sessions(db):
    old = _game(db, played=date(2026, 9, 1))
    a = _mistake(db, old)
    for when, ok in ((datetime(2026, 10, 1, 20), True), (datetime(2026, 10, 2, 20), True),
                     (datetime(2026, 10, 5, 20), True), (datetime(2026, 10, 12, 20), False)):
        _attempt(db, a, ok, when)  # steps before each answer: 0, 1, 2, 3
    b = _mistake(db, old, ply=20)
    for day, minutes in ((23, 8), (24, 12)):  # Monday and Tuesday of the week of Wed 2026-11-25
        db.add(Attempt(exercise_kind="game_position", game_mistake_id=b.id, mode="daily_review", correct=False,
                       served_at=datetime(2026, 11, day, 23, 0), finished_at=datetime(2026, 11, day, 23, minutes)))
    db.commit()
    s = moments.stats(db, date(2026, 11, 25))
    assert s["returns_ok_3d"] == 50 and s["returns_ok_7d"] == 0
    assert s["session_days_week"] == 2 and s["median_session_min"] == 10


def test_time_note_only_for_fast_decisive_moves():
    assert moments.time_note("decisive", 3.0, 20.0) == "Você pensou 3 s no lance que decidiu a partida."
    assert moments.time_note("missed", 8.0, 20.0) == "Você pensou 8 s na chance que ele te deu."
    assert moments.time_note("common", 1.0, 20.0) is None
    assert moments.time_note("decisive", 30.0, 20.0) is None
    assert moments.time_note("decisive", None, 20.0) is None
    assert moments.time_note("decisive", 1.4, None) == "Você pensou 1,4 s no lance que decidiu a partida."
