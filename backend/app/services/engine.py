"""Stockfish over UCI (via python-chess). Every evaluation shown in ChessLab comes from here;
nothing is simulated. If the engine is missing, calls raise EngineUnavailable."""
from __future__ import annotations

import atexit
import math
import threading
from dataclasses import dataclass

import chess
import chess.engine

from ..config import settings

MATE_CP = 10000


class EngineUnavailable(RuntimeError):
    pass


def win_pct(cp: int) -> float:
    """Lichess' centipawn → win-percentage model (side-to-move POV)."""
    cp = max(-1500, min(1500, cp))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def score_to_cp(score: chess.engine.PovScore, pov: chess.Color) -> int:
    return score.pov(pov).score(mate_score=MATE_CP)


def score_dict(score: chess.engine.PovScore, pov: chess.Color) -> dict:
    s = score.pov(pov)
    return {"cp": s.score(mate_score=MATE_CP), "mate": s.mate()}


@dataclass
class Line:
    move: str
    san: str
    cp: int
    mate: int | None
    pv: list[str]
    pv_san: list[str]
    depth: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class StockfishService:
    def __init__(self, path: str | None = None):
        self.path = path or settings.stockfish_path
        self._engine: chess.engine.SimpleEngine | None = None
        self._lock = threading.Lock()
        self.name: str | None = None

    # -- lifecycle -------------------------------------------------------
    def _ensure(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            try:
                eng = chess.engine.SimpleEngine.popen_uci(self.path, timeout=15)
            except Exception as exc:  # FileNotFoundError, PermissionError, EngineError...
                raise EngineUnavailable(
                    f"Could not start Stockfish at '{self.path}'. Set STOCKFISH_PATH. ({exc})"
                ) from exc
            opts = {}
            if "Threads" in eng.options:
                opts["Threads"] = settings.engine_threads
            if "Hash" in eng.options:
                opts["Hash"] = settings.engine_hash_mb
            if opts:
                eng.configure(opts)
            self.name = eng.id.get("name", "Stockfish")
            self._engine = eng
        return self._engine

    def close(self) -> None:
        with self._lock:
            if self._engine is not None:
                try:
                    self._engine.quit()
                except Exception:
                    pass
                self._engine = None

    def status(self) -> dict:
        try:
            with self._lock:
                self._ensure()
            return {"ok": True, "name": self.name, "path": self.path}
        except EngineUnavailable as exc:
            return {"ok": False, "error": str(exc), "path": self.path}

    # -- analysis --------------------------------------------------------
    def analyse(self, board: chess.Board, depth: int | None = None, movetime: float | None = None,
                multipv: int = 1) -> list[Line]:
        """Analyse a position. Scores are from the side-to-move's point of view."""
        if board.is_game_over():
            return []
        depth = min(depth or settings.engine_default_depth, settings.engine_max_depth)
        if movetime is not None:
            movetime = min(movetime, settings.engine_max_time)
            limit = chess.engine.Limit(time=movetime)
        else:
            limit = chess.engine.Limit(depth=depth, time=settings.engine_max_time * 3)
        multipv = max(1, min(multipv, 10, board.legal_moves.count()))
        with self._lock:
            eng = self._ensure()
            try:
                infos = eng.analyse(board, limit, multipv=multipv)
            except chess.engine.EngineTerminatedError as exc:
                self._engine = None
                raise EngineUnavailable(f"Stockfish terminated: {exc}") from exc
        if isinstance(infos, dict):
            infos = [infos]
        lines: list[Line] = []
        for info in infos:
            pv = info.get("pv") or []
            if not pv:
                continue
            sans, b = [], board.copy()
            for mv in pv:
                sans.append(b.san(mv))
                b.push(mv)
            sc = info["score"]
            lines.append(Line(move=pv[0].uci(), san=sans[0], cp=score_to_cp(sc, board.turn),
                              mate=sc.pov(board.turn).mate(), pv=[m.uci() for m in pv], pv_san=sans,
                              depth=int(info.get("depth", 0))))
        return lines

    def evaluate(self, board: chess.Board, depth: int | None = None) -> int:
        """Centipawns from side-to-move POV (terminal positions handled exactly)."""
        if board.is_checkmate():
            return -MATE_CP
        if board.is_game_over():
            return 0
        lines = self.analyse(board, depth=depth)
        return lines[0].cp if lines else 0

    def compare_move(self, board: chess.Board, move: chess.Move, depth: int | None = None) -> dict:
        """Compare the user's move with the engine's best move (mover's POV)."""
        best = self.analyse(board, depth=depth, multipv=3)
        if not best:
            raise ValueError("position is terminal")
        after = board.copy()
        after.push(move)
        user_cp = -self.evaluate(after, depth=depth)
        best_cp = best[0].cp
        loss = max(0, best_cp - user_cp)
        wl = max(0.0, win_pct(best_cp) - win_pct(user_cp))
        return {
            "best": best[0].as_dict(),
            "top": [l.as_dict() for l in best],
            "user_move": move.uci(),
            "user_san": board.san(move),
            "user_cp": user_cp,
            "best_cp": best_cp,
            "cp_loss": loss,
            "win_pct_loss": round(wl, 2),
            "verdict": classify_loss(wl),
            "is_best": move.uci() == best[0].move,
            "in_top": move.uci() in [l.move for l in best],
        }


def classify_loss(win_pct_loss: float) -> str:
    """Lichess-style thresholds on win-percentage loss."""
    if win_pct_loss >= 30:
        return "blunder"
    if win_pct_loss >= 20:
        return "mistake"
    if win_pct_loss >= 10:
        return "inaccuracy"
    return "good"


_service: StockfishService | None = None


def get_engine() -> StockfishService:
    global _service
    if _service is None:
        _service = StockfishService()
        atexit.register(_service.close)
    return _service
