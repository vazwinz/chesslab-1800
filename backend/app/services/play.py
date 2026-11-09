"""Play against the computer ("Jogar").

* Strength levels from about 400 to 2500. Stockfish cannot play below about 1320 on its own, so
  every level uses the same recipe: a shallow-to-deep search over the best few moves, a choice
  among them that tolerates bigger losses at lower levels, and, at the lowest levels, the odd
  plain blunder. The Elo numbers are approximate: they were not calibrated against people.
* Your own rating against the computer (Glicko, like the puzzles) moves after every game you
  play without help, and the automatic level follows it, so the opponent grows with you.
* Every move you make can be judged at once (the "alarme" for mistakes and blunders).
* Finished games are saved as games ("contra o AURA"), analysed like any other and feed the
  Error DNA and the cycle. They carry no rating of yours, so your real rating is untouched.
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timezone

import chess
import chess.pgn
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import KV, Game, GameMistake
from .engine import MATE_CP, StockfishService, classify_loss, win_pct
from .rating import glicko_update

MIN_ELO, MAX_ELO = 400, 2500
LEVELS = [(400, "Iniciante"), (600, "Aprendiz"), (800, "Novato"), (1000, "Clube"), (1200, "Intermediário"),
          (1400, "Experiente"), (1600, "Forte"), (1800, "Avançado"), (2000, "Expert"), (2200, "Mestre"),
          (2500, "Grande mestre")]
KEY = "play_rating"
LOG_KEY, LOG_MAX = "play_log", 400
BOT_RD = 60.0        # the levels are approximate, so a bot's rating is not exact either
START_RD = 300.0
HISTORY = 60
JUDGE_DEPTH = 12

# Openings to start from (moves in SAN from the initial position).
OPENINGS = [
    ("italiana", "Italiana", "e4 e5 Nf3 Nc6 Bc4 Bc5"),
    ("espanhola", "Espanhola", "e4 e5 Nf3 Nc6 Bb5 a6"),
    ("escocesa", "Escocesa", "e4 e5 Nf3 Nc6 d4 exd4"),
    ("gambito-do-rei", "Gambito do Rei", "e4 e5 f4 exf4"),
    ("siciliana", "Siciliana", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3"),
    ("francesa", "Francesa", "e4 e6 d4 d5"),
    ("caro-kann", "Caro-Kann", "e4 c6 d4 d5"),
    ("escandinava", "Escandinava", "e4 d5 exd5 Qxd5"),
    ("pirc", "Pirc", "e4 d6 d4 Nf6 Nc3 g6"),
    ("gambito-da-dama", "Gambito da Dama", "d4 d5 c4 e6"),
    ("eslava", "Eslava", "d4 d5 c4 c6"),
    ("londres", "Sistema Londres", "d4 d5 Bf4 Nf6 e3"),
    ("indiana-do-rei", "Índia do Rei", "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6"),
    ("inglesa", "Inglesa", "c4 e5"),
]


def clamp_elo(elo: float) -> int:
    return int(max(MIN_ELO, min(MAX_ELO, round(elo))))


def level_name(elo: float) -> str:
    name = LEVELS[0][1]
    for e, n in LEVELS:
        if elo >= e - 1:
            name = n
    return name


def strength(elo: float) -> dict:
    """How a level plays: search depth, candidate moves, how much loss it tolerates (temperature in
    centipawns: higher picks worse moves more often) and the chance of a plain blunder."""
    x = (clamp_elo(elo) - MIN_ELO) / (MAX_ELO - MIN_ELO)  # 0 .. 1
    return {
        "depth": int(round(2 + 14 * x)),                       # 2 at 400 .. 16 at 2500
        "multipv": 1 if x >= 0.85 else 4 if x >= 0.65 else 6,
        "temperature": 220 * math.exp(-4.2 * x),               # ~220 cp at 400, ~45 at 1200, ~3 at 2500
        "blunder": max(0.0, 0.18 * (1 - x / 0.45)),            # 18% at 400, ~3% at 1200, 0 from ~1350
    }


def engine_move(engine: StockfishService, board: chess.Board, elo: float,
                rng: random.Random | None = None) -> dict:
    """The computer's move at this level, with its evaluation (engine's point of view)."""
    if board.is_game_over():
        raise ValueError("a partida já terminou nesta posição")
    rng = rng or random.Random()
    p = strength(elo)
    lines = engine.analyse(board, depth=p["depth"], multipv=p["multipv"])
    if not lines:
        raise ValueError("a partida já terminou nesta posição")
    chosen = lines[0]
    if len(lines) > 1 or p["blunder"] > 0:
        if p["blunder"] > 0 and rng.random() < p["blunder"]:
            mv = rng.choice(list(board.legal_moves))  # a beginner's oversight: any legal move
            known = next((l for l in lines if l.move == mv.uci()), None)
            return {"move": mv.uci(), "san": board.san(mv), "eval_cp": known.cp if known else None,
                    "best": lines[0].move, "blunder": True}
        best = lines[0].cp
        weights = [math.exp(-max(0, best - l.cp) / max(1.0, p["temperature"])) for l in lines]
        chosen = rng.choices(lines, weights=weights, k=1)[0]
    return {"move": chosen.move, "san": chosen.san, "eval_cp": chosen.cp, "best": lines[0].move, "blunder": False}


def judge(engine: StockfishService, board: chess.Board, move: chess.Move, depth: int = JUDGE_DEPTH) -> dict:
    """How good your move was (your point of view), the best move and the opponent's best reply."""
    best = engine.analyse(board, depth=depth)
    if not best:
        raise ValueError("a partida já terminou nesta posição")
    after = board.copy()
    after.push(move)
    reply = None
    if after.is_checkmate():
        user_cp = MATE_CP
    elif after.is_game_over():
        user_cp = 0
    else:
        rl = engine.analyse(after, depth=depth)
        user_cp = -rl[0].cp if rl else 0
        reply = rl[0] if rl else None
    best_cp = best[0].cp
    loss = max(0.0, win_pct(best_cp) - win_pct(user_cp))
    verdict = "best" if move.uci() == best[0].move else classify_loss(loss)
    return {"verdict": verdict, "cp_loss": max(0, best_cp - user_cp), "win_pct_loss": round(loss, 1),
            "user_uci": move.uci(), "user_san": board.san(move), "best_uci": best[0].move, "best_san": best[0].san,
            "eval_after_cp": user_cp, "reply_uci": reply.move if reply else None,
            "reply_san": reply.san if reply else None}


