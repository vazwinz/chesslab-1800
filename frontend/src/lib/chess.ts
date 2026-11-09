import { Chess, Move } from "chess.js";

export const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const FIG: Record<string, string> = { K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘" };

/** SAN with figurines (♘f3) or letters (Nf3). Promotions too (e8=♕). */
export function san(s: string, notation: "figurine" | "letters" = "figurine") {
  if (notation === "letters") return s;
  return s.replace(/^([KQRBN])/, (m) => FIG[m]).replace(/=([QRBN])/, (_, p) => `=${FIG[p]}`);
}

export function tryMove(fen: string, uci: string): { move: Move; fen: string } | null {
  try {
    const g = new Chess(fen);
    const move = g.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] || undefined });
    return { move, fen: g.fen() };
  } catch {
    return null;
  }
}

/** Positions after each move of a UCI line: [{fen, san, uci, lastMove}] */
export function walk(startFen: string, ucis: string[]) {
  const g = new Chess(startFen);
  const out: { fen: string; san: string; uci: string; flags: string; lastMove: [string, string] }[] = [];
  for (const u of ucis) {
    try {
      const m = g.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u[4] || undefined });
      out.push({ fen: g.fen(), san: m.san, uci: u, flags: m.flags, lastMove: [m.from, m.to] });
    } catch {
      break;
    }
  }
  return out;
}

export function sanToUci(fen: string, s: string): string | null {
  try {
    const g = new Chess(fen);
    const m = g.move(s);
    return m.from + m.to + (m.promotion ?? "");
  } catch {
    return null;
  }
}

export const turnOf = (fen: string) => (fen.split(" ")[1] === "b" ? "black" : "white");

/** Stockfish score (side-to-move POV) → White's POV. */
export function whiteScore(cp: number | null, mate: number | null, fen: string) {
  const w = turnOf(fen) === "white" ? 1 : -1;
  return { cp: cp == null ? null : cp * w, mate: mate == null ? null : mate * w };
}

export function evalLabel(cp: number | null, mate: number | null) {
  if (mate != null) return mate > 0 ? `#${mate}` : `#-${Math.abs(mate)}`;
  if (cp == null) return "";
  return `${cp > 0 ? "+" : ""}${(cp / 100).toFixed(2)}`;
}

/** White's winning chances 0..1 (the Lichess model), used to fill the evaluation bar. */
export function whiteShare(cp: number | null, mate: number | null) {
  if (mate != null) return mate > 0 ? 1 : 0;
  if (cp == null) return 0.5;
  const c = Math.max(-1500, Math.min(1500, cp));
  return 1 / (1 + Math.exp(-0.00368208 * c));
}
