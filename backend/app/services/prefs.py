"""Interface preferences, stored in the database (the desktop window does not keep browser
storage between launches, so the database is the only place a choice is really remembered)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import KV

KEY = "ui_prefs"
DEFAULTS: dict = {
    "theme": "system",          # system | light | dark
    "board_theme": "grafite",   # grafite | torneio | madeira | oceano
    "show_coordinates": True,
    "show_legal_moves": True,
    "animation_ms": 180,
    "sound": True,
    "volume": 0.7,
    "auto_next": False,         # go to the next puzzle automatically after a correct solve
    "notation": "figurine",     # figurine (♘f3) | letters (Nf3)
    "tour_done": False,
    "player_names": "",         # your Chess.com/Lichess usernames, comma separated
    "update_check": True,
    "dismissed_version": None,
    "goal_rating": 1800,
    "goal_time_class": "auto",   # auto (the class you play most) | bullet | blitz | rapid | daily
    "chesscom_username": "",
    # arrows on the analysis and review boards (each can be switched off under the board)
    "arrows_best": True,        # Stockfish's best move
    "arrows_played": True,      # the move you played, at each of your mistakes
    "arrows_opponent": True,    # the opponent's threat before your move and the reply that punishes it
    "arrows_others": True,      # Stockfish's 2nd and 3rd moves (analysis board)
    # "Jogar" (against the computer)
    "play_alarm": "forte",      # mistakes and blunders: forte (red screen until you click) | leve (a flash) | desligado
    "play_color": "white",      # white | black | random
    "play_clock": "none",       # none | 5+3 | 10+5 | 15+10 | 30+0
    "play_hints": 3,            # hints per game, 0-5 (a hint makes the game unrated)
    "play_takebacks": True,     # allow taking a move back (makes the game unrated)
    "play_auto_level": True,    # the level follows your rating against the computer
    "play_level": 1000,         # the level when it does not
    "play_show_eval": False,    # evaluation bar during the game
}
CHOICES = {
    "theme": {"system", "light", "dark"},
    "board_theme": {"torneio", "grafite", "madeira", "oceano"},
    "notation": {"figurine", "letters"},
    "goal_time_class": {"auto", "bullet", "blitz", "rapid", "daily"},
    "play_alarm": {"forte", "leve", "desligado"},
    "play_color": {"white", "black", "random"},
    "play_clock": {"none", "5+3", "10+5", "15+10", "30+0"},
}


def get_prefs(db: Session) -> dict:
    kv = db.get(KV, KEY)
    stored = dict(kv.value) if kv and isinstance(kv.value, dict) else {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def update_prefs(db: Session, changes: dict) -> dict:
    cur = get_prefs(db)
    for k, v in changes.items():
        if k not in DEFAULTS:
            raise ValueError(f"preferência desconhecida: {k}")
        default = DEFAULTS[k]
        if k in CHOICES and v not in CHOICES[k]:
            raise ValueError(f"valor inválido para {k}: {v!r}")
        if isinstance(default, bool) and not isinstance(v, bool):
            raise ValueError(f"{k} deve ser verdadeiro ou falso")
        if k == "volume":
            v = max(0.0, min(1.0, float(v)))
        if k == "animation_ms":
            v = max(0, min(600, int(v)))
        if k == "player_names":
            v = ", ".join(n.strip() for n in str(v).split(",") if n.strip())[:300]
        if k == "dismissed_version" and v is not None:
            v = str(v)[:20]
        if k == "goal_rating":
            v = max(400, min(3200, int(v)))
        if k == "chesscom_username":
            v = str(v).strip()[:40]
        if k == "play_hints":
            v = max(0, min(5, int(v)))
        if k == "play_level":
            v = max(400, min(2500, int(v)))
        cur[k] = v
    kv = db.get(KV, KEY)
    if kv is None:
        db.add(KV(key=KEY, value=cur))
    else:
        kv.value = cur
    db.commit()
    return cur


def player_names(db: Session) -> list[str]:
    return [n.strip() for n in (get_prefs(db).get("player_names") or "").split(",") if n.strip()]