# ------------------------------------------------------------------ your rating against the computer
def _seed(db: Session) -> tuple[float, float, str]:
    """A first guess: your real rating (latest game with your rating in its headers), else 800."""
    real = db.execute(select(Game.user_elo).where(Game.user_elo.is_not(None))
                      .order_by(Game.played_on.desc().nulls_last(), Game.id.desc()).limit(1)).scalar()
    if real:
        return float(real), 200.0, "rating real das suas partidas"
    return 800.0, START_RD, "ponto de partida"


def state(db: Session) -> dict:
    kv = db.get(KV, KEY)
    if kv is None or not isinstance(kv.value, dict) or "rating" not in kv.value:
        r, rd, src = _seed(db)
        st = {"rating": r, "rd": rd, "games": 0, "wins": 0, "draws": 0, "losses": 0, "history": [], "seed": src}
    else:
        st = dict(kv.value)
    st["suggested_level"] = suggested_level(st["rating"])
    st["level_name"] = level_name(st["suggested_level"])
    return st


def suggested_level(rating: float) -> int:
    """The automatic level: your rating, so each game is about even (rounded to 50)."""
    return clamp_elo(round(rating / 50) * 50)


def record(db: Session, level: float, score: float, game_id: int | None) -> dict:
    st = state(db)
    before = st["rating"]
    r, rd = glicko_update(st["rating"], st["rd"], float(clamp_elo(level)), BOT_RD, score)
    st.update(rating=round(r, 1), rd=round(max(BOT_RD, rd), 1), games=st["games"] + 1)
    key = "wins" if score == 1 else "losses" if score == 0 else "draws"
    st[key] = st.get(key, 0) + 1
    st["history"] = (st.get("history") or [])[-(HISTORY - 1):] + [{
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "level": clamp_elo(level),
        "score": score, "rating": st["rating"], "game_id": game_id}]
    for k in ("suggested_level", "level_name"):
        st.pop(k, None)
    kv = db.get(KV, KEY)
    if kv is None:
        db.add(KV(key=KEY, value=st))
    else:
        kv.value = st
    db.commit()
    return {"rating_before": round(before, 1), "rating_after": st["rating"],
            "next_level": suggested_level(st["rating"]), "next_level_name": level_name(suggested_level(st["rating"]))}


