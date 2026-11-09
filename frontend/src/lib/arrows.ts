import { Chess } from "chess.js";
import type { Arrow } from "react-chessboard/dist/chessboard/types";
import type { Prefs } from "./prefs";

/** The kinds of arrows the analysis and review boards draw; each one can be switched off
 *  under the board (the choice is saved in the preferences). Arrows you draw yourself with the
 *  right mouse button are separate (orange) and always available. */
export type ArrowKind = "best" | "played" | "opponent" | "others";

export const ARROW_KINDS: Record<ArrowKind, { label: string; pref: keyof Prefs; color: string; hint: string }> = {
  best: { label: "Melhor lance", pref: "arrows_best", color: "rgba(29, 138, 78, 0.85)",
    hint: "O lance que o Stockfish prefere." },
  played: { label: "Seu lance", pref: "arrows_played", color: "rgba(206, 44, 44, 0.8)",
    hint: "O lance que você jogou, em cada erro seu." },
  opponent: { label: "Ideia do adversário", pref: "arrows_opponent", color: "rgba(140, 72, 200, 0.85)",
    hint: "A ameaça do adversário antes do seu lance e, depois de um erro, a resposta dele que pune o lance." },
  others: { label: "Outras opções", pref: "arrows_others", color: "rgba(41, 98, 214, 0.5)",
    hint: "O 2º e o 3º lances do Stockfish." },
};

/** An arrow for a UCI move (e2e4, e7e8q), or null when there is no move. */
export function moveArrow(uci: string | null | undefined, kind: ArrowKind): Arrow | null {
  if (!uci || uci.length < 4) return null;
  return [uci.slice(0, 2), uci.slice(2, 4), ARROW_KINDS[kind].color] as Arrow;
}

/** The arrows that are switched on, in drawing order (later ones are drawn on top). */
export function pickArrows(prefs: Prefs, items: [ArrowKind, string | null | undefined][]): Arrow[] {
  const out: Arrow[] = [];
  for (const [kind, uci] of items) {
    if (!prefs[ARROW_KINDS[kind].pref]) continue;
    const a = moveArrow(uci, kind);
    if (a && !out.some((b) => b[0] === a[0] && b[1] === a[1])) out.push(a);
  }
  return out;
}

/** The same position with the other side to move: what the opponent would play "if it were their
 *  turn" is their threat. Null when the side to move is in check or the game is over (no threat
 *  question to ask there). */
export function nullMoveFen(fen: string): string | null {
  try {
    const g = new Chess(fen);
    if (g.inCheck() || g.isGameOver()) return null;
    const parts = fen.split(" ");
    parts[1] = parts[1] === "w" ? "b" : "w";
    parts[3] = "-"; // no en passant after a pass
    return parts.join(" ");
  } catch {
    return null;
  }
}

/** A threat worth showing: the opponent, moving twice, gains at least `minCp` (or mates).
 *  `bestCp`/`bestMate` are Stockfish's score of the real position (side to move), `threat` its
 *  best line in the null-move position (opponent to move). */
export function isRealThreat(bestCp: number | null, bestMate: number | null,
  threat: { cp: number | null; mate: number | null } | null | undefined, minCp = 100): boolean {
  if (!threat) return false;
  if (threat.mate != null) return threat.mate > 0;
  if (threat.cp == null) return false;
  if (bestMate != null) return bestMate < 0; // already lost: everything is a threat, show it
  return threat.cp + (bestCp ?? 0) >= minCp;
}
