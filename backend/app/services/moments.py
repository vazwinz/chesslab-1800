"""The day's session of "Seus erros de partida": the most valuable moments of the day's games, mixed
across games, plus the positions the ladder brings back (1, 3, 7 and 21 days).

A moment is one of your mistakes or blunders in a game, judged by the analysis. Its kind comes from
the win-% curve of the game (`Game.metrics["wins"]`, your side, one value per position):
- "decisive": the game was not lost before it, was after it, and never came back;
- "missed": the opponent had just given you a big chance and your move gave much of it back;
- "common": everything else (and every moment of a game analysed before the curve was kept).

The session is built once a day and kept in KV "daily_review", so it does not change under you;
games that arrive later are offered as a second round. Unanswered moments of the previous session
come back first the next day. Returns come from every attempt on a game position (also from before
this feature), capped per day, most overdue first."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import KV, Attempt, Game, GameMistake, utcnow

KIND_WEIGHT = {"decisive": 2.0, "missed": 1.8, "common": 1.0}
KIND_LABEL = {"decisive": "Erro decisivo", "missed": "Chance perdida", "common": "Erro"}
PATTERN_BONUS = 1.3          # the same Error DNA category in 2 or more of the day's games
INTERVALS = (1, 3, 7, 21)    # days until the next return, one step per correct answer
MASTERED_STREAK = 3          # correct answers in a row at the last step
NEW = {False: 5, True: 3}    # new moments per session (light day: True)
RETURNS = {False: 5, True: 3}
PER_GAME = 2                 # moments from one game, at most
SEVERITIES = ("mistake", "blunder")
KEY = "daily_review"


# ------------------------------------------------------------------ kinds
def kind_of(wins: list[float | None] | None, ply: int) -> str:
    """The kind of the moment at `ply` (your move), from the game's win-% curve."""
    if not wins or ply + 1 >= len(wins) or wins[ply] is None or wins[ply + 1] is None:
        return "common"
    before, after = wins[ply], wins[ply + 1]
    rest = [w for w in wins[ply + 2:] if w is not None]
    if before >= 50 and after < 25 and all(w <= 40 for w in rest):
        return "decisive"
    prev = wins[ply - 2] if ply >= 2 else None
    if prev is not None and before >= 70 and before - prev >= 20 and before - after >= 10:
        return "missed"
    return "common"


def time_note(kind: str, think_s: float | None, median_think_s: float | None) -> str | None:
    """A line for a fast decision on a move that decided the game (or threw away a gift): under 5 s,
    or under half your usual time in that game."""
    if kind not in ("decisive", "missed") or think_s is None:
        return None
    if not (think_s < 5 or (median_think_s and think_s < 0.5 * median_think_s)):
        return None
    s = f"{think_s:.1f}".replace(".", ",") if think_s < 2 else str(round(think_s))
    if kind == "decisive":
        return f"Você pensou {s} s no lance que decidiu a partida."
    return f"Você pensou {s} s na chance que ele te deu."


# ------------------------------------------------------------------ the ladder
def ladder(history: list[tuple[bool, datetime]]) -> tuple[date | None, int]:
    """(the date the position is due again, its step 0..4) from its answers in order; None = mastered.
    Correct: one step up (+1, +3, +7, +21 days). Wrong: tomorrow, one step down."""
    step, streak, due = 0, 0, None
    for correct, when in history:
        if correct:
            if step == len(INTERVALS):
                streak += 1
                if streak >= MASTERED_STREAK:
                    return None, step
            step = min(step + 1, len(INTERVALS))
            due = when.date() + timedelta(days=INTERVALS[step - 1])
        else:
            step, streak = max(step - 1, 0), 0
            due = when.date() + timedelta(days=1)
    return due, step


def _histories(db: Session) -> dict[int, list[tuple[bool, datetime]]]:
    rows = db.execute(select(Attempt.game_mistake_id, Attempt.correct, Attempt.finished_at)
                      .where(Attempt.exercise_kind == "game_position", Attempt.game_mistake_id.is_not(None),
                             Attempt.finished_at.is_not(None), Attempt.correct.is_not(None))
                      .order_by(Attempt.finished_at, Attempt.id)).all()
    out: dict[int, list[tuple[bool, datetime]]] = defaultdict(list)
    for mid, ok, when in rows:
        out[mid].append((bool(ok), when))
    return out


