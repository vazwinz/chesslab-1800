"""The background queue of game work: a quick pass then a deep one, resumed at start, and the
Chess.com import that runs on its own."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import Game
from app.services import game_jobs, prefs


@pytest.fixture(autouse=True)
def quiet_queue(monkeypatch):
    """No worker thread: the tests read what was queued."""
    monkeypatch.setattr(game_jobs, "_ensure_worker", lambda: None)
    game_jobs._queue.clear()
    monkeypatch.setattr(game_jobs, "_state", {"status": "idle"})
    yield
    game_jobs._queue.clear()


def _game(db, fp: str, analyzed: bool, metrics: dict) -> int:
    g = Game(fingerprint=fp, pgn="1. e4 e5 *", white="TestUser", black="Opponent", result="*",
             user_color="white", source="pgn", analyzed=analyzed, metrics=metrics)
    db.add(g)
    db.commit()
    return g.id


def test_two_pass_queues_quick_then_deep():
    game_jobs.enqueue_analysis([3, 4], two_pass=True)
    assert list(game_jobs._queue) == [("analyze", 3, 12), ("analyze", 4, 12),
                                      ("analyze", 3, None), ("analyze", 4, None)]


def test_the_same_game_can_wait_for_both_passes_but_not_twice():
    game_jobs.enqueue_analysis([3], two_pass=True)
    game_jobs.enqueue_analysis([3], two_pass=True)
    assert list(game_jobs._queue) == [("analyze", 3, 12), ("analyze", 3, None)]


def test_resume_queues_unanalysed_and_deep_pending(db):
    a = _game(db, "a", False, {})
    b = _game(db, "b", True, {"deep": "pending", "criteria": 2})
    c = _game(db, "c", True, {"deep": "done", "criteria": 2})
    assert game_jobs.resume(db) is not None
    q = list(game_jobs._queue)
    assert ("analyze", a, 12) in q and ("analyze", a, None) in q
    assert ("analyze", b, None) in q and ("analyze", b, 12) not in q
    assert not any(t[1] == c for t in q)


def test_resume_with_nothing_to_do_returns_none(db):
    _game(db, "c", True, {"deep": "done", "criteria": 2})
    assert game_jobs.resume(db) is None and not game_jobs._queue


@pytest.fixture()
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(game_jobs, "enqueue_chesscom", lambda u, m, a: seen.append((u, m, a)) or {})
    return seen


def test_auto_import_needs_a_username_and_the_switch(db, calls):
    t = datetime(2026, 11, 20, 10, 0)
    assert game_jobs.maybe_auto_import(db, now=t) is False  # no username saved
    prefs.update_prefs(db, {"chesscom_username": "TestUser", "chesscom_auto_import": False})
    assert game_jobs.maybe_auto_import(db, now=t) is False  # switched off
    prefs.update_prefs(db, {"chesscom_auto_import": True})
    assert game_jobs.maybe_auto_import(db, now=t) is True
    assert calls == [("TestUser", 1, True)]


def test_auto_import_at_most_once_an_hour(db, calls):
    prefs.update_prefs(db, {"chesscom_username": "TestUser"})
    t = datetime(2026, 11, 20, 10, 0)
    assert game_jobs.maybe_auto_import(db, now=t) is True
    assert game_jobs.maybe_auto_import(db, now=t + timedelta(minutes=30)) is False
    assert game_jobs.maybe_auto_import(db, now=t + timedelta(minutes=61)) is True
    assert len(calls) == 2


def test_auto_import_takes_last_month_too_on_the_first_two_days(db, calls):
    prefs.update_prefs(db, {"chesscom_username": "TestUser"})
    game_jobs.maybe_auto_import(db, now=datetime(2026, 12, 2, 10, 0))
    game_jobs.maybe_auto_import(db, now=datetime(2026, 12, 3, 12, 0))
    assert [m for _, m, _ in calls] == [2, 1]
