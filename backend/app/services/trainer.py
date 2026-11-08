"""Exercise orchestration: chooses the next exercise for a training session, validates moves,
and finalises attempts (rating, Error DNA, retention, interventions, fatigue, closed loop)."""
from __future__ import annotations

import logging
import random
from datetime import timedelta

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cognitive import attention, interventions, loop, pressure, retention
from ..cognitive.error_dna import CATEGORIES, DecisionFeatures, classify, engine_features, phase_of
from ..models import Attempt, GameMistake, InterventionAssignment, Puzzle, RatingPoint, TrainingSession, utcnow
from . import adaptive, puzzles
from .engine import EngineUnavailable, get_engine
from .explain import explain
from .rating import current_rating, expected_score, glicko_update

log = logging.getLogger(__name__)
SESSION_KINDS = ["mixed", "theme", "blind", "candidates", "retention", "pressure", "endgame", "own_mistakes", "loop"]
ERROR_ANALYSIS_DEPTH = 12
UNRATED_MODES = ("pressure",)


class NoExercise(Exception):
    pass


# ------------------------------------------------------------------ selection
def _payload(a: Attempt, p: Puzzle | None = None, gm: GameMistake | None = None, extra: dict | None = None) -> dict:
    base = {"attempt_id": a.id, "mode": a.mode, "kind": a.exercise_kind, "time_limit_ms": a.time_limit_ms,
            "min_think_ms": a.min_think_ms, "blind": a.mode == "blind" or bool((extra or {}).get("blind")),
            "candidates": a.mode == "candidates" or bool((extra or {}).get("candidates")),
            "retention_probe": a.retention_probe, "pressure_level": a.pressure_level}
    if p is not None:
        st = puzzles.puzzle_start(p)
        base.update({"puzzle_id": p.id, **st, "rating": p.rating, "concept": a.concept if a.mode in
                     ("theme", "retention", "intervention") else None})
    if gm is not None:
        board = chess.Board(gm.fen_before)
        base.update({"fen": gm.fen_before, "initial_fen": gm.fen_before, "opponent_move": None,
                     "solver_color": "white" if board.turn else "black", "solution_len": 1,
                     "game_mistake_id": gm.id, "prompt": f"In your game you played {gm.move_san}. Find a better move."})
    base.update(extra or {})
    return base


def _new_attempt(db: Session, sess: TrainingSession, mode: str, p: Puzzle | None = None, gm: GameMistake | None = None,
                 **kw) -> Attempt:
    r, rd = current_rating(db)
    idx = db.execute(select(Attempt.id).where(Attempt.session_id == sess.id)).all()
    a = Attempt(session_id=sess.id, mode=mode, index_in_session=len(idx) + 1, user_rating_before=r,
                served_at=utcnow(), moves_played=[], move_times_ms=[], hesitation={}, candidates=[],
                error_detail={}, timed_out=False, themes="", **kw)
    if p is not None:
        a.exercise_kind, a.puzzle_id, a.puzzle_rating = "puzzle", p.id, p.rating
        a.solution_len, a.themes = p.solution_len, p.themes
        a.concept = a.concept or puzzles.primary_concept(p.themes)
        a.expected_score = expected_score(r, p.rating, p.rating_deviation)
    if gm is not None:
        # own-game positions are not a puzzle concept, so they stay out of the retention scheduler
        a.exercise_kind, a.game_mistake_id, a.solution_len = "game_position", gm.id, 1
    db.add(a)
    sess.last_activity_at = utcnow()
    db.flush()
    return a


def _adaptive_window(db: Session, offset: int = 0) -> tuple[int, int]:
    r, _ = current_rating(db)
    return adaptive.target_rating(db, r, offset)


def _assessment(db: Session, sess: TrainingSession) -> dict:
    r, _ = current_rating(db)
    p = puzzles.select_puzzle(db, int(r - 150), int(r + 150), exclude_recent_days=3650)
    if p is None:
        raise NoExercise("No unseen puzzles near your rating. Import more puzzles.")
    a = _new_attempt(db, sess, "assessment", p)
    return _payload(a, p)


