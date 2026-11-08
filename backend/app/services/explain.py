"""Human-language descriptions of Lichess puzzle themes (used after each attempt to explain
the tactical idea). Evaluations are never invented here: numbers come only from Stockfish."""

THEME_TEXT = {
    "fork": "Fork: one piece attacks two or more targets at once, so the opponent cannot save both.",
    "pin": "Pin: a piece cannot move (or should not) because a more valuable piece stands behind it.",
    "skewer": "Skewer: a valuable piece is attacked and must move, exposing a piece behind it.",
    "discoveredAttack": "Discovered attack: moving one piece unmasks an attack by another.",
    "doubleCheck": "Double check: two pieces give check at once — only a king move can answer it.",
    "deflection": "Deflection: lure a defender away from the square or piece it must guard.",
    "attraction": "Attraction (decoy): force a piece, often the king, onto a square where it can be hit.",
    "capturingDefender": "Removing the defender: capture the piece that protects the real target.",
    "intermezzo": "Zwischenzug: an in-between move (often a check or threat) before the expected recapture.",
    "backRankMate": "Back-rank mate: the king is trapped behind its own pawns on the first/last rank.",
    "mateIn1": "Mate in 1.", "mateIn2": "Mate in 2: a forcing sequence that ends in checkmate.",
    "mateIn3": "Mate in 3: a longer forcing mating line — calculate every check.",
    "mate": "Checkmate pattern.", "smotheredMate": "Smothered mate: a knight mates a king surrounded by its own pieces.",
    "sacrifice": "Sacrifice: give up material for a bigger gain (mate, material or a decisive attack).",
    "defensiveMove": "Defensive move: the only move that parries the opponent's threat.",
    "equality": "Save the position: find the move that keeps the balance from a worse position.",
    "hangingPiece": "Hanging piece: an undefended piece can simply be taken.",
    "trappedPiece": "Trapped piece: a piece with no safe squares can be won.",
    "xRayAttack": "X-ray: a piece attacks or defends through another piece.",
    "quietMove": "Quiet move: a non-checking, non-capturing move that sets up an unstoppable threat.",
    "clearance": "Clearance: vacate a square or line so another piece can use it.",
    "interference": "Interference: block the line between a defender and what it defends.",
    "kingsideAttack": "Kingside attack.", "exposedKing": "Exposed king: weak king cover allows a decisive attack.",
    "promotion": "Promotion: a pawn becomes a queen (or another piece).",
    "underPromotion": "Underpromotion: promoting to a knight, rook or bishop is stronger here.",
    "advancedPawn": "Advanced pawn: a far-advanced pawn creates decisive threats.",
    "pawnEndgame": "Pawn endgame: king activity, opposition and pawn races decide.",
    "rookEndgame": "Rook endgame: activity, checks from behind and cutting the king matter most.",
    "queenEndgame": "Queen endgame.", "bishopEndgame": "Bishop endgame.", "knightEndgame": "Knight endgame.",
    "endgame": "Endgame technique.", "zugzwang": "Zugzwang: any move worsens the opponent's position.",
    "crushing": "The solution wins decisively.", "advantage": "The solution gives a clear advantage.",
}


def explain(themes: str) -> list[str]:
    return [THEME_TEXT[t] for t in themes.split() if t in THEME_TEXT]