def log_game(db: Session, game_id: int | None, practice: bool, helped: bool, plies: int, score: float) -> None:
    """Every finished game, rated or not (the routine counts today's games from it)."""
    kv = db.get(KV, LOG_KEY)
    log = list(kv.value) if kv and isinstance(kv.value, list) else []
    log = (log + [{"day": date.today().isoformat(), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "game_id": game_id, "practice": practice, "helped": helped, "plies": plies, "score": score}])[-LOG_MAX:]
    if kv is None:
        db.add(KV(key=LOG_KEY, value=log))
    else:
        kv.value = log
    db.commit()


def games_on(db: Session, day: date) -> int:
    """Games played on that (local) day that count for the routine: from an even start, two plies or more."""
    kv = db.get(KV, LOG_KEY)
    log = kv.value if kv and isinstance(kv.value, list) else []
    return sum(1 for g in log if g.get("day") == day.isoformat() and not g.get("practice") and g.get("plies", 0) >= 2)


# ------------------------------------------------------------------ where a game can start
def openings_list() -> list[dict]:
    out = []
    for key, name, san in OPENINGS:
        b = chess.Board()
        for s in san.split():
            b.push_san(s)
        out.append({"id": key, "name": name, "moves": san, "fen": b.fen()})
    return out


def mistake_starts(db: Session, limit: int = 30) -> list[dict]:
    """Positions right before your mistakes in analysed games, worst first, newest first."""
    rank = {"blunder": 0, "mistake": 1, "inaccuracy": 2}
    rows = db.execute(select(GameMistake, Game).join(Game, Game.id == GameMistake.game_id)
                      .where(GameMistake.severity.in_(("blunder", "mistake")))
                      .order_by(Game.played_on.desc().nulls_last(), GameMistake.id.desc()).limit(200)).all()
    items = [{"id": m.id, "game_id": g.id, "fen": m.fen_before, "move": m.move_san, "best": m.best_san,
              "severity": m.severity, "category": m.category, "ply": m.ply, "date": g.played_on.isoformat() if g.played_on else None,
              "opponent": g.black if g.user_color == "white" else g.white,
              "color": "white" if chess.Board(m.fen_before).turn == chess.WHITE else "black"} for m, g in rows]
    items.sort(key=lambda x: rank.get(x["severity"], 3))
    return items[:limit]


# ------------------------------------------------------------------ saving a finished game
def pgn_for(start_fen: str, moves_uci: list[str], user_color: str, level: int, result: str, reason: str,
            time_control: str | None, opening: str | None) -> str:
    board = chess.Board(start_fen)
    game = chess.pgn.Game()
    if start_fen != chess.STARTING_FEN:
        game.setup(board)
    now = datetime.now(timezone.utc)
    bot = f"AURA {level} ({level_name(level)})"
    game.headers.update({
        "Event": "AURA, jogar contra o computador", "Site": "AURA", "Date": now.strftime("%Y.%m.%d"),
        "UTCDate": now.strftime("%Y.%m.%d"), "UTCTime": now.strftime("%H:%M:%S"),
        "White": "Você" if user_color == "white" else bot, "Black": "Você" if user_color == "black" else bot,
        "Result": result, "Termination": reason, "TimeControl": time_control or "-",
        ("BlackElo" if user_color == "white" else "WhiteElo"): str(level),  # only the computer's rating
    })
    if opening:
        game.headers["Opening"] = opening
    node = game
    for u in moves_uci:
        mv = chess.Move.from_uci(u)
        if mv not in board.legal_moves:
            raise ValueError(f"lance ilegal na partida: {u}")
        node = node.add_variation(mv)
        board.push(mv)
    return str(game)
