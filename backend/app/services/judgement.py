"""How one move is judged, everywhere in AURA (game review, Jogar, the coach): one function, so the
same move always gets the same verdict.

Verdicts follow Lichess (lila `Advice.scala`): the drop in winning chances on its -1..1 scale of
0.1 / 0.2 / 0.3 is, on the 0..100 win-% scale used here, 5 / 10 / 15 points; forced mates follow
Lichess' MateAdvice. The user's move is searched from the same root position as the best move
(`go searchmoves`), so both scores come from the same search and the best move never loses points
to search noise. On top of the errors, two marks for good moves:

- "brilliant" (!!): a sacrifice (the opponent can win material from the moved piece) that is the
  engine's move, in a position that was not already won (unless it keeps a forced mate) and is not
  lost after it.
- "great" (!, "lance único"): the engine's move when every other move drops at least 10 points and
  none of them keeps a clear win; never a recapture, a move out of check, a grab of free
  material or a mate in one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import pstdev

import chess

from .engine import Line, StockfishService, classify_loss, win_pct

CRITERIA = 2  # bump when the judging changes: games analysed with older criteria are offered a re-analysis

VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}

BRILLIANT_MIN_OFFER = 2      # at least a minor piece for a pawn, or the exchange
BRILLIANT_MAX_BEFORE = 90.0  # win-% before: in a position already this won, a sacrifice is not brilliant
BRILLIANT_MIN_AFTER = 45.0   # win-% after: not brilliant if it leaves you worse
NEAR_BEST = 2.0              # win-% loss still counted as "the engine's move" for a sacrifice
GREAT_GAP = 10.0             # every other move would be at least a mistake
GREAT_MAX_SECOND = 75.0      # ... and the second-best does not keep a clear win (about +3)


def classify_move(best_cp: int, best_mate: int | None, user_cp: int, user_mate: int | None) -> str:
    """Verdict for a move, mover's point of view: the best line's score and the played move's score."""
    had_mate = best_mate is not None and best_mate > 0
    keeps_mate = user_mate is not None and user_mate > 0
    gets_mated = user_mate is not None and user_mate < 0
    was_mated = best_mate is not None and best_mate < 0
    if had_mate and not keeps_mate:  # a forced mate slipped away: judged by what is left
        if gets_mated:
            return "blunder"
        return "inaccuracy" if user_cp > 999 else "mistake" if user_cp > 700 else "blunder"
    if gets_mated and not was_mated:  # walked into a forced mate: judged by how bad it already was
        return "inaccuracy" if best_cp < -999 else "mistake" if best_cp < -700 else "blunder"
    if had_mate or was_mated:  # mate either way, sooner or later
        return "good"
    return classify_loss(max(0.0, win_pct(best_cp) - win_pct(user_cp)))


