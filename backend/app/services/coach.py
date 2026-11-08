"""Optional AI coach. Default provider 'none' produces a deterministic explanation built only
from Stockfish output and stored Error DNA. An LLM can be plugged in through an
OpenAI-compatible HTTP adapter (COACH_PROVIDER=openai_compatible); it receives the engine
facts and is instructed not to invent evaluations. The LLM path is untested in this repo."""
from __future__ import annotations

import chess

from ..config import settings
from .engine import StockfishService


def engine_facts(engine: StockfishService, fen: str, move_uci: str | None, depth: int = 16) -> dict:
    board = chess.Board(fen)
    facts: dict = {"fen": fen, "side_to_move": "white" if board.turn else "black"}
    top = engine.analyse(board, depth=depth, multipv=3)
    facts["engine_lines"] = [{"san": l.san, "cp": l.cp, "mate": l.mate, "pv_san": l.pv_san[:8]} for l in top]
    if move_uci:
        facts["user_move"] = engine.compare_move(board, chess.Move.from_uci(move_uci), depth=depth)
    return facts


def _fmt(cp: int, mate: int | None) -> str:
    if mate is not None:
        return f"mate in {abs(mate)} ({'for' if mate > 0 else 'against'} the side to move)"
    return f"{cp / 100:+.2f}"


def rule_based(facts: dict) -> str:
    lines = facts["engine_lines"]
    if not lines:
        return "The position is terminal."
    best = lines[0]
    out = [f"Stockfish's best move is {best['san']} ({_fmt(best['cp'], best['mate'])}), "
           f"main line: {' '.join(best['pv_san'])}."]
    if len(lines) > 1:
        gap = best["cp"] - lines[1]["cp"]
        if gap >= 150:
            out.append(f"It is clearly the only good move: the next best, {lines[1]['san']}, is {gap / 100:.1f} "
                       "pawns worse — look for a concrete tactic.")
        else:
            out.append(f"Alternatives {', '.join(l['san'] for l in lines[1:])} are close; this is a choice between plans.")
    um = facts.get("user_move")
    if um and not um["is_best"]:
        out.append(f"Your move {um['user_san']} evaluates to {um['user_cp'] / 100:+.2f} vs {um['best_cp'] / 100:+.2f}"
                   f" ({um['verdict']}, {um['win_pct_loss']:.0f}% win-probability lost).")
    return " ".join(out)


def explain(engine: StockfishService, fen: str, move_uci: str | None = None) -> dict:
    facts = engine_facts(engine, fen, move_uci)
    text = rule_based(facts)
    provider = settings.coach_provider
    llm_text = None
    if provider == "openai_compatible" and settings.coach_api_key and settings.coach_base_url:
        llm_text = _llm(facts)
    return {"provider": provider if llm_text else "none", "text": llm_text or text, "engine_facts": facts}


def _llm(facts: dict) -> str | None:  # pragma: no cover - requires an external provider
    import httpx

    prompt = ("You are a chess coach. Explain in plain language, for a ~1500 player, the ideas behind the "
              "position. Use ONLY these Stockfish facts; never invent evaluations or claim a move is best "
              f"unless the facts say so.\nFACTS: {facts}")
    try:
        r = httpx.post(f"{settings.coach_base_url.rstrip('/')}/chat/completions", timeout=30,
                       headers={"Authorization": f"Bearer {settings.coach_api_key}"},
                       json={"model": settings.coach_model, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None
