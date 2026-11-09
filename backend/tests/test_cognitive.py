"""Cognitive Engine: Error DNA, retention, interventions, closed loop, attention, pressure, prediction."""
from __future__ import annotations

import time

import random
from datetime import date, timedelta

import chess
from sqlalchemy import select

from app import db as dbmod
from app.cognitive import attention, error_dna, interventions, loop, prediction, pressure, retention
from app.cognitive.error_dna import DecisionFeatures, classify
from app.cognitive.stats import ols, predict, wilson
from app.models import (Attempt, ConceptMemory, Game, GameMistake, InterventionStat, Puzzle, TrainingSession,
                        utcnow)
from app.services import puzzles

from .conftest import PGN_FIXTURE, needs_engine


# ------------------------------------------------------------------ helpers
def _age(attempt_id, ms):
    """Make the server believe `ms` milliseconds passed since the exercise was served."""
    with dbmod.SessionLocal() as s:
        a = s.get(Attempt, attempt_id)
        a.served_at = utcnow() - timedelta(milliseconds=ms + 50)
        s.commit()


def solve(c, ex, correct=True, elapsed=6000):
    """Answer an exercise through the public API (correctly, or with a legal wrong move)."""
    _age(ex["attempt_id"], max(elapsed, (ex.get("min_think_ms") or 0) + 500))
    with dbmod.SessionLocal() as s:
        if ex["kind"] == "game_position":
            gm = s.get(GameMistake, ex["game_mistake_id"])
            mv = gm.best_uci if correct else gm.move_uci
            return c.post(f"/api/attempts/{ex['attempt_id']}/move", json={"uci": mv, "elapsed_ms": elapsed}).json()
        p = s.get(Puzzle, ex["puzzle_id"])
        sol = puzzles.solution_moves(p)
    if ex.get("min_think_ms"):
        elapsed = max(elapsed, ex["min_think_ms"] + 500)
    if ex.get("blind"):
        moves = sol[0::2] if correct else [_wrong(ex["fen"], sol[0])]
        return c.post(f"/api/attempts/{ex['attempt_id']}/line", json={"moves": moves, "elapsed_ms": elapsed,
                                                                         "first_move_ms": elapsed}).json()
    if not correct:
        return c.post(f"/api/attempts/{ex['attempt_id']}/move",
                      json={"uci": _wrong(ex["fen"], sol[0]), "elapsed_ms": elapsed}).json()
    res = None
    for i in range(0, len(sol), 2):
        res = c.post(f"/api/attempts/{ex['attempt_id']}/move", json={"uci": sol[i], "elapsed_ms": elapsed}).json()
    return res


def _wrong(fen, right):
    b = chess.Board(fen)
    for m in b.legal_moves:
        if m.uci() != right:
            t = b.copy()
            t.push(m)
            if not t.is_checkmate():
                return m.uci()
    raise AssertionError("no wrong move")


# ------------------------------------------------------------------ Error DNA (pure rules)
def test_error_dna_priority_rules():
    assert classify(DecisionFeatures(timed_out=True), "puzzle") == "time_management_failure"
    assert classify(DecisionFeatures(think_s=1.0, impulsive_threshold_s=3.0, legal_moves=30), "puzzle") == "impulsive_decision"
    assert classify(DecisionFeatures(think_s=1.0, impulsive_threshold_s=3.0, legal_moves=1), "puzzle") != "impulsive_decision"
    assert classify(DecisionFeatures(themes=["defensiveMove"]), "puzzle") == "missed_opponent_threat"
    assert classify(DecisionFeatures(threat_cp=400, refutation_is_threat=True), "game") == "missed_opponent_threat"
    assert classify(DecisionFeatures(phase="endgame"), "game") == "endgame_technique_failure"
    assert classify(DecisionFeatures(fail_ply=1), "puzzle") == "calculation_error"
    assert classify(DecisionFeatures(blind=True), "puzzle") == "calculation_error"
    assert classify(DecisionFeatures(fail_ply=0), "puzzle") == "tactical_blindness"
    assert classify(DecisionFeatures(fail_ply=0, candidates_missed_solution=True), "puzzle") == "poor_candidate_selection"
    assert classify(DecisionFeatures(best_forcing=True, tactic_gap_cp=300, phase="middlegame"), "game") == "tactical_blindness"
    assert classify(DecisionFeatures(user_forcing=True, refutation_forcing=True, phase="middlegame"), "game") == "calculation_error"
    assert classify(DecisionFeatures(many_good_options=True, phase="middlegame"), "game") == "poor_candidate_selection"
    assert classify(DecisionFeatures(phase="middlegame"), "game") == "positional_misunderstanding"
    assert set(error_dna.PRIORITY) == set(error_dna.CATEGORIES)


