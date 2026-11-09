"""Board facts for the coach, computed only with python-chess (no engine, no guessing):
what a move captures, checks, forks, pins, skewers, discovers, leaves hanging, threatens to
mate... Every phrase the coach writes about a move comes from one of these facts."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import chess

from ..i18n import PIECE, material_words, piece_name

VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
DIRS = {
    chess.ROOK: [(1, 0), (-1, 0), (0, 1), (0, -1)],
    chess.BISHOP: [(1, 1), (1, -1), (-1, 1), (-1, -1)],
}
DIRS[chess.QUEEN] = DIRS[chess.ROOK] + DIRS[chess.BISHOP]


def sq(s: int) -> str:
    return chess.square_name(s)


def pc_at(board: chess.Board, s: int) -> str:
    p = board.piece_at(s)
    return f"{piece_name(p.piece_type)} em {sq(s)}" if p else sq(s)


def defended(board: chess.Board, s: int, color: chess.Color) -> bool:
    """Is the piece of `color` on `s` protected by another piece of its own colour?"""
    return board.is_attacked_by(color, s)


def lowest_attacker(board: chess.Board, s: int, by: chess.Color) -> int | None:
    vals = [VALUE[board.piece_type_at(a)] for a in board.attackers(by, s)]
    return min(vals) if vals else None


def en_prise(board: chess.Board, s: int) -> bool:
    """The piece on s can be won: attacked and undefended, or attacked by a cheaper piece."""
    p = board.piece_at(s)
    if p is None or p.piece_type == chess.KING:
        return False
    low = lowest_attacker(board, s, not p.color)
    if low is None:
        return False
    return (not defended(board, s, p.color)) or low < VALUE[p.piece_type]


def _ray(board: chess.Board, start: int, df: int, dr: int) -> list[int]:
    """Occupied squares along a direction, nearest first (at most two)."""
    out = []
    f, r = chess.square_file(start) + df, chess.square_rank(start) + dr
    while 0 <= f < 8 and 0 <= r < 8:
        s = chess.square(f, r)
        if board.piece_at(s):
            out.append(s)
            if len(out) == 2:
                break
        f, r = f + df, r + dr
    return out


def mate_in_one(board: chess.Board) -> chess.Move | None:
    for m in board.legal_moves:
        board.push(m)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            return m
    return None


def material(board: chess.Board) -> dict[chess.Color, dict[int, int]]:
    return {c: {pt: len(board.pieces(pt, c)) for pt in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)}
            for c in (chess.WHITE, chess.BLACK)}


def material_value(m: dict[int, int]) -> int:
    return sum(VALUE[pt] * n for pt, n in m.items())


@dataclass
class MoveFacts:
    san: str
    uci: str
    color: str
    piece: str
    from_sq: str
    to_sq: str
    capture: str | None = None
    capture_type: int | None = None
    check: bool = False
    mate: bool = False
    double_check: bool = False
    discovered_check: bool = False
    promotion: str | None = None
    castle: str | None = None
    en_passant: bool = False
    escapes_check: bool = False
    only_move: bool = False
    recapture: bool = False
    fork: list[str] = field(default_factory=list)
    pins: list[str] = field(default_factory=list)
    skewers: list[str] = field(default_factory=list)
    discovered: list[str] = field(default_factory=list)
    attacks_unprotected: list[str] = field(default_factory=list)
    hangs: bool = False
    threatens_mate: str | None = None
    tags: list[str] = field(default_factory=list)
    motifs: list[str] = field(default_factory=list)  # Lichess theme keys this move shows

    def as_dict(self) -> dict:
        return asdict(self)


def move_facts(board: chess.Board, move: chess.Move, prev_move: chess.Move | None = None) -> MoveFacts:
    """Facts about `move` played in `board` (board is not modified)."""
    piece = board.piece_at(move.from_square)
    me, them = piece.color, not piece.color
    captured_sq = move.to_square
    if board.is_en_passant(move):
        captured_sq = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
    captured = board.piece_at(captured_sq)
    after = board.copy()
    after.push(move)
    f = MoveFacts(san=board.san(move), uci=move.uci(), color="Brancas" if me else "Pretas",
                  piece=PIECE[piece.piece_type], from_sq=sq(move.from_square), to_sq=sq(move.to_square))
    f.escapes_check = board.is_check()
    f.only_move = board.legal_moves.count() == 1
    f.en_passant = board.is_en_passant(move)
    if captured:
        f.capture, f.capture_type = PIECE[captured.piece_type], captured.piece_type
        f.recapture = bool(prev_move and prev_move.to_square == move.to_square and board.is_capture(move))
    if board.is_castling(move):
        f.castle = "pequeno" if chess.square_file(move.to_square) > chess.square_file(move.from_square) else "grande"
    if move.promotion:
        f.promotion = PIECE[move.promotion]
    f.check, f.mate = after.is_check(), after.is_checkmate()
    checkers = after.checkers()
    f.double_check = len(checkers) >= 2
    f.discovered_check = f.check and not (checkers & chess.BB_SQUARES[move.to_square])
    moved_type = move.promotion or piece.piece_type

    # what the moved piece attacks now
    targets = []
    for s in after.attacks(move.to_square):
        p = after.piece_at(s)
        if p and p.color == them:
            targets.append((s, p.piece_type, defended(after, s, them)))
    valuable = [(s, t) for s, t, d in targets
                if t == chess.KING or VALUE[t] > VALUE[moved_type] or (not d and t != chess.PAWN)]
    moved_safe = not en_prise(after, move.to_square)  # a forking piece that can simply be taken is no fork
    if len(valuable) >= 2 and moved_safe:
        f.fork = [f"{piece_name(t)} em {sq(s)}" for s, t in valuable]
        f.motifs.append("fork")
    f.attacks_unprotected = [f"{piece_name(t)} em {sq(s)}" for s, t, d in targets
                             if not d and t not in (chess.KING, chess.PAWN)]

    # pins and skewers created by the moved slider
    if moved_type in DIRS:
        for df, dr in DIRS[moved_type]:
            hit = _ray(after, move.to_square, df, dr)
            if len(hit) < 2:
                continue
            a, b = (after.piece_at(x) for x in hit)
            if a.color != them or b.color != them:
                continue
            if b.piece_type == chess.KING or VALUE[b.piece_type] > VALUE[a.piece_type]:
                kind = "no rei" if b.piece_type == chess.KING else f"contra {piece_name(b.piece_type)} em {sq(hit[1])}"
                f.pins.append(f"{piece_name(a.piece_type)} em {sq(hit[0])} {kind}")
                if "pin" not in f.motifs:
                    f.motifs.append("pin")
            elif a.piece_type in (chess.KING, chess.QUEEN, chess.ROOK) and VALUE[a.piece_type] > VALUE[b.piece_type] \
                    and b.piece_type != chess.PAWN:
                f.skewers.append(f"{piece_name(a.piece_type)} em {sq(hit[0])}, com "
                                 f"{piece_name(b.piece_type)} em {sq(hit[1])} logo atrás")
                if "skewer" not in f.motifs:
                    f.motifs.append("skewer")

    # discovered attacks: own sliders whose line opened through the from-square
    for s in after.pieces(chess.BISHOP, me) | after.pieces(chess.ROOK, me) | after.pieces(chess.QUEEN, me):
        if s == move.to_square:
            continue
        new = after.attacks(s) & ~board.attacks(s)
        for t in chess.SquareSet(new):
            p = after.piece_at(t)
            if p and p.color == them and p.piece_type != chess.PAWN and \
                    chess.BB_SQUARES[move.from_square] & chess.between(s, t):
                f.discovered.append(f"{piece_name(after.piece_type_at(s))} em {sq(s)} passa a atacar "
                                    f"{piece_name(p.piece_type)} em {sq(t)}")
    if f.discovered or f.discovered_check:
        f.motifs.append("discoveredAttack")
    if f.double_check:
        f.motifs.append("doubleCheck")

    # is the moved piece left en prise? (in the engine's own line this is a sacrifice)
    f.hangs = en_prise(after, move.to_square) and not f.mate
    # mate threat: if it were our move again, could we mate at once?
    if not after.is_check() and not after.is_game_over():
        null = after.copy()
        null.push(chess.Move.null())
        if null.is_valid():
            m = mate_in_one(null)
            if m is not None:
                f.threatens_mate = null.san(m)
    if f.mate:
        f.motifs.append("mate")
        if _back_rank_mate(after):
            f.motifs.append("backRankMate")
        if _smothered(after, move):
            f.motifs.append("smotheredMate")
    if f.promotion:
        f.motifs.append("underPromotion" if move.promotion != chess.QUEEN else "promotion")
    f.tags = tags_for(f)
    return f


def _back_rank_mate(after: chess.Board) -> bool:
    k = after.king(after.turn)
    if k is None:
        return False
    rank = chess.square_rank(k)
    if rank not in (0, 7):
        return False
    checker = next(iter(after.checkers()), None)
    if checker is None or after.piece_type_at(checker) not in (chess.ROOK, chess.QUEEN):
        return False
    return chess.square_rank(checker) == rank


def _smothered(after: chess.Board, move: chess.Move) -> bool:
    k = after.king(after.turn)
    if k is None or after.piece_type_at(move.to_square) != chess.KNIGHT:
        return False
    own = [s for s in chess.SquareSet(chess.BB_KING_ATTACKS[k]) if after.color_at(s) == after.turn]
    return len(own) == len(chess.SquareSet(chess.BB_KING_ATTACKS[k]))


def tags_for(f: MoveFacts) -> list[str]:
    """Short Portuguese phrases, one per fact, in a sensible reading order."""
    t: list[str] = []
    if f.mate:
        t.append("xeque-mate")
    if f.castle:
        t.append(f"roque {f.castle}")
    if f.escapes_check and not f.mate:
        t.append("sai do xeque")
    if f.capture:
        art = "a" if f.capture in ("torre", "dama") else "o"
        what = f"recaptura {art} {f.capture}" if f.recapture else f"captura {art} {f.capture}"
        t.append(f"{what} em {f.to_sq}" + (" (en passant)" if f.en_passant else ""))
    if f.promotion:
        t.append(f"promove a {f.promotion}" if f.promotion != "dama" else "promove a dama")
    if f.double_check:
        t.append("xeque duplo")
    elif f.discovered_check:
        t.append("xeque descoberto")
    elif f.check and not f.mate:
        t.append("dá xeque")
    if f.fork:
        t.append("garfo: ataca " + " e ".join(f.fork) + " ao mesmo tempo")
    for p in f.pins:
        t.append(f"crava {p}")
    for s in f.skewers:
        t.append(f"espeto: ataca {s}")
    for d in f.discovered:
        t.append(f"ataque descoberto: {d}")
    if f.threatens_mate and not f.mate:
        t.append(f"ameaça mate com {f.threatens_mate}")
    if f.attacks_unprotected and not f.fork:
        t.append("ataca " + " e ".join(f.attacks_unprotected[:2]) + ", sem defesa")
    if f.only_move:
        t.append("único lance legal")
    return t


def material_change(start: chess.Board, end: chess.Board, pov: chess.Color) -> dict:
    """What each side lost between two positions (promotions included), from `pov`'s side."""
    a, b = material(start), material(end)
    mine_lost = {pt: max(0, a[pov][pt] - b[pov][pt]) for pt in a[pov]}
    theirs_lost = {pt: max(0, a[not pov][pt] - b[not pov][pt]) for pt in a[not pov]}
    balance = (material_value(b[pov]) - material_value(b[not pov])) - (material_value(a[pov]) - material_value(a[not pov]))
    return {"won": material_words(theirs_lost), "lost": material_words(mine_lost), "balance": balance}


def describe_material(ch: dict, who: str) -> str:
    """'você ganha um cavalo' / 'as Brancas ganham uma torre e perdem um bispo' / ''."""
    if ch["balance"] == 0 and not ch["won"] and not ch["lost"]:
        return ""
    plural = who != "você"
    if ch["won"] and ch["lost"]:
        text = f"{who} {'ganham' if plural else 'ganha'} {ch['won']} e {'perdem' if plural else 'perde'} {ch['lost']}"
    elif ch["won"]:
        text = f"{who} {'ganham' if plural else 'ganha'} {ch['won']}"
    elif ch["lost"]:
        text = f"{who} {'perdem' if plural else 'perde'} {ch['lost']}"
    else:
        text = ""
    if ch["balance"]:
        sign = "+" if ch["balance"] > 0 else ""
        text += f" (saldo de material {sign}{ch['balance']})" if text else f"saldo de material {sign}{ch['balance']}"
    return text