def _retention_exercise(db: Session, sess: TrainingSession) -> dict | None:
    due = retention.due_concepts(db, limit=5)
    for cm in due:
        kind = retention.probe_kind(cm)
        p = None
        if kind == "recall":
            p = retention.recall_candidate(db, cm.concept, max(1.0, cm.interval_days * 0.8))
        if p is None:
            kind = "transfer"
            r, _ = current_rating(db)
            p = puzzles.select_puzzle(db, int(r - 250), int(r + 100), themes=[cm.concept], exclude_recent_days=3650)
        if p is None:
            continue
        a = _new_attempt(db, sess, "retention", p, concept=cm.concept, retention_probe=kind)
        return _payload(a, p, extra={"concept": cm.concept})
    return None


def _own_mistake(db: Session, sess: TrainingSession, mode: str, **kw) -> dict | None:
    recent = {gid for gid in db.execute(select(Attempt.game_mistake_id).where(
        Attempt.game_mistake_id.is_not(None), Attempt.served_at >= utcnow() - timedelta(days=3))).scalars()}
    q = select(GameMistake).where(GameMistake.severity.in_(("mistake", "blunder")))
    cat = kw.pop("category", None)
    if cat:
        q = q.where(GameMistake.category == cat)
    rows = [m for m in db.execute(q.order_by(GameMistake.id.desc()).limit(300)).scalars() if m.id not in recent]
    if not rows:
        return None
    gm = random.choice(rows)
    a = _new_attempt(db, sess, mode, gm=gm, **kw)
    return _payload(a, gm=gm)


def _intervention_exercise(db: Session, sess: TrainingSession, asg: InterventionAssignment) -> dict:
    spec = interventions.exercise_spec(db, asg)
    if spec.get("interleave_with_due_review"):
        ex = _retention_exercise(db, sess)
        if ex is not None:
            att = db.get(Attempt, ex["attempt_id"])
            att.assignment_id = asg.id
            ex["interleaved"] = True
            return ex
    if spec["own_games"]:
        ex = _own_mistake(db, sess, "intervention", assignment_id=asg.id, category=asg.target_category)
        if ex is None:
            ex = _own_mistake(db, sess, "intervention", assignment_id=asg.id)
        if ex is not None:
            ex["intervention"] = spec
            return ex
    lo, hi = _adaptive_window(db, spec["offset"])
    themes = puzzles.themed_any(db, spec["themes"]) if spec["themes"] else None
    p = puzzles.select_puzzle(db, lo, hi, themes=themes or None, min_len=spec["min_len"], max_len=spec["max_len"])
    if p is None:
        p = puzzles.select_puzzle(db, lo, hi)
    if p is None:
        raise NoExercise("No puzzles available for this intervention. Import more puzzles.")
    a = _new_attempt(db, sess, "intervention", p, assignment_id=asg.id, min_think_ms=spec["min_think_ms"],
                     time_limit_ms=spec["time_limit_s"] * 1000 if spec["time_limit_s"] else None)
    return _payload(a, p, extra={"intervention": spec, "blind": spec["blind"], "candidates": spec["candidates"]})


