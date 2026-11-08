"""Opening repertoire: lines from PGN/FEN, move drills, common-mistake review and the
typical middlegame structure each line leads to (plans are the user's own notes plus engine lines)."""
from __future__ import annotations

import io
from collections import Counter

import chess
import chess.pgn
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import OpeningDrill, Repertoire, RepertoireLine


def parse_line(pgn_or_moves: str, start_fen: str | None = None) -> tuple[str, list[str], list[str]]:
    """Accepts a PGN (headers optional, FEN header honoured) or a plain SAN/UCI move list."""
    text = pgn_or_moves.strip()
    board = chess.Board(start_fen) if start_fen else None
    if board is None:
        game = chess.pgn.read_game(io.StringIO(text))
        if game is not None and list(game.mainline_moves()) and not game.errors:
            b = game.board()
            fen0 = b.fen()
            ucis, sans = [], []
            for mv in game.mainline_moves():
                sans.append(b.san(mv))
                ucis.append(mv.uci())
                b.push(mv)
            return fen0, ucis, sans
        board = chess.Board()
    fen0 = board.fen()
    ucis, sans = [], []
    for tok in text.replace("\n", " ").split():
        if tok.endswith(".") or tok[0].isdigit() and "." in tok:
            tok = tok.split(".")[-1]
            if not tok:
                continue
        if tok in ("1-0", "0-1", "1/2-1/2", "*"):
            break
        try:
            mv = board.parse_san(tok)
        except ValueError:
            mv = chess.Move.from_uci(tok)
            if mv not in board.legal_moves:
                raise ValueError(f"illegal move {tok}")
        sans.append(board.san(mv))
        ucis.append(mv.uci())
        board.push(mv)
    if not ucis:
        raise ValueError("no moves found")
    return fen0, ucis, sans


def structure(fen: str) -> dict:
    """Pawn-structure facts of the position the line reaches (no engine involved)."""
    b = chess.Board(fen)
    out = {}
    for color, name in ((chess.WHITE, "white"), (chess.BLACK, "black")):
        files = [chess.square_file(s) for s in b.pieces(chess.PAWN, color)]
        c = Counter(files)
        isolated = [chess.FILE_NAMES[f] for f in c if (f - 1 not in c and f + 1 not in c)]
        doubled = [chess.FILE_NAMES[f] for f, n in c.items() if n > 1]
        opp = [chess.square_file(s) for s in b.pieces(chess.PAWN, not color)]
        passed = []
        for s in b.pieces(chess.PAWN, color):
            f, r = chess.square_file(s), chess.square_rank(s)
            blockers = [t for t in b.pieces(chess.PAWN, not color)
                        if abs(chess.square_file(t) - f) <= 1 and
                        (chess.square_rank(t) > r if color == chess.WHITE else chess.square_rank(t) < r)]
            if not blockers:
                passed.append(chess.square_name(s))
        out[name] = {"pawns": len(files), "isolated": isolated, "doubled": doubled, "passed": passed}
    open_files = [chess.FILE_NAMES[f] for f in range(8)
                  if not any(chess.square_file(s) == f for s in b.pieces(chess.PAWN, chess.WHITE) | b.pieces(chess.PAWN, chess.BLACK))]
    out["open_files"] = open_files
    return out


def drill_check(db: Session, line: RepertoireLine, ply: int, uci: str) -> dict:
    expected = line.moves_uci[ply] if ply < len(line.moves_uci) else None
    ok = expected is not None and uci == expected
    db.add(OpeningDrill(line_id=line.id, ply=ply, expected_uci=expected or "", played_uci=uci, correct=ok))
    db.commit()
    return {"correct": ok, "expected": expected, "expected_san": line.moves_san[ply] if expected else None}


def common_mistakes(db: Session, repertoire_id: int | None = None) -> list[dict]:
    q = select(OpeningDrill, RepertoireLine).join(RepertoireLine, RepertoireLine.id == OpeningDrill.line_id)
    if repertoire_id:
        q = q.where(RepertoireLine.repertoire_id == repertoire_id)
    stats: dict[tuple[int, int], dict] = {}
    for d, line in db.execute(q).all():
        k = (line.id, d.ply)
        s = stats.setdefault(k, {"line_id": line.id, "line": line.name, "ply": d.ply,
                                 "expected_san": line.moves_san[d.ply] if d.ply < len(line.moves_san) else None,
                                 "n": 0, "wrong": 0, "wrong_moves": Counter()})
        s["n"] += 1
        if not d.correct:
            s["wrong"] += 1
            s["wrong_moves"][d.played_uci] += 1
    out = [{**s, "wrong_moves": s["wrong_moves"].most_common(3)} for s in stats.values() if s["wrong"]]
    return sorted(out, key=lambda s: -s["wrong"] / s["n"])


def list_repertoires(db: Session) -> list[dict]:
    reps = db.execute(select(Repertoire).order_by(Repertoire.id)).scalars().all()
    out = []
    for r in reps:
        lines = db.execute(select(RepertoireLine).where(RepertoireLine.repertoire_id == r.id)).scalars().all()
        out.append({"id": r.id, "name": r.name, "color": r.color,
                    "lines": [{"id": l.id, "name": l.name, "start_fen": l.start_fen, "moves_uci": l.moves_uci,
                               "moves_san": l.moves_san, "plans": l.plans} for l in lines]})
    return out