@needs_engine
def test_engine_features_detect_missed_threat():
    from app.services.engine import StockfishService

    # White to move; Black threatens ...Qxb1#. h2h3 ignores the threat (and misses Rb8#).
    board = chess.Board("6k1/5ppp/8/8/8/8/q4PPP/1R4K1 w - - 0 1")
    eng = StockfishService()
    try:
        f = error_dna.engine_features(eng, board, chess.Move.from_uci("h2h3"), 12)
        assert f.threat_move == "a2b1" and f.refutation_is_threat and f.threat_cp >= error_dna.THREAT_CP
        assert f.best_move == "b1b8" and f.cp_loss > 1000
        assert classify(f, "game") == "missed_opponent_threat"
    finally:
        eng.close()


@needs_engine
def test_puzzle_failures_are_classified_via_api(client_with_puzzles):
    c = client_with_puzzles
    sid = c.post("/api/sessions", json={"kind": "mixed"}).json()["id"]
    r1 = solve(c, c.post(f"/api/sessions/{sid}/next").json(), correct=False, elapsed=400)
    assert "error_dna" in r1, r1
    assert r1["error_dna"]["category"] == "impulsive_decision"
    assert r1["error_dna"]["evidence"]["think_s"] == 0.4
    r2 = solve(c, c.post(f"/api/sessions/{sid}/next").json(), correct=False, elapsed=20000)
    assert r2["error_dna"]["category"] not in ("impulsive_decision", "time_management_failure")
    assert "cp_loss" in r2["error_dna"]["evidence"]
    bs = c.post("/api/sessions", json={"kind": "blind"}).json()["id"]
    r3 = solve(c, c.post(f"/api/sessions/{bs}/next").json(), correct=False, elapsed=20000)
    assert r3["error_dna"]["category"] in ("calculation_error", "missed_opponent_threat", "endgame_technique_failure")
    dna = c.get("/api/cognitive/error-dna").json()
    assert sum(p["count"] for p in dna["patterns"]) == 3


@needs_engine
def test_game_import_analysis_and_recurring_patterns(client):
    pgn = PGN_FIXTURE.read_text()
    r = client.post("/api/games/import", json={"pgn": pgn, "player_names": ["TestUser"], "analyze": True}).json()
    assert r["imported"] == 4 and r["unknown_user_color"] == 0
    assert r["job"]["status"] == "running"  # analysis runs in the background queue
    for _ in range(600):
        job = client.get("/api/games/jobs").json()
        if job["status"] != "running":
            break
        time.sleep(0.2)
    assert job["status"] == "done" and job["done"] == 4 and not job["errors"], job
    dup = client.post("/api/games/import", json={"pgn": pgn, "player_names": ["TestUser"]}).json()
    assert dup["imported"] == 0 and dup["duplicates"] == 4
    games = client.get("/api/games").json()
    assert all(g["analyzed"] and g["metrics"]["acpl"] is not None for g in games)
    detail = client.get(f"/api/games/{games[0]['id']}").json()
    assert detail["mistakes"], "a deliberately weak player must make mistakes"
    m = detail["mistakes"][0]
    assert m["category"] in error_dna.CATEGORIES and m["severity"] in ("inaccuracy", "mistake", "blunder")
    assert "best_move" in m["evidence"]
    dna = client.get("/api/cognitive/error-dna").json()
    assert dna["game_moves_analyzed"] > 50
    assert any(p["recurring"] for p in dna["patterns"])
    # own-game mistakes become exercises
    sid = client.post("/api/sessions", json={"kind": "own_mistakes"}).json()["id"]
    ex = client.post(f"/api/sessions/{sid}/next").json()
    assert ex["kind"] == "game_position" and "lance melhor" in ex["prompt"]
    res = solve(client, ex, correct=True)
    assert res["correct"] is True and res["comparison"]["verdict"] == "good"


