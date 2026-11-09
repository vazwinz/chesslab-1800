import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

/** How the computer judged one of your moves (from /api/play/judge). */
export type Judgment = {
  ply: number;
  fen_before: string;
  verdict: "best" | "good" | "inaccuracy" | "mistake" | "blunder";
  win_pct_loss: number;
  cp_loss: number;
  user_uci: string;
  user_san: string;
  best_uci: string;
  best_san: string;
  reply_uci: string | null;
  reply_san: string | null;
  eval_after_cp: number; // your point of view, after your move
};

export type PlayResult = { result: "1-0" | "0-1" | "1/2-1/2"; reason: string };

export type PlayGame = {
  id: number;             // tells a new game from the previous one while requests are in flight
  startFen: string;
  startLabel: string;     // "Posição inicial", "Siciliana", "Antes do seu erro de 12/10"...
  opening: string | null;
  practice: boolean;      // from an endgame, one of your mistakes or a FEN: does not move your level
  moves: string[];        // UCI, from startFen
  userColor: "white" | "black";
  level: number;
  levelName: string;
  clock: { base: number; inc: number } | null; // seconds; only your clock runs
  timeLeftMs: number | null;
  turnStartedAt: number;  // Date.now() when your turn started
  hintsLeft: number;
  helped: boolean;        // used a hint: the game does not move your level
  judgments: Judgment[];
  streak: number;         // your moves in a row without a mistake or blunder
  bestStreak: number;
  engineEval: number | null; // the computer's view of the position after its last move (centipawns)
  over: (PlayResult & { summary?: any }) | null;
};

/** The "Jogar" screen starting a game from this position (the review and the analysis board link here). */
export const playFromHref = (fen: string, color: "white" | "black", label: string) =>
  `/jogar?${new URLSearchParams({ fen, cor: color, rotulo: label, auto: "1" })}`;

type State = {
  game: PlayGame | null;
  setGame: (g: PlayGame | null) => void;
  patch: (p: Partial<PlayGame>) => void;
};

/** The game in progress lives outside the Jogar screen, so going to another screen and coming
 *  back resumes it (kept for the session, like the training session). */
export const usePlay = create<State>()(
  persist(
    (set) => ({
      game: null,
      setGame: (game) => set({ game }),
      patch: (p) => set((s) => ({ game: s.game ? { ...s.game, ...p } : s.game })),
    }),
    { name: "aura.play", version: 1, storage: createJSONStorage(() => sessionStorage), partialize: ({ game }) => ({ game }) },
  ),
);
