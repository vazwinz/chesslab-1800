"""ERROR DNA — rule-based classification of meaningful mistakes.

Status: EXPERIMENTAL. The categories are coaching heuristics computed from observable data
(Stockfish evaluations, board features, move timing). They describe *what kind of decision
went wrong*, not why it happened in the player's head; one mistake can fit several labels,
we keep the first that matches in a documented priority order and store every feature used,
so each label is auditable (see docs/COGNITIVE_ENGINE.md)."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Attempt, GameMistake, utcnow
from ..models import Game
from ..services.engine import StockfishService, threat_gain, win_pct

INFO = {
    "tactical_blindness": {
        "name": "Cegueira tática",
        "short": "havia uma tática forçada e ela não foi vista",
        "how": "No puzzle, o primeiro lance já foi errado. Na partida, o melhor lance era forçante (xeque, captura) "
               "e bem melhor que o segundo.",
        "tip": "Da próxima vez, se pergunte: quais são todos os xeques, capturas e ameaças, das duas cores?"},
    "calculation_error": {
        "name": "Erro de cálculo",
        "short": "a ideia começou certa, mas a sequência foi mal calculada",
        "how": "No puzzle, você acertou o começo e errou um lance depois, ou errou a linha no modo às cegas. Na "
               "partida, o seu lance era forçante e a refutação também.",
        "tip": "Da próxima vez, se pergunte: no fim da minha linha, qual é a melhor resposta do adversário?"},
    "missed_opponent_threat": {
        "name": "Ameaça ignorada",
        "short": "o adversário tinha uma ameaça e ela não foi respondida",
        "how": "Puzzle de defesa, ou a refutação do seu lance era justamente a ameaça que o adversário já tinha "
               "(o AURA testa isso deixando o adversário jogar duas vezes).",
        "tip": "Da próxima vez, se pergunte: o que o último lance do adversário ameaça?"},
    "impulsive_decision": {
        "name": "Decisão impulsiva",
        "short": "o lance saiu muito mais rápido do que a posição pedia",
        "how": "Você pensou bem menos do que o seu normal em puzzles parecidos (ou do que o relógio permitia, "
               "na partida) e havia mais de um lance legal.",
        "tip": "Da próxima vez, se pergunte: eu comparei pelo menos dois lances antes de jogar?"},
    "poor_candidate_selection": {
        "name": "Candidatos ruins",
        "short": "havia boas opções que não foram consideradas",
        "how": "No modo de candidatos, a solução não estava na sua lista. Na partida, os três melhores lances eram "
               "parecidos e você jogou fora deles.",
        "tip": "Da próxima vez, se pergunte: quais são os meus três candidatos antes de escolher?"},
    "positional_misunderstanding": {
        "name": "Erro posicional",
        "short": "erro de avaliação numa posição calma, sem tática",
        "how": "Nenhuma das regras acima bateu: foi um lance quieto que piorou a posição.",
        "tip": "Da próxima vez, se pergunte: qual é a minha pior peça e como ela melhora?"},
    "time_management_failure": {
        "name": "Problema de relógio",
        "short": "erro cometido com pouco tempo ou por estourar o tempo",
        "how": "O tempo acabou, ou o lance foi feito com o relógio abaixo de 10 s (ou 5% do tempo inicial).",
        "tip": "Da próxima vez, se pergunte: quanto tempo eu posso gastar neste lance?"},
    "endgame_technique_failure": {
        "name": "Técnica de final",
        "short": "erro numa posição de final simplificada",
        "how": "Pouco material sobrando (ou puzzle com tema de final) quando o erro aconteceu.",
        "tip": "Da próxima vez, se pergunte: o meu rei está ativo e para onde vão os peões?"},
}
CATEGORIES = {k: f"{v['name']} — {v['short']}" for k, v in INFO.items()}
PRIORITY = ["time_management_failure", "impulsive_decision", "missed_opponent_threat", "endgame_technique_failure",
            "calculation_error", "tactical_blindness", "poor_candidate_selection", "positional_misunderstanding"]
PIECE_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
THREAT_CP = 200          # opponent threat worth ≥ 2 pawns
TACTIC_GAP_CP = 150      # best move is clearly better than the 2nd best → a concrete tactic exists
MANY_GOOD_CP = 60        # top-3 moves within this margin → several good candidates existed
DEFENSIVE_THEMES = {"defensiveMove", "equality"}
ENDGAME_THEMES = {"endgame", "pawnEndgame", "rookEndgame", "queenEndgame", "bishopEndgame", "knightEndgame",
                  "queenRookEndgame"}


def is_forcing(board: chess.Board, move: chess.Move) -> bool:
    return board.is_capture(move) or board.gives_check(move) or move.promotion is not None


def phase_of(board: chess.Board) -> str:
    npm = sum(PIECE_VALUE[p.piece_type] for p in board.piece_map().values() if p.piece_type not in (chess.PAWN, chess.KING))
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    if npm <= 13 or (queens == 0 and npm <= 20):
        return "endgame"
    if board.fullmove_number <= 12 and npm >= 56:
        return "opening"
    return "middlegame"


@dataclass
class DecisionFeatures:
    """Everything the classifier looks at, stored with the label for auditability."""
    cp_loss: int | None = None
    best_cp: int | None = None
    user_cp: int | None = None
    win_pct_loss: float | None = None
    best_move: str | None = None
    best_forcing: bool | None = None
    tactic_gap_cp: int | None = None
    many_good_options: bool | None = None
    user_forcing: bool | None = None
    refutation: str | None = None
    refutation_forcing: bool | None = None
    threat_move: str | None = None
    threat_cp: int | None = None
    refutation_is_threat: bool | None = None
    phase: str | None = None
    think_s: float | None = None
    impulsive_threshold_s: float | None = None
    clock_s: float | None = None
    low_clock_threshold_s: float | None = None
    timed_out: bool = False
    fail_ply: int | None = None
    blind: bool = False
    candidates_missed_solution: bool | None = None
    themes: list[str] = field(default_factory=list)
    legal_moves: int | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None and v != []}


def engine_features(engine: StockfishService, board: chess.Board, move: chess.Move, depth: int) -> DecisionFeatures:
    """Stockfish-derived features of one decision (board = position before the user's move)."""
    f = DecisionFeatures(phase=phase_of(board), legal_moves=board.legal_moves.count(), user_forcing=is_forcing(board, move))
    top = engine.analyse(board, depth=depth, multipv=3)
    if not top:
        return f
    best = top[0]
    f.best_move = best.move
    f.best_forcing = is_forcing(board, chess.Move.from_uci(best.move))
    if len(top) > 1:
        f.tactic_gap_cp = best.cp - top[1].cp
        f.many_good_options = len(top) >= 3 and best.cp - top[2].cp <= MANY_GOOD_CP
    after = board.copy()
    after.push(move)
    if after.is_checkmate():
        user_cp = 10000
        reply_lines = []
    else:
        reply_lines = engine.analyse(after, depth=depth)
        user_cp = -(reply_lines[0].cp if reply_lines else 0)
    f.best_cp, f.user_cp = best.cp, user_cp
    f.cp_loss = max(0, best.cp - user_cp)
    f.win_pct_loss = round(max(0.0, win_pct(best.cp) - win_pct(user_cp)), 2)
    if reply_lines:
        f.refutation = reply_lines[0].move
        f.refutation_forcing = is_forcing(after, chess.Move.from_uci(f.refutation))
    # Null-move threat probe: what would the opponent do if it were their move now?
    if not board.is_check():
        null = board.copy(stack=False)
        null.push(chess.Move.null())
        null = chess.Board(null.fen())  # no null move in the history sent to the engine
        if null.is_valid() and not null.is_game_over():
            nl = engine.analyse(null, depth=max(8, depth - 4))
            if nl:
                f.threat_move = nl[0].move
                # how much better the opponent's position becomes if they could move again
                f.threat_cp = threat_gain(best.cp, best.mate, nl[0].cp, nl[0].mate)
                if f.refutation:
                    t, r = chess.Move.from_uci(f.threat_move), chess.Move.from_uci(f.refutation)
                    f.refutation_is_threat = (t == r) or (t.to_square == r.to_square)
    return f


def classify(f: DecisionFeatures, source: str) -> str:
    """Return the first category (in PRIORITY order) whose rule matches."""
    rules = {
        "time_management_failure": lambda: f.timed_out or (
            f.clock_s is not None and f.low_clock_threshold_s is not None and f.clock_s <= f.low_clock_threshold_s),
        "impulsive_decision": lambda: (f.think_s is not None and f.impulsive_threshold_s is not None
                                       and f.think_s < f.impulsive_threshold_s and (f.legal_moves or 2) > 1),
        "missed_opponent_threat": lambda: bool(DEFENSIVE_THEMES & set(f.themes)) or (
            (f.threat_cp or 0) >= THREAT_CP and bool(f.refutation_is_threat)),
        "endgame_technique_failure": lambda: f.phase == "endgame" or bool(ENDGAME_THEMES & set(f.themes)),
        "calculation_error": lambda: (f.fail_ply or 0) > 0 or (source == "puzzle" and f.blind) or (
            source == "game" and bool(f.user_forcing) and bool(f.refutation_forcing)),
        "tactical_blindness": lambda: source == "puzzle" and not f.candidates_missed_solution or (
            source == "game" and bool(f.best_forcing) and (f.tactic_gap_cp or 0) >= TACTIC_GAP_CP),
        "poor_candidate_selection": lambda: bool(f.candidates_missed_solution) or bool(f.many_good_options),
        "positional_misunderstanding": lambda: True,
    }
    for cat in PRIORITY:
        if rules[cat]():
            return cat
    return "positional_misunderstanding"


# --------------------------------------------------------------------- recurring patterns
def recurring_patterns(db: Session, days: int = 90, half_life_days: float = 21.0) -> dict:
    """Aggregate Error DNA over games and puzzles. Recency-weighted so old habits fade out.
    A pattern is 'recurring' when it appears ≥3 times in ≥2 different games/sessions."""
    since = utcnow() - timedelta(days=days)
    now = utcnow()

    def w(ts: datetime) -> float:
        return 0.5 ** (max(0.0, (now - ts).total_seconds() / 86400) / half_life_days)

    by_cat: dict[str, dict] = defaultdict(lambda: {"count": 0, "weight": 0.0, "games": 0, "puzzles": 0,
                                                   "contexts": set(), "themes": Counter(), "phases": Counter()})
    gm = db.execute(select(GameMistake).where(GameMistake.created_at >= since)).scalars().all()
    for m in gm:
        d = by_cat[m.category]
        d["count"] += 1
        d["games"] += 1
        d["weight"] += w(m.created_at)
        d["contexts"].add(f"g{m.game_id}")
        d["phases"][m.phase] += 1
    att = db.execute(select(Attempt).where(Attempt.served_at >= since, Attempt.error_category.is_not(None))).scalars().all()
    for a in att:
        d = by_cat[a.error_category]
        d["count"] += 1
        d["puzzles"] += 1
        d["weight"] += w(a.served_at)
        d["contexts"].add(f"s{a.session_id}")
        if a.concept:
            d["themes"][a.concept] += 1
    total_decisions = len(db.execute(select(Attempt.id).where(Attempt.served_at >= since,
                                                              Attempt.correct.is_not(None))).all())
    games = db.execute(select(Game).where(Game.analyzed.is_(True), Game.imported_at >= since)).scalars().all()
    game_moves = sum(int(g.metrics.get("user_moves", 0)) for g in games)
    total_weight = sum(d["weight"] for d in by_cat.values()) or 1.0
    out = []
    for cat, d in by_cat.items():
        out.append({
            "category": cat,
            "label": CATEGORIES.get(cat, cat),
            "count": d["count"],
            "from_games": d["games"],
            "from_puzzles": d["puzzles"],
            "distinct_contexts": len(d["contexts"]),
            "recent_weight": round(d["weight"], 2),
            "share": round(d["weight"] / total_weight, 3),
            "recurring": d["count"] >= 3 and len(d["contexts"]) >= 2,
            "top_themes": d["themes"].most_common(3),
            "phases": dict(d["phases"]),
        })
    out.sort(key=lambda x: -x["recent_weight"])
    return {"window_days": days, "puzzle_attempts": total_decisions, "game_moves_analyzed": game_moves,
            "patterns": out}