# ------------------------------------------------------------------ retention
def test_retention_intervals_grow_only_with_spacing(db):
    cm = retention.record_exposure(db, "fork", True, 5)
    db.flush()
    assert cm.interval_days == 1.0 and cm.reps == 1
    retention.record_exposure(db, "fork", True, 5)  # massed: immediately again
    assert cm.interval_days == 1.0 and cm.reps == 1, "cramming must not inflate the interval"
    cm.last_reviewed_at = utcnow() - timedelta(days=1)
    retention.record_exposure(db, "fork", True, 5)
    assert cm.interval_days == 3.0
    cm.last_reviewed_at = utcnow() - timedelta(days=3)
    retention.record_exposure(db, "fork", True, 4)
    assert cm.interval_days > 3.0
    before_ease = cm.ease
    retention.record_exposure(db, "fork", False, 1)
    assert cm.lapses == 1 and cm.interval_days == 1.0 and cm.ease < before_ease


def test_retention_probe_uses_new_positions(client_with_puzzles):
    c = client_with_puzzles
    from collections import Counter

    with dbmod.SessionLocal() as s:
        counts = Counter(puzzles.primary_concept(p.themes) for p in s.execute(select(Puzzle)).scalars())
    concept = next(k for k, n in counts.most_common() if k and n >= 2)
    sid = c.post("/api/sessions", json={"kind": "theme", "theme": concept}).json()["id"]
    ex = c.post(f"/api/sessions/{sid}/next").json()
    while puzzles.primary_concept(" ".join(c.get(f"/api/puzzles/{ex['puzzle_id']}").json()["themes"])) != concept:
        solve(c, ex, correct=True)
        ex = c.post(f"/api/sessions/{sid}/next").json()
    res = solve(c, ex, correct=True)
    assert res["retention"]["concept"] == concept
    with dbmod.SessionLocal() as s:  # pretend the review is due
        cm = s.get(ConceptMemory, concept)
        cm.due_at = utcnow() - timedelta(hours=1)
        cm.last_reviewed_at = utcnow() - timedelta(days=2)
        s.commit()
    rs = c.post("/api/sessions", json={"kind": "retention"}).json()["id"]
    probe = c.post(f"/api/sessions/{rs}/next").json()
    assert probe["retention_probe"] == "transfer" and probe["puzzle_id"] != ex["puzzle_id"]
    assert probe["mode"] == "retention"
    solve(c, probe, correct=True)
    rep = c.get("/api/cognitive/retention").json()
    item = next(x for x in rep["concepts"] if x["concept"] == concept)
    assert item["transfer"] == {"n": 1, "ok": 1}
    assert any(b["n"] for b in rep["curve"])


# ------------------------------------------------------------------ interventions
def test_thompson_sampling_learns_per_user(db):
    rng = random.Random(3)
    st = InterventionStat(intervention_key="candidate_listing", target_category="positional_misunderstanding",
                          alpha=1, beta=12, trials=11, mean_effect=-0.01)
    db.add(st)
    db.add(InterventionStat(intervention_key="own_mistakes", target_category="positional_misunderstanding",
                            alpha=12, beta=1, trials=11, mean_effect=0.05))
    db.flush()
    picks = [interventions.choose_intervention(db, "positional_misunderstanding", rng)[0].key for _ in range(50)]
    assert picks.count("own_mistakes") > 40, "the intervention that worked for this user should dominate"