# ------------------------------------------------------------------ material: static exchange
def _captured_value(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        return VALUE[chess.PAWN]
    p = board.piece_at(move.to_square)
    return VALUE[p.piece_type] if p and p.color != board.turn else 0


def _exchange_on(board: chess.Board, sq: chess.Square) -> int:
    """What the side to move wins by capturing on `sq` with its least valuable piece and going on
    with the exchange; 0 when it is better not to capture."""
    if board.piece_at(sq) is None:
        return 0
    caps = [m for m in board.legal_moves if m.to_square == sq]
    if not caps:
        return 0
    m = min(caps, key=lambda c: VALUE[board.piece_type_at(c.from_square)])
    gain = VALUE[board.piece_type_at(sq)] + (VALUE[m.promotion] - 1 if m.promotion else 0)
    b = board.copy(stack=False)
    b.push(m)
    return max(0, gain - _exchange_on(b, sq))


def see(board: chess.Board, move: chess.Move) -> int:
    """Static exchange of `move` (any move) for the side playing it, in pawns: what it captures
    minus what the opponent then wins by capturing the moved piece."""
    gain = _captured_value(board, move) + (VALUE[move.promotion] - 1 if move.promotion else 0)
    b = board.copy(stack=False)
    b.push(move)
    return gain - _exchange_on(b, move.to_square)


def offered_material(board: chess.Board, move: chess.Move) -> int:
    """How much material the move offers: what the opponent can win from the moved piece."""
    return max(0, -see(board, move))


def _recapture(board: chess.Board, move: chess.Move) -> bool:
    if not board.move_stack or not board.is_capture(move):
        return False
    last = board.peek()
    if last.to_square != move.to_square:
        return False
    prev = board.copy()
    prev.pop()
    return prev.is_capture(last)


def _mates(board: chess.Board, move: chess.Move) -> bool:
    b = board.copy(stack=False)
    b.push(move)
    return b.is_checkmate()


def highlight(board: chess.Board, move: chess.Move, top: list[Line], user: Line) -> str | None:
    """"brilliant", "great" or None for the move played (`user` is its line, from the same root)."""
    if not top or board.legal_moves.count() < 2:
        return None
    best = top[0]
    is_best = move.uci() == best.move
    before, after = win_pct(best.cp), win_pct(user.cp)
    if (is_best or before - after <= NEAR_BEST) and offered_material(board, move) >= BRILLIANT_MIN_OFFER:
        keeps_mate = bool(best.mate and best.mate > 0 and user.mate and user.mate > 0)
        if keeps_mate or (before <= BRILLIANT_MAX_BEFORE and after >= BRILLIANT_MIN_AFTER):
            return "brilliant"
    if (is_best and len(top) > 1 and not board.is_check() and not _recapture(board, move) and see(board, move) < 2
            and not _mates(board, move)):
        second = win_pct(top[1].cp)
        if before - second >= GREAT_GAP and second < GREAT_MAX_SECOND:
            return "great"
    return None


# ------------------------------------------------------------------ one move, with Stockfish
def _first(line: Line, top: list[Line]) -> list[Line]:
    return [line] + [l for l in top if l.move != line.move]


@dataclass
class Scored:
    top: list[Line]           # best lines from the position before the move
    user: Line                # the played move's line, from the same root
    reply: Line | None        # the opponent's best answer to it (rest of the user's line)
    verdict: str              # best | good | inaccuracy | mistake | blunder
    highlight: str | None     # brilliant | great | None
    cp_loss: int
    win_pct_loss: float

    @property
    def best(self) -> Line:
        return self.top[0]


def best_lines(engine: StockfishService, board: chess.Board, depth: int, multipv: int = 3) -> list[Line]:
    """Stockfish's best lines. MultiPV prunes harder at the root: at depth 12 Stockfish 17.1 misses
    a mate-in-2 queen sacrifice that a single-line search finds at depth 8. So a single line first
    (run after the MultiPV search, the hash it left misleads it too), then the MultiPV lines; the
    better first line wins."""
    one = engine.analyse(board, depth=depth) if multipv > 1 else []
    top = engine.analyse(board, depth=depth, multipv=multipv)
    if one and top and one[0].cp > top[0].cp:
        top = _first(one[0], top)
    return top


def line_of(engine: StockfishService, board: chess.Board, move: chess.Move, depth: int,
            top: list[Line]) -> tuple[list[Line], Line]:
    """The line of `move`, searched from the same root as `top` (its own MultiPV line when it is
    there). If it scores better than the best line, the player saw further than the search did and
    it becomes the best line. Returns (top, line)."""
    user = next((l for l in top if l.move == move.uci()), None)
    if user is None:
        own = engine.analyse(board, depth=depth, root_moves=[move])
        user = own[0] if own else None
        if user is not None and top and user.cp > top[0].cp:
            top = _first(user, top)
    if user is None:  # pragma: no cover - Stockfish always answers a searchmoves request
        after = board.copy()
        after.push(move)
        user = Line(move=move.uci(), san=board.san(move), cp=-engine.evaluate(after, depth), mate=None,
                    pv=[move.uci()], pv_san=[board.san(move)], depth=depth)
    return top, user


def score_move(engine: StockfishService, board: chess.Board, move: chess.Move, depth: int,
               multipv: int = 3) -> Scored:
    """Judge `move` in `board` (position before it, side to move = the mover)."""
    if move not in board.legal_moves:
        raise ValueError(f"lance ilegal nesta posição: {move.uci()}")
    top = best_lines(engine, board, depth, multipv)
    if not top:
        raise ValueError("a partida já terminou nesta posição")
    top, user = line_of(engine, board, move, depth, top)
    reply = None
    if len(user.pv) > 1:
        reply = Line(move=user.pv[1], san=user.pv_san[1], cp=-user.cp,
                     mate=-user.mate if user.mate is not None else None,
                     pv=user.pv[1:], pv_san=user.pv_san[1:], depth=user.depth)
    best = top[0]
    verdict = "best" if move.uci() == best.move else classify_move(best.cp, best.mate, user.cp, user.mate)
    return Scored(top=top, user=user, reply=reply, verdict=verdict, highlight=highlight(board, move, top, user),
                  cp_loss=max(0, best.cp - user.cp),
                  win_pct_loss=round(max(0.0, win_pct(best.cp) - win_pct(user.cp)), 2))


# ------------------------------------------------------------------ game accuracy (Lichess)
def move_accuracy(before: float, after: float) -> float:
    """Lichess per-move accuracy from the mover's win-% before and after (AccuracyPercent.scala)."""
    if after >= before:
        return 100.0
    raw = 103.1668100711649 * math.exp(-0.04354415386753951 * (before - after)) - 3.166924740191411
    return max(0.0, min(100.0, raw + 1))  # +1: Lichess' bonus for imperfect analysis


def game_accuracy(wins: list[float], user_moves: list[int]) -> float | None:
    """Lichess game accuracy: the mean of the volatility-weighted mean and the harmonic mean of the
    move accuracies. `wins` = the user's win-% in every position, from the start to the end; `user_moves` = indexes i of the user's moves (from wins[i] to wins[i+1])."""
    n = len(wins) - 1
    if n < 1:
        return None
    ws = min(max(2, min(8, n // 10)), len(wins))
    windows = [wins[:ws]] * max(0, ws - 2) + [wins[i:i + ws] for i in range(len(wins) - ws + 1)]
    weights = [max(0.5, min(12.0, pstdev(w))) for w in windows]
    pairs = [(move_accuracy(wins[i], wins[i + 1]), weights[i]) for i in user_moves if 0 <= i < n]
    if not pairs:
        return None
    weighted = sum(a * w for a, w in pairs) / sum(w for _, w in pairs)
    harmonic = len(pairs) / sum(1 / max(a, 1.0) for a, _ in pairs)
    return round((weighted + harmonic) / 2, 1)
