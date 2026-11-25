"""One Portuguese sentence for why a move fails, from the line that punishes it (your move, the
opponent's best reply, and what follows). Moves are wrapped in [[ ]] so the screen shows them in
the owner's notation (figurines or letters).

First match wins: a mate in the line; the reply takes a piece you left without enough defence; the
reply attacks two valuable pieces at once (a fork); the reply pins one of your pieces to the king
or the queen. Anything else returns None (the screen then says the reply gains the advantage)."""
from __future__ import annotations

import chess

from .judgement import VALUE, see

NAME = {chess.PAWN: "peão", chess.KNIGHT: "cavalo", chess.BISHOP: "bispo", chess.ROOK: "torre",
        chess.QUEEN: "dama", chess.KING: "rei"}
FEMININE = {chess.ROOK, chess.QUEEN}


def _the(piece_type: int) -> str:
    return ("a " if piece_type in FEMININE else "o ") + NAME[piece_type]


def _your(piece_type: int) -> str:
    return ("sua " if piece_type in FEMININE else "seu ") + NAME[piece_type]


def _line(fen: str, ucis: list[str]) -> list[tuple[chess.Board, chess.Move]] | None:
    """(the position before each move, the move), or None when the line is not legal."""
    board, out = chess.Board(fen), []
    for u in ucis:
        try:
            mv = chess.Move.from_uci(u)
        except ValueError:
            return None
        if mv not in board.legal_moves:
            return None
        out.append((board.copy(stack=False), mv))
        board.push(mv)
    return out


def _mate(steps: list[tuple[chess.Board, chess.Move]]) -> int | None:
    """The opponent's mate in the line, in moves of theirs (the moves at odd places are theirs)."""
    for i, (b, mv) in enumerate(steps):
        if i % 2 == 1:
            after = b.copy(stack=False)
            after.push(mv)
            if after.is_checkmate():
                return (i + 1) // 2
    return None


def describe(fen: str, refutation: list[str]) -> str | None:
    steps = _line(fen, refutation or [])
    if not steps or len(steps) < 2:
        return None
    (start, mine), (before_reply, reply) = steps[0], steps[1]
    me = start.turn
    my_san = start.san(mine)
    reply_san = before_reply.san(reply)
    n = _mate(steps)
    if n is not None:
        return f"Depois de [[{my_san}]], ele dá mate em {n}."
    victim = before_reply.piece_at(reply.to_square)
    if victim is not None and victim.color == me and see(before_reply, reply) > 0:
        return f"Depois de [[{my_san}]], ele captura {_the(victim.piece_type)} em {chess.square_name(reply.to_square)}."
    after = before_reply.copy(stack=False)
    after.push(reply)
    attacker = after.piece_at(reply.to_square)
    targets = [after.piece_at(sq) for sq in after.attacks(reply.to_square)]
    targets = [p for p in targets if p is not None and p.color == me
               and (p.piece_type == chess.KING or VALUE[p.piece_type] >= 3)]
    if attacker is not None and len(targets) >= 2:
        a, b = sorted(targets, key=lambda p: (p.piece_type != chess.KING, -VALUE[p.piece_type]))[:2]
        return (f"Depois de [[{my_san}]], [[{reply_san}]] ataca {_the(a.piece_type)} e {_the(b.piece_type)} "
                "ao mesmo tempo.")
    for sq in chess.SQUARES:
        p = after.piece_at(sq)
        if p is None or p.color != me or p.piece_type == chess.KING:
            continue
        if after.is_pinned(me, sq) and not before_reply.is_pinned(me, sq):
            return f"Depois de [[{reply_san}]], {_your(p.piece_type)} fica cravad{'a' if p.piece_type in FEMININE else 'o'}."
    return None