def test_controlled_difficulty_and_interleaving(db):
    a = interventions.start_assignment(db, "tactical_blindness", "fork", None, {"rate": 0.3, "n": 40},
                                       random.Random(1))
    assert a.intervention_key in ("pattern_drill", "own_mistakes")
    a.intervention_key = "pattern_drill"
    for _ in range(6):
        db.add(Attempt(assignment_id=a.id, mode="intervention", correct=True, served_at=utcnow()))
    db.flush()
    off0 = a.params["offset"]
    assert interventions.assignment_offset(db, a) == off0 + 50  # too easy → harder
    a.exercises_done = 3
    spec = interventions.exercise_spec(db, a)
    assert spec["interleaved"] and spec["themes"] == []
    out = interventions.record_outcome(db, a, {"rate": 0.1, "n": 20})
    assert out["improved"] and db.get(InterventionStat, ("pattern_drill", "tactical_blindness")).alpha == 2


# ------------------------------------------------------------------ closed loop
@needs_engine
def test_closed_loop_full_cycle(client_with_puzzles, monkeypatch):
    monkeypatch.setattr(loop, "BASELINE_N", 6)
    monkeypatch.setattr(loop, "REASSESS_N", 5)
    monkeypatch.setattr(loop, "PRACTICE_N", 5)
    c = client_with_puzzles
    sid = c.post("/api/sessions", json={"kind": "loop"}).json()["id"]
    phases = []
    for i in range(40):
        r = c.post(f"/api/sessions/{sid}/next")
        if r.status_code == 409:
            break
        ex = r.json()
        phases.append(ex["loop_phase"])
        # MEASURE: fast wrong answers create a recurring impulsive pattern; later: mostly correct
        wrong = ex["loop_phase"] == "measure" and i % 2 == 0
        solve(c, ex, correct=not wrong, elapsed=400 if wrong else 7000)
        st = c.get("/api/cognitive/loop").json()
        if st["history"]:
            break
    st = c.get("/api/cognitive/loop").json()
    assert "measure" in phases and "practice" in phases and "reassess" in phases, phases
    assert st["history"], st
    adapt = st["history"][0]["adaptation"]
    assert adapt["category"] == "impulsive_decision" and adapt["intervention"] == "slow_down"
    assert adapt["updated"] in (True, False)
    eff = c.get("/api/cognitive/interventions").json()["effectiveness"]
    if adapt["updated"]:
        assert eff and eff[0]["trials"] == 1
    assert st["phase"] in ("practice", "diagnose", "measure")  # next cycle already running


# ------------------------------------------------------------------ attention / fatigue
def _session_with(db, results: list[tuple[bool, int]]):
    s = TrainingSession(kind="mixed", started_at=utcnow() - timedelta(minutes=60), last_activity_at=utcnow())
    db.add(s)
    db.flush()
    for ok, ms in results:
        db.add(Attempt(session_id=s.id, correct=ok, expected_score=0.6, total_ms=ms, served_at=utcnow(),
                       hesitation={}))
    db.flush()
    return s


def test_fatigue_detected_only_for_consistent_decline(db):
    good = [(True, 10000)] * 6 + [(False, 10000)] * 2
    tired = [(False, 18000)] * 6 + [(True, 18000)] * 2
    s1 = _session_with(db, good + good + tired)
    t1 = attention.session_trend(db, s1.id)
    assert t1["suggest_break"] and "médico" in t1["disclaimer"]
    s2 = _session_with(db, good * 3)
    assert not attention.session_trend(db, s2.id)["suggest_break"]
    s3 = _session_with(db, good * 2 + [(False, 18000)] * 2 + [(True, 10000)] * 6)  # one bad streak recovered
    assert not attention.session_trend(db, s3.id)["suggest_break"]
    s4 = _session_with(db, good)
    assert attention.session_trend(db, s4.id)["status"].startswith("coletando")


