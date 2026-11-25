"""The rule of the day: an if-then plan ("se… então") from the Error DNA category you missed most in
today's session of "Seus erros de partida". You accept it (as is or edited) or skip it; the accepted
rule shows the next day on the start screen and before a game, with how often that kind of mistake
came up in your games before and after it. Kept in KV "rules"."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cognitive.error_dna import INFO
from ..models import KV, Attempt, Game, GameMistake, utcnow
from .moments import SEVERITIES

KEY = "rules"
TEMPLATES = {
    "tactical_blindness": "Se tem captura ou xeque na posição, eu olho todos antes de decidir.",
    "calculation_error": "Se a minha linha tem troca, eu conto até o fim quem fica com o quê.",
    "missed_opponent_threat": "Se ele acabou de mexer, eu pergunto o que esse lance ameaça.",
    "impulsive_decision": "Se a posição está tensa, eu espero 10 segundos antes de jogar.",
    "poor_candidate_selection": "Se não é lance forçado, eu acho 3 candidatos antes de escolher.",
    "positional_misunderstanding": "Se não tem tática, eu melhoro a minha pior peça.",
    "time_management_failure": "Se passei da metade do tempo na abertura, eu jogo os lances simples rápido.",
    "endgame_technique_failure": "Se é final, eu ativo o rei antes de tudo.",
}


def _label(category: str) -> str:
    return (INFO.get(category) or {}).get("name") or category


def suggestion(db: Session, day: date) -> dict | None:
    """The rule for the category of the moments you missed most today (ties: the latest one)."""
    from .routine import _bounds

    lo, hi = _bounds(day)
    rows = db.execute(select(GameMistake.category, Attempt.finished_at)
                      .join(GameMistake, GameMistake.id == Attempt.game_mistake_id)
                      .where(Attempt.mode == "daily_review", Attempt.correct.is_(False),
                             Attempt.finished_at >= lo, Attempt.finished_at < hi)
                      .order_by(Attempt.finished_at)).all()
    rows = [(c, t) for c, t in rows if c in TEMPLATES]
    if not rows:
        return None
    counts = Counter(c for c, _ in rows)
    top = max(counts.values())
    latest = {c: t for c, t in rows}
    cat = max((c for c, n in counts.items() if n == top), key=lambda c: latest[c])
    return {"category": cat, "label": _label(cat), "text": TEMPLATES[cat]}


def history(db: Session) -> list[dict]:
    """Accepted rules, newest first."""
    kv = db.get(KV, KEY)
    items = list((kv.value or {}).get("rules") or []) if kv else []
    return sorted(items, key=lambda r: r["day"], reverse=True)


def _save(db: Session, items: list[dict]) -> None:
    kv = db.get(KV, KEY)
    if kv is None:
        db.add(KV(key=KEY, value={"rules": items}))
    else:
        kv.value = {"rules": items}
    db.commit()


def accept(db: Session, text: str, category: str, day: date | None = None) -> dict:
    day = day or date.today()
    rule = {"day": day.isoformat(), "category": category, "text": " ".join((text or "").split())[:200] or TEMPLATES.get(category, ""),
            "accepted_at": utcnow().isoformat()}
    _save(db, [r for r in history(db) if r["day"] != rule["day"]] + [rule])
    return rule


def remove(db: Session, day: date | None = None) -> None:
    day = day or date.today()
    _save(db, [r for r in history(db) if r["day"] != day.isoformat()])


def accepted_on(db: Session, day: date) -> dict | None:
    return next((r for r in history(db) if r["day"] == day.isoformat()), None)


def active(db: Session, day: date) -> dict | None:
    """The rule in force on `day`: the newest one accepted on an earlier day."""
    return next((r for r in history(db) if r["day"] < day.isoformat()), None)


def trend(db: Session, category: str, day: date) -> dict:
    """That category's mistakes in your games of the 7 days before `day` and of the 7 days from it
    (only games judged with the current criteria)."""
    def count(lo: date, hi: date) -> tuple[int, int]:
        games = [g for g in db.execute(select(Game).where(Game.analyzed.is_(True), Game.user_color.is_not(None),
                                                           Game.played_on >= lo, Game.played_on <= hi)).scalars()
                 if int((g.metrics or {}).get("criteria") or 1) >= 2]
        ids = [g.id for g in games]
        n = len(db.execute(select(GameMistake.id).where(GameMistake.game_id.in_(ids), GameMistake.category == category,
                                                        GameMistake.severity.in_(SEVERITIES))).all()) if ids else 0
        return n, len(games)

    before, games_before = count(day - timedelta(days=7), day - timedelta(days=1))
    after, games_after = count(day, day + timedelta(days=6))
    return {"before": before, "after": after, "games_before": games_before, "games_after": games_after}


def state(db: Session, day: date | None = None) -> dict:
    """What the screens need: today's suggestion, the rule accepted today (for tomorrow), the one in
    force today with its trend."""
    day = day or date.today()
    act = active(db, day)
    if act:
        act = {**act, "label": _label(act["category"]), "trend": trend(db, act["category"], date.fromisoformat(act["day"]))}
    return {"suggestion": suggestion(db, day), "today": accepted_on(db, day), "active": act}