def due_returns(db: Session, day: date, limit: int) -> list[int]:
    """Mistakes the ladder brings back on `day` (or before), most overdue first."""
    due = []
    for mid, h in _histories(db).items():
        when, _ = ladder(h)
        if when is not None and when <= day:
            due.append((when, mid))
    if not due:
        return []
    live = {mid for mid, sev in db.execute(select(GameMistake.id, GameMistake.severity)
                                           .where(GameMistake.id.in_([m for _, m in due]))).all()
            if sev != "retired"}
    return [mid for _, mid in sorted(due) if mid in live][:limit]


def next_return_in(db: Session, mistake_id: int, today: date | None = None) -> int | None:
    """Days until this position comes back, after its latest answer; None = mastered."""
    when, _ = ladder(_histories(db).get(mistake_id, []))
    if when is None:
        return None
    return max(1, (when - (today or date.today())).days)


# ------------------------------------------------------------------ the session
def _item(m: GameMistake, g: Game, source: str) -> dict:
    return {"mistake_id": m.id, "game_id": g.id, "kind": kind_of((g.metrics or {}).get("wins"), m.ply),
            "source": source}


def _window_games(db: Session, day: date, days_back: int, again: str | None = None) -> list[Game]:
    """Analysed games of the last `days_back` days not looked at yet (`again`: also those looked at
    on that day, when an untouched session is rebuilt)."""
    gs = db.execute(select(Game).where(Game.analyzed.is_(True), Game.user_color.is_not(None),
                                       Game.played_on >= day - timedelta(days=days_back), Game.played_on <= day)
                    .order_by(Game.played_on.desc(), Game.id.desc())).scalars()
    return [g for g in gs if (g.metrics or {}).get("reviewed_on") in (None, again)]


def _candidates(db: Session, games: list[Game]) -> list[tuple[float, GameMistake, Game]]:
    by_id = {g.id: g for g in games}
    if not by_id:
        return []
    ms = list(db.execute(select(GameMistake).where(GameMistake.game_id.in_(by_id),
                                                   GameMistake.severity.in_(SEVERITIES))).scalars())
    games_per_cat: dict[str, set[int]] = defaultdict(set)
    for m in ms:
        games_per_cat[m.category].add(m.game_id)
    out = []
    for m in ms:
        g = by_id[m.game_id]
        score = m.win_pct_loss * KIND_WEIGHT[kind_of((g.metrics or {}).get("wins"), m.ply)]
        if len(games_per_cat[m.category]) >= 2:
            score *= PATTERN_BONUS
        out.append((score, m, g))
    out.sort(key=lambda t: (-t[0], t[1].id))
    return out


def _pick(cands: list[tuple[float, GameMistake, Game]], n: int, taken: set[int]) -> list[tuple[GameMistake, Game]]:
    per_game: dict[int, int] = defaultdict(int)
    out = []
    for _, m, g in cands:
        if len(out) >= n:
            break
        if m.id in taken or per_game[g.id] >= PER_GAME:
            continue
        per_game[g.id] += 1
        out.append((m, g))
    return out


def _order(picked: list[tuple[GameMistake, Game]]) -> list[tuple[GameMistake, Game]]:
    """Highest first, but the next one from another game and another category when there is one."""
    left, out = list(picked), []
    while left:
        prev = out[-1] if out else None
        nxt = next((x for x in left if prev is None or (x[1].id != prev[1].id and x[0].category != prev[0].category)),
                   None) or next((x for x in left if prev is None or x[1].id != prev[1].id), None) or left[0]
        left.remove(nxt)
        out.append(nxt)
    return out


def _mark_reviewed(games: list[Game], day: date) -> None:
    for g in games:
        g.metrics = {**(g.metrics or {}), "reviewed_on": day.isoformat()}


def _stored(db: Session) -> dict | None:
    kv = db.get(KV, KEY)
    return dict(kv.value) if kv and kv.value else None


