"""Dashboard statistics, computed with SQL aggregates over the stored attempts, ratings, games
and the routine's daily rows (nothing is estimated). Days are calendar days in this computer's time zone."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..cognitive.stats import wilson
from ..models import Attempt, Game, RatingPoint, TrainingSession
from ..timeutil import iso, local_date
from . import adaptive, prefs
from .routine import consistency
from .rating import current_rating

MIN_THEME_N = 5
TIME_CLASSES = {"bullet": "Bullet", "blitz": "Blitz", "rapid": "Rápidas", "daily": "Diárias"}


def _graded_puzzles():
    return (Attempt.correct.is_not(None), Attempt.exercise_kind == "puzzle")


def _ok():
    return func.coalesce(func.sum(case((Attempt.correct.is_(True), 1), else_=0)), 0)


def overview(db: Session) -> dict:
    r, rd = current_rating(db)
    n_graded = db.execute(select(func.count()).select_from(Attempt).where(Attempt.correct.is_not(None))).scalar() or 0
    n_puz, solved = db.execute(select(func.count(), _ok()).where(*_graded_puzzles())).one()

    # minutes of measured solving time per local day, last 28 days
    start = date.today() - timedelta(days=27)
    since_utc = datetime.combine(start - timedelta(days=1), datetime.min.time())
    per_day: dict[date, float] = defaultdict(float)
    for served, ms in db.execute(select(Attempt.served_at, Attempt.total_ms).where(
            Attempt.correct.is_not(None), Attempt.total_ms.is_not(None), Attempt.served_at >= since_utc)):
        per_day[local_date(served)] += (ms or 0) / 60000
    daily = [{"day": (start + timedelta(days=i)).isoformat(),
              "minutes": round(per_day.get(start + timedelta(days=i), 0), 1)} for i in range(28)]

    # themes: two light columns of your attempts (a join with the 15M-row puzzle_themes table made
    # SQLite walk that whole table)
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for themes_txt, ok in db.execute(select(Attempt.themes, Attempt.correct).where(*_graded_puzzles())):
        for t in (themes_txt or "").split():
            tally[t][0] += 1
            tally[t][1] += int(bool(ok))
    themes = [{"theme": t, **wilson(ok, n)} for t, (n, ok) in tally.items() if n >= MIN_THEME_N]
    weakest = sorted(themes, key=lambda x: (x["rate"], -x["n"]))[:6]
    strongest = sorted(themes, key=lambda x: (-x["rate"], -x["n"]))[:6]

    # success by rating band
    by_band = []
    for b in adaptive.BANDS:
        n, ok = db.execute(select(func.count(), _ok()).where(*_graded_puzzles(), Attempt.puzzle_rating >= b["min"],
                                                             Attempt.puzzle_rating < b["max"])).one()
        by_band.append({"band": b["label"], "range": f"{b['min']}–{b['max']}", **wilson(int(ok), int(n))})

    # current streak of consecutive correct puzzles
    streak, offset, broken = 0, 0, False
    while not broken:
        chunk = db.execute(select(Attempt.correct).where(*_graded_puzzles()).order_by(Attempt.id.desc())
                           .limit(500).offset(offset)).scalars().all()
        for c in chunk:
            if not c:
                broken = True
                break
            streak += 1
        if len(chunk) < 500:
            break
        offset += 500

    # median solving time of correct puzzles
    cond = (*_graded_puzzles(), Attempt.correct.is_(True), Attempt.total_ms.is_not(None))
    n_ok_times = db.execute(select(func.count()).select_from(Attempt).where(*cond)).scalar() or 0
    median_ms = db.execute(select(Attempt.total_ms).where(*cond).order_by(Attempt.total_ms).limit(1)
                           .offset(n_ok_times // 2)).scalar() if n_ok_times else None

    # rating series, down-sampled to ~300 points (the last point is always included)
    n_pts = db.execute(select(func.count()).select_from(RatingPoint)).scalar() or 0
    step = max(1, n_pts // 300)
    q = select(RatingPoint.ts, RatingPoint.rating).order_by(RatingPoint.id)
    if step > 1:
        q = q.where(RatingPoint.id % step == 0)
    series = [{"ts": iso(t), "rating": round(v, 1)} for t, v in db.execute(q)]
    last = db.execute(select(RatingPoint.ts, RatingPoint.rating).order_by(RatingPoint.id.desc()).limit(1)).first()
    if last and (not series or series[-1]["ts"] != iso(last[0])):
        series.append({"ts": iso(last[0]), "rating": round(last[1], 1)})

    # last sessions, aggregated in one query
    sessions = db.execute(select(TrainingSession).order_by(TrainingSession.id.desc()).limit(15)).scalars().all()
    agg = {}
    if sessions:
        agg = {sid: (int(n), int(ok), int(ms or 0)) for sid, n, ok, ms in db.execute(
            select(Attempt.session_id, func.count(), _ok(), func.coalesce(func.sum(Attempt.total_ms), 0))
            .where(Attempt.session_id.in_([s.id for s in sessions]), Attempt.correct.is_not(None))
            .group_by(Attempt.session_id))}
    hist = []
    for s in sessions:
        n, ok, ms = agg.get(s.id, (0, 0, 0))
        if not n:
            continue  # opened and closed without finishing an exercise
        hist.append({"id": s.id, "kind": s.kind, "theme": s.theme, "started_at": iso(s.started_at), "attempts": n,
                     "correct": ok, "minutes": round(ms / 60000, 1), "break_suggested": s.break_suggested_at is not None})

    games = db.execute(select(Game).where(Game.analyzed.is_(True)).order_by(Game.played_on, Game.id)).scalars().all()
    return {
        "has_data": bool(n_graded),
        "rating": {"current": round(r), "rd": round(rd), "provisional": rd > 110, "series": series,
                   "note": "Rating de puzzle (Glicko-1 contra os ratings dos puzzles do Lichess). "
                           "Não é o rating do Chess.com."},
        "real_rating": real_rating(db),
        "band": adaptive.band_for(db),
        "totals": {"attempts": int(n_puz), "solved": int(solved), "accuracy": wilson(int(solved), int(n_puz)),
                   "current_streak": streak, "median_solve_ms": median_ms, "mistakes": int(n_puz) - int(solved)},
        "daily_minutes": daily, "weakest_themes": weakest, "strongest_themes": strongest, "by_band": by_band,
        "consistency": consistency(db), "history": hist,
        "games": [{"id": g.id, "date": g.played_on.isoformat() if g.played_on else None, "white": g.white,
                   "black": g.black, "result": g.result, "time_class": g.time_class, "user_elo": g.user_elo,
                   **{k: g.metrics.get(k) for k in ("accuracy", "acpl", "blunders", "mistakes", "inaccuracies",
                                                     "user_moves", "blunders_per_100")}} for g in games],
    }


def real_rating(db: Session) -> dict:
    """Your rating as written in the headers of the games you imported (Chess.com / Lichess)."""
    p = prefs.get_prefs(db)
    rows = db.execute(select(Game.played_on, Game.imported_at, Game.id, Game.time_class, Game.user_elo, Game.source)
                      .where(Game.user_elo.is_not(None)).order_by(Game.played_on, Game.id)).all()
    by_class: dict[str, list] = defaultdict(list)
    for played, imported, gid, tc, elo, src in rows:
        day = played or local_date(imported)
        by_class[tc or "?"].append({"date": day.isoformat() if day else None, "elo": elo, "game_id": gid,
                                    "source": src})
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    classes = []
    for tc, pts in by_class.items():
        before = [x["elo"] for x in pts if x["date"] and x["date"] < cutoff]
        classes.append({"time_class": tc, "label": TIME_CLASSES.get(tc, "Outros"), "games": len(pts),
                        "current": pts[-1]["elo"], "best": max(x["elo"] for x in pts), "first": pts[0]["elo"],
                        "change_30d": pts[-1]["elo"] - before[-1] if before else None, "series": pts[-300:]})
    classes.sort(key=lambda c: -c["games"])
    goal_tc = p.get("goal_time_class") or "auto"
    main = next((c for c in classes if c["time_class"] == goal_tc), None) if goal_tc != "auto" else None
    main = main or (classes[0] if classes else None)
    goal = int(p.get("goal_rating") or 1800)
    return {"goal": goal, "goal_time_class": main["time_class"] if main else None, "classes": classes,
            "main": main, "to_goal": (goal - main["current"]) if main else None,
            "note": "Rating escrito no cabeçalho das partidas que você importou (WhiteElo/BlackElo). Ele só "
                    "atualiza quando você importa partidas novas."}