def next_exercise(db: Session, sess: TrainingSession) -> dict:
    kind = sess.kind
    if kind == "loop":
        c = loop.advance(db)
        n = len(db.execute(select(Attempt.id).where(Attempt.session_id == sess.id)).all())
        if c.phase == "practice" and c.assignment_id:
            ex = _intervention_exercise(db, sess, db.get(InterventionAssignment, c.assignment_id))
        else:
            ex = None
            if c.phase == "measure" and n % 5 == 4:
                ex = _retention_exercise(db, sess)
            ex = ex or _assessment(db, sess)
        ex["loop_phase"] = c.phase
        db.commit()
        return ex
    if kind == "retention":
        ex = _retention_exercise(db, sess)
        if ex is None:
            raise NoExercise("No concepts are due for review right now.")
        db.commit()
        return ex
    if kind == "own_mistakes":
        ex = _own_mistake(db, sess, "standard")
        if ex is None:
            raise NoExercise("No analysed game mistakes yet. Import and analyse your games first.")
        db.commit()
        return ex
    if kind == "pressure":
        lv = pressure.current_level(db)
        lo, hi = _adaptive_window(db, -100)
        themes = puzzles.themed_any(db, lv["themes"]) if lv["themes"] else []
        pool = []
        for _ in range(6):
            p = puzzles.select_puzzle(db, lo, hi, themes=themes or None, min_len=lv["min_len"],
                                      exclude={q.id for q in pool})
            if p is None:
                p = puzzles.select_puzzle(db, lo, hi, exclude={q.id for q in pool})
            if p is not None:
                pool.append(p)
        if not pool:
            raise NoExercise("No puzzles available. Import puzzles first.")
        p = min(pool, key=lambda q: abs(pressure.complexity(q) - lv["complexity"]))
        a = _new_attempt(db, sess, "pressure", p, time_limit_ms=lv["seconds"] * 1000, pressure_level=lv["level"])
        db.commit()
        return _payload(a, p, extra={"complexity": pressure.complexity(p)})
    # base modes
    themes = None
    if kind == "theme" and sess.theme:
        themes = puzzles.TACTICAL_CATEGORIES.get(sess.theme, [sess.theme])
    elif kind == "endgame":
        themes = puzzles.ENDGAME_THEMES
    if themes:
        themes = puzzles.themed_any(db, themes)
        if not themes:
            raise NoExercise("No puzzles with this theme in the local database.")
    lo, hi = _adaptive_window(db)
    min_len = 2 if kind == "blind" else None
    p = puzzles.select_puzzle(db, lo, hi, themes=themes, min_len=min_len)
    if p is None and min_len:
        p = puzzles.select_puzzle(db, lo, hi, themes=themes)
    if p is None:
        raise NoExercise("No puzzles available. Import the Lichess puzzle database first.")
    mode = {"blind": "blind", "candidates": "candidates"}.get(kind, "standard")
    a = _new_attempt(db, sess, mode, p, concept=puzzles.primary_concept(p.themes))
    db.commit()
    return _payload(a, p)


# ------------------------------------------------------------------ moves
def _server_elapsed_ms(a: Attempt) -> int:
    return int((utcnow() - a.served_at).total_seconds() * 1000)


def _trusted(client_ms: int | None, server_ms: int) -> int:
    if client_ms is None or client_ms < 0 or client_ms > server_ms + 1500:
        return server_ms
    return int(client_ms)


def play_move(db: Session, a: Attempt, uci: str, elapsed_ms: int | None, hesitation: dict | None) -> dict:
    if a.correct is not None:
        return {"error": "attempt already finished"}
    server_ms = _server_elapsed_ms(a)
    elapsed = _trusted(elapsed_ms, server_ms)
    if a.min_think_ms and not a.moves_played and server_ms + 500 < a.min_think_ms:
        return {"locked": True, "remaining_ms": a.min_think_ms - server_ms}
    if a.time_limit_ms and server_ms > a.time_limit_ms + 1500:
        return finish(db, a, correct=False, timed_out=True, total_ms=server_ms, hesitation=hesitation)
    if a.first_move_ms is None:
        a.first_move_ms = elapsed
    times = list(a.move_times_ms or [])
    times.append(elapsed)
    a.move_times_ms = times
    if a.exercise_kind == "game_position":
        return _game_position_move(db, a, uci, elapsed, hesitation)
    p = db.get(Puzzle, a.puzzle_id)
    ply_index = len(a.moves_played or []) // 2
    res = puzzles.check_user_move(p, ply_index, a.moves_played or [], uci)
    if not res["legal"]:
        return {"legal": False}
    played = list(a.moves_played or []) + [res["uci"]]
    if res["correct"] and not res["finished"]:
        played.append(res["reply"])
        a.moves_played = played
        db.commit()
        return {"legal": True, "correct": True, "finished": False, "reply": res["reply"],
                "reply_san": res["reply_san"], "fen": res["fen"]}
    a.moves_played = played
    if not res["correct"]:
        a.fail_ply, a.expected_move = ply_index, res["expected"]
    return finish(db, a, correct=res["correct"], total_ms=elapsed, hesitation=hesitation)