# ------------------------------------------------------------------ pressure
@needs_engine
def test_pressure_mode_timeouts_and_levels(client_with_puzzles):
    c = client_with_puzzles
    sid = c.post("/api/sessions", json={"kind": "pressure"}).json()["id"]
    ex = c.post(f"/api/sessions/{sid}/next").json()
    assert ex["time_limit_ms"] == 60000 and 0 <= ex["complexity"] <= 1
    # client claims a timeout too early → rejected as a timeout
    r = c.post(f"/api/attempts/{ex['attempt_id']}/give-up", json={"timed_out": True, "elapsed_ms": 1000}).json()
    assert r["timed_out"] is False
    ex2 = c.post(f"/api/sessions/{sid}/next").json()
    with dbmod.SessionLocal() as s:
        a = s.get(Attempt, ex2["attempt_id"])
        a.served_at = a.served_at - timedelta(seconds=61)
        s.commit()
    r2 = c.post(f"/api/attempts/{ex2['attempt_id']}/give-up", json={"timed_out": True, "elapsed_ms": 61000}).json()
    assert r2["timed_out"] and r2["error_dna"]["category"] == "time_management_failure"
    assert "rating" not in r2  # pressure attempts don't move the puzzle rating
    for _ in range(6):
        solve(c, c.post(f"/api/sessions/{sid}/next").json(), correct=True, elapsed=5000)
    rep = c.get("/api/cognitive/pressure").json()
    assert rep["current"]["level"] == 2
    lv1 = rep["by_level"]["1"]
    assert lv1["timeout_rate"]["n"] == lv1["n"] and lv1["decision_quality"]["n"] == lv1["n"] - 1


# ------------------------------------------------------------------ prediction & stats
def test_prediction_requires_data_and_reports_intervals(db):
    rep = prediction.prediction_report(db)
    assert rep["games"]["status"] == "insufficient_data" and rep["puzzle_rating"]["status"] == "insufficient_data"
    rng = random.Random(5)
    for i in range(14):
        db.add(Game(fingerprint=f"g{i}", pgn="", user_color="white", analyzed=True,
                    played_on=date(2026, 9, 1) + timedelta(days=2 * i),
                    metrics={"accuracy": 70 + 0.5 * i + rng.uniform(-3, 3), "blunders_per_100": 4 - 0.1 * i,
                             "user_moves": 40}))
    db.flush()
    g = prediction.game_trajectory(db)
    assert g["status"] == "ok"
    acc = g["accuracy"]
    assert acc["slope_per_30d_ci"][0] < acc["slope_per_30d"] < acc["slope_per_30d_ci"][1]
    f = acc["forecasts"][0]
    assert f["pi_low"] < f["value"] < f["pi_high"]
    assert "não" in prediction.DISCLAIMER.lower()


def test_stats_helpers():
    w = wilson(8, 10)
    assert w["low"] < 0.8 < w["high"]
    fit = ols([0, 1, 2, 3, 4], [1, 3, 5, 7, 9.1])
    assert abs(fit["slope"] - 2) < 0.1
    p = predict(fit, 5)
    assert p["pi_low"] < p["value"] < p["pi_high"]


def test_profile_never_claims_iq(client):
    prof = client.get("/api/cognitive/profile").json()
    assert "Não mede inteligência" in prof["disclaimer"]
    assert prof["pattern_recognition"]["sufficient"] is False
    pr = client.get("/api/cognitive/principles").json()
    assert {"active_retrieval", "spaced_repetition", "interleaving", "feedback", "deliberate_practice",
            "progressive_challenge"} <= set(pr["validated_principles"])
    assert "error_dna" in pr["experimental_features"]


def test_pressure_complexity_bounds(puzzles_db):
    for p in puzzles_db.execute(select(Puzzle)).scalars():
        assert 0.0 <= pressure.complexity(p) <= 1.0