def _save(db: Session, session: dict) -> None:
    kv = db.get(KV, KEY)
    if kv is None:
        db.add(KV(key=KEY, value=session))
    else:
        kv.value = session
    db.commit()


def answered(db: Session, session: dict) -> set[int]:
    """Mistakes of the session already answered in it (since it was built)."""
    since = datetime.fromisoformat(session["built_at"])
    ids = [i["mistake_id"] for i in session.get("items", [])]
    if not ids:
        return set()
    return set(db.execute(select(Attempt.game_mistake_id).where(
        Attempt.game_mistake_id.in_(ids), Attempt.mode == "daily_review",
        Attempt.finished_at.is_not(None), Attempt.finished_at >= since)).scalars())


def build_session(db: Session, day: date, light: bool, rebuild: bool = False) -> dict:
    """Build (and keep) the session of `day`: yesterday's unanswered moments, then the day's new
    moments mixed with the positions due again. `rebuild`: the stored session of the same day was not
    started, so its games are looked at again together with the ones that arrived since."""
    prev = _stored(db)
    carry: list[int] = []
    again = None
    if rebuild and prev and prev.get("day") == day.isoformat():
        carry, again = list(prev.get("carry") or []), day.isoformat()
    elif prev and prev.get("day") and prev["day"] < day.isoformat():
        done = answered(db, prev)
        carry = [i["mistake_id"] for i in prev.get("items", []) if i["mistake_id"] not in done]
    games = _window_games(db, day, 1, again) or _window_games(db, day, 3, again)
    new = _order(_pick(_candidates(db, games), NEW[light], set(carry)))
    new_ids = {m.id for m, _ in new}
    ret_ids = [mid for mid in dict.fromkeys(carry + due_returns(db, day, RETURNS[light] + len(carry)))
               if mid not in new_ids][:RETURNS[light]]
    rows = {m.id: (m, g) for m, g in db.execute(select(GameMistake, Game).join(Game, Game.id == GameMistake.game_id)
                                                 .where(GameMistake.id.in_(ret_ids))).all()} if ret_ids else {}
    returns = [_item(*rows[mid], "return") for mid in ret_ids if mid in rows and rows[mid][0].severity != "retired"]
    first = [r for r in returns if r["mistake_id"] in set(carry)]
    rest = [r for r in returns if r["mistake_id"] not in set(carry)]
    items = list(first)
    fresh = [_item(m, g, "new") for m, g in new]
    while fresh or rest:
        if fresh:
            items.append(fresh.pop(0))
        if rest:
            items.append(rest.pop(0))
    _mark_reviewed(games, day)
    session = {"day": day.isoformat(), "items": items, "built_at": utcnow().isoformat(), "light": light,
               "carry": carry}
    _save(db, session)
    return session


def today_session(db: Session, day: date | None = None, light: bool | None = None) -> dict:
    """The session of `day` (today), built on first use. Once you have answered a moment it stays as
    it is (later games are a second round); until then it takes in the games that arrive."""
    day = day or date.today()
    s = _stored(db)
    if s and s.get("day") == day.isoformat():
        if not answered(db, s) and new_games_since(db, s) > 0:
            return build_session(db, day, bool(s.get("light")) if light is None else light, rebuild=True)
        return s
    return build_session(db, day, bool(light))


def new_games_since(db: Session, session: dict) -> int:
    """Analysed games of the session's day (or the day before) not looked at yet: a second round."""
    return len(_window_games(db, date.fromisoformat(session["day"]), 1))


def second_round(db: Session, day: date | None = None) -> dict:
    """Add the moments of games that arrived after the session was built."""
    day = day or date.today()
    s = today_session(db, day)
    games = _window_games(db, day, 1)
    taken = {i["mistake_id"] for i in s["items"]}
    more = [_item(m, g, "new") for m, g in _order(_pick(_candidates(db, games), NEW[bool(s.get("light"))], taken))]
    _mark_reviewed(games, day)
    s = {**s, "items": s["items"] + more}
    _save(db, s)
    return s


# ------------------------------------------------------------------ where you think you lost
CALIBRATION_KEY = "calibration"
HIT_PLIES = 2  # your pick counts as right when it is the decisive move or one move either side