def _game_position_move(db: Session, a: Attempt, uci: str, elapsed: int, hesitation: dict | None) -> dict:
    gm = db.get(GameMistake, a.game_mistake_id)
    board = chess.Board(gm.fen_before)
    try:
        mv = chess.Move.from_uci(uci)
    except ValueError:
        return {"legal": False}
    if mv not in board.legal_moves:
        return {"legal": False}
    a.moves_played = [mv.uci()]
    comparison = None
    try:
        comparison = get_engine().compare_move(board, mv, depth=ERROR_ANALYSIS_DEPTH)
        correct = comparison["verdict"] == "good"
        a.cp_loss = comparison["cp_loss"]
    except EngineUnavailable:
        correct = mv.uci() == gm.best_uci
    if not correct:
        a.fail_ply, a.expected_move = 0, gm.best_uci
    return finish(db, a, correct=correct, total_ms=elapsed, hesitation=hesitation, comparison=comparison)


def submit_line(db: Session, a: Attempt, moves: list[str], elapsed_ms: int | None, first_move_ms: int | None,
                hesitation: dict | None) -> dict:
    """Blind mode: the whole line is submitted before any piece moves. Accepts UCI or SAN."""
    if a.correct is not None or a.exercise_kind != "puzzle":
        return {"error": "not a pending puzzle attempt"}
    p = db.get(Puzzle, a.puzzle_id)
    sol = puzzles.solution_moves(p)
    board = chess.Board(p.fen)
    board.push(chess.Move.from_uci(p.moves.split()[0]))
    played, correct, fail = [], True, None
    for i in range(len(sol) // 2 + 1):
        if 2 * i >= len(sol):
            break
        if i >= len(moves):
            correct, fail = False, i
            break
        raw = moves[i].strip()
        try:
            mv = board.parse_san(raw)
        except ValueError:
            try:
                mv = chess.Move.from_uci(raw)
            except ValueError:
                mv = None
        if mv is None or mv not in board.legal_moves:
            correct, fail = False, i
            break
        board.push(mv)
        played.append(mv.uci())
        if mv.uci() != sol[2 * i] and not board.is_checkmate():
            correct, fail = False, i
            break
        if board.is_checkmate() or 2 * i + 1 >= len(sol):
            break
        reply = chess.Move.from_uci(sol[2 * i + 1])
        board.push(reply)
        played.append(reply.uci())
    a.moves_played = played
    server_ms = _server_elapsed_ms(a)
    a.first_move_ms = _trusted(first_move_ms, server_ms)
    if not correct:
        a.fail_ply, a.expected_move = fail, sol[2 * fail]
    return finish(db, a, correct=correct, total_ms=_trusted(elapsed_ms, server_ms), hesitation=hesitation)


def submit_candidates(db: Session, a: Attempt, moves: list[str]) -> dict:
    if a.moves_played:
        return {"error": "candidates must be listed before the first move"}
    board = _solver_board(db, a)
    ucis = []
    for raw in moves[:3]:
        try:
            mv = board.parse_san(raw)
        except ValueError:
            try:
                mv = chess.Move.from_uci(raw)
            except ValueError:
                return {"error": f"illegal or unreadable move: {raw}"}
        if mv not in board.legal_moves:
            return {"error": f"illegal move: {raw}"}
        ucis.append(mv.uci())
    a.candidates = ucis
    db.commit()
    return {"ok": True, "candidates": ucis}


def _solver_board(db: Session, a: Attempt) -> chess.Board:
    if a.exercise_kind == "game_position":
        return chess.Board(db.get(GameMistake, a.game_mistake_id).fen_before)
    p = db.get(Puzzle, a.puzzle_id)
    b = chess.Board(p.fen)
    b.push(chess.Move.from_uci(p.moves.split()[0]))
    return b


def give_up(db: Session, a: Attempt, elapsed_ms: int | None, hesitation: dict | None, timed_out: bool = False) -> dict:
    if a.correct is not None:
        return {"error": "attempt already finished"}
    server_ms = _server_elapsed_ms(a)
    if timed_out and a.time_limit_ms and server_ms + 1500 < a.time_limit_ms:
        timed_out = False  # client claims a timeout that cannot have happened yet
    if a.fail_ply is None:
        a.fail_ply = len(a.moves_played or []) // 2
        if a.exercise_kind == "puzzle":
            a.expected_move = puzzles.solution_moves(db.get(Puzzle, a.puzzle_id))[2 * a.fail_ply]
    return finish(db, a, correct=False, timed_out=timed_out, total_ms=_trusted(elapsed_ms, server_ms),
                  hesitation=hesitation, gave_up=not timed_out)


# ------------------------------------------------------------------ finalisation
def impulsive_threshold_ms(db: Session, rating: int | None) -> float:
    """35% of the player's own median first-move time on correctly solved puzzles of similar
    rating (min 2.5 s). Falls back to 3 s until 8 such attempts exist."""
    q = select(Attempt.first_move_ms).where(Attempt.correct.is_(True), Attempt.first_move_ms.is_not(None))
    if rating:
        q = q.where(Attempt.puzzle_rating.between(rating - 200, rating + 200))
    xs = sorted(x for x in db.execute(q.order_by(Attempt.id.desc()).limit(100)).scalars() if x)
    if len(xs) < 8:
        return 3000.0
    return max(2500.0, 0.35 * xs[len(xs) // 2])


def _classify_failure(db: Session, a: Attempt, gave_up: bool) -> tuple[str, dict]:
    f = DecisionFeatures(themes=(a.themes or "").split(), fail_ply=a.fail_ply, blind=a.mode == "blind" or
                         bool(a.assignment_id and a.mode == "intervention" and _assignment_blind(db, a)),
                         timed_out=a.timed_out)
    if a.candidates and a.exercise_kind == "puzzle":
        sol_first = puzzles.solution_moves(db.get(Puzzle, a.puzzle_id))[0]
        f.candidates_missed_solution = sol_first not in a.candidates
    times = a.move_times_ms or []
    fp = a.fail_ply or 0
    if fp < len(times):
        prev = times[fp - 1] if fp > 0 else 0
        f.think_s = (times[fp] - prev) / 1000
    if not gave_up and f.think_s is not None:
        f.impulsive_threshold_s = impulsive_threshold_ms(db, a.puzzle_rating) / 1000
    board = _solver_board(db, a)
    played = a.moves_played or []
    for mv in played[: 2 * fp]:
        board.push(chess.Move.from_uci(mv))
    f.phase = phase_of(board)
    wrong = played[2 * fp] if len(played) > 2 * fp else None
    if wrong and not a.timed_out and a.exercise_kind == "puzzle":
        try:
            ef = engine_features(get_engine(), board, chess.Move.from_uci(wrong), ERROR_ANALYSIS_DEPTH)
            for k, v in ef.as_dict().items():
                if getattr(f, k) in (None, [], False) and k not in ("themes",):
                    setattr(f, k, v)
            a.cp_loss = ef.cp_loss
        except EngineUnavailable as exc:
            log.warning("engine unavailable for error analysis: %s", exc)
    if gave_up and not wrong:
        # no move was played: it was not seen at all (or the line was not found)
        f.think_s = None
    cat = classify(f, "puzzle")
    return cat, f.as_dict()


def _assignment_blind(db: Session, a: Attempt) -> bool:
    asg = db.get(InterventionAssignment, a.assignment_id)
    return bool(asg and interventions.CATALOG[asg.intervention_key].blind)


def finish(db: Session, a: Attempt, correct: bool, total_ms: int, hesitation: dict | None, timed_out: bool = False,
           gave_up: bool = False, comparison: dict | None = None) -> dict:
    a.correct, a.timed_out, a.total_ms = bool(correct), timed_out, total_ms
    a.finished_at = utcnow()
    a.hesitation = hesitation or {}
    sess = db.get(TrainingSession, a.session_id) if a.session_id else None
    out: dict = {"finished": True, "correct": a.correct, "timed_out": timed_out, "attempt_id": a.id}
    # rating
    if a.exercise_kind == "puzzle" and a.mode not in UNRATED_MODES:
        p = db.get(Puzzle, a.puzzle_id)
        r, rd = current_rating(db)
        nr, nrd = glicko_update(r, rd, p.rating, p.rating_deviation, 1.0 if correct else 0.0)
        a.user_rating_after = nr
        db.add(RatingPoint(rating=nr, rd=nrd, attempt_id=a.id))
        out["rating"] = {"before": round(r), "after": round(nr), "rd": round(nrd)}
    # error DNA
    if not correct:
        cat, detail = _classify_failure(db, a, gave_up)
        a.error_category, a.error_detail = cat, detail
        out["error_dna"] = {"category": cat, "label": CATEGORIES[cat], "evidence": detail}
    # retention
    median = _median_ms(db, a.puzzle_rating)
    hes = (a.hesitation or {}).get("selection_changes", 0) >= 3
    cm = retention.record_exposure(db, a.concept, a.correct, retention.quality_from(a.correct, total_ms, median, hes))
    retention.record_probe(cm, a.retention_probe, a.correct)
    if cm is not None:
        out["retention"] = {"concept": cm.concept, "next_review_in_days": round(cm.interval_days, 2)}
    # intervention progress
    if a.assignment_id:
        asg = db.get(InterventionAssignment, a.assignment_id)
        asg.exercises_done += 1
        out["intervention"] = {"done": asg.exercises_done, "target": asg.exercises_target}
    # adaptive difficulty / pressure level
    db.flush()
    change = adaptive.update_after_attempt(db)
    if change:
        out["band_change"] = change
    if a.mode == "pressure":
        pc = pressure.update_level(db)
        if pc:
            out["pressure_change"] = pc
    # fatigue
    if sess is not None:
        sess.last_activity_at = utcnow()
        db.flush()
        trend = attention.session_trend(db, sess.id)
        if trend["suggest_break"]:
            out["break"] = {"recommendation": trend["recommendation"], "reasons": trend["reasons"],
                            "disclaimer": trend["disclaimer"]}
            if sess.break_suggested_at is None:
                sess.break_suggested_at = utcnow()
    # closed loop
    c = loop.advance(db)
    out["loop_phase"] = c.phase
    # feedback
    if a.exercise_kind == "puzzle":
        p = db.get(Puzzle, a.puzzle_id)
        out.update({"solution_san": puzzles.solution_san(p), "solution_uci": puzzles.solution_moves(p),
                    "themes": p.themes.split(), "explanation": explain(p.themes), "puzzle_rating": p.rating,
                    "game_url": p.game_url, "start_fen": puzzles.puzzle_start(p)["fen"]})
    else:
        gm = db.get(GameMistake, a.game_mistake_id)
        out.update({"best_san": gm.best_san, "your_game_move": gm.move_san, "comparison": comparison,
                    "category": gm.category})
    if a.candidates:
        out["candidates"] = _score_candidates(db, a)
    db.commit()
    return out


def _median_ms(db: Session, rating: int | None) -> float | None:
    q = select(Attempt.total_ms).where(Attempt.correct.is_(True), Attempt.total_ms.is_not(None))
    if rating:
        q = q.where(Attempt.puzzle_rating.between(rating - 200, rating + 200))
    xs = sorted(x for x in db.execute(q.order_by(Attempt.id.desc()).limit(100)).scalars() if x)
    return xs[len(xs) // 2] if len(xs) >= 5 else None


def _score_candidates(db: Session, a: Attempt) -> dict:
    board = _solver_board(db, a)
    truth = None
    if a.exercise_kind == "puzzle":
        truth = puzzles.solution_moves(db.get(Puzzle, a.puzzle_id))[0]
    top = []
    try:
        top = [l.move for l in get_engine().analyse(board, depth=ERROR_ANALYSIS_DEPTH, multipv=3)]
    except EngineUnavailable:
        pass
    best = truth or (top[0] if top else None)
    score = 1.0 if best in a.candidates else (0.5 if set(a.candidates) & set(top) else 0.0)
    a.candidate_score = score
    return {"listed": a.candidates, "solution": best, "engine_top3": top, "score": score}