def decisive_ply(g: Game, ms: list[GameMistake]) -> int | None:
    """The move that lost the game: the first decisive moment, else your biggest drop."""
    wins = (g.metrics or {}).get("wins")
    errs = [m for m in ms if m.severity in SEVERITIES]
    dec = [m.ply for m in errs if kind_of(wins, m.ply) == "decisive"]
    if dec:
        return min(dec)
    return max(errs, key=lambda m: m.win_pct_loss).ply if errs else None


def _calibrations(db: Session) -> dict:
    kv = db.get(KV, CALIBRATION_KEY)
    return dict((kv.value or {}).get("games") or {}) if kv else {}


def calibration(db: Session, g: Game, ms: list[GameMistake]) -> dict:
    """For the review screen: whether this lost game still asks "onde você acha que perdeu?", your
    answer if any, and how often you were right over all games."""
    allc = _calibrations(db)
    mine = allc.get(str(g.id))
    answered = [c for c in allc.values() if c.get("picked_ply") is not None]
    return {"lost": (g.metrics or {}).get("result_for_user") == 0.0 and decisive_ply(g, ms) is not None,
            "asked": mine is not None, "picked_ply": (mine or {}).get("picked_ply"),
            "decisive_ply": (mine or {}).get("decisive_ply"), "hit": (mine or {}).get("hit"),
            "stats": {"hits": sum(1 for c in answered if c.get("hit")), "total": len(answered)}}


def record_calibration(db: Session, g: Game, ms: list[GameMistake], ply: int | None) -> dict:
    """Keep your pick (None: you skipped) and compare it with the move that lost the game."""
    dec = decisive_ply(g, ms)
    hit = None if ply is None or dec is None else abs(ply - dec) <= HIT_PLIES
    allc = _calibrations(db)
    allc[str(g.id)] = {"picked_ply": ply, "decisive_ply": dec, "hit": hit, "at": utcnow().isoformat()}
    kv = db.get(KV, CALIBRATION_KEY)
    if kv is None:
        db.add(KV(key=CALIBRATION_KEY, value={"games": allc}))
    else:
        kv.value = {"games": allc}
    db.commit()
    return calibration(db, g, ms)


# ------------------------------------------------------------------ whether it works
def _steps_before(history: list[tuple[bool, datetime]]) -> list[int]:
    """The ladder step each answer was given at (the same moves as `ladder`)."""
    step, out = 0, []
    for correct, _ in history:
        out.append(step)
        step = min(step + 1, len(INTERVALS)) if correct else max(step - 1, 0)
    return out


def _local_day(t: datetime) -> date:
    from datetime import timezone

    return t.replace(tzinfo=timezone.utc).astimezone().date()


def stats(db: Session, day: date | None = None) -> dict:
    """Numbers for Diagnóstico: how often positions coming back after 3 and after 7 days are solved,
    on how many days of this week you did the session, and how long a session takes (median)."""
    import statistics

    day = day or date.today()
    b3, b7 = [], []
    for h in _histories(db).values():
        for (ok, _), step in zip(h, _steps_before(h)):
            if step >= 2:
                b3.append(ok)
            if step >= 3:
                b7.append(ok)
    pct = lambda xs: round(100 * sum(xs) / len(xs)) if xs else None  # noqa: E731
    rows = db.execute(select(Attempt.served_at, Attempt.finished_at).where(
        Attempt.mode == "daily_review", Attempt.finished_at.is_not(None))).all()
    per_day: dict[date, list[tuple[datetime, datetime]]] = defaultdict(list)
    for served, finished in rows:
        per_day[_local_day(finished)].append((served or finished, finished))
    monday = day - timedelta(days=day.weekday())
    minutes = [(max(f for _, f in xs) - min(s for s, _ in xs)).total_seconds() / 60 for xs in per_day.values()]
    return {"returns_ok_3d": pct(b3), "returns_ok_7d": pct(b7),
            "session_days_week": sum(1 for d in per_day if monday <= d <= day),
            "median_session_min": round(statistics.median(minutes), 1) if minutes else None}
