import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type Exercise = {
  attempt_id: number;
  mode: string;
  kind: "puzzle" | "game_position";
  puzzle_id?: string;
  fen: string;
  initial_fen: string;
  opponent_move: string | null;
  opponent_san?: string;
  solver_color: "white" | "black";
  solution_len: number;
  rating?: number;
  concept?: string | null;
  time_limit_ms: number | null;
  min_think_ms: number | null;
  blind: boolean;
  candidates: boolean;
  retention_probe?: string | null;
  pressure_level?: number | null;
  loop_phase?: string;
  intervention?: { intervention: string; interleaved?: boolean };
  prompt?: string;
  complexity?: number;
};

export type Ribbon = "ok" | "bad" | "time";

type State = {
  session: { id: number; kind: string; theme?: string | null } | null;
  ex: Exercise | null;
  fen: string;
  lastMove: [string, string] | null;
  result: any;
  servedAt: number; // Date.now() when the solver could start thinking
  ribbon: Ribbon[];
  candsDone: boolean;
  set: (p: Partial<State>) => void;
  reset: () => void;
};

/** The training session lives outside the Train screen, so going to another screen (or opening
 *  the analysis) and coming back resumes exactly where you were. Kept for the app's lifetime. */
export const useTrain = create<State>()(
  persist(
    (set) => ({
      session: null, ex: null, fen: "", lastMove: null, result: null, servedAt: 0, ribbon: [], candsDone: false,
      set: (p) => set(p),
      reset: () => set({ session: null, ex: null, fen: "", lastMove: null, result: null, servedAt: 0, ribbon: [], candsDone: false }),
    }),
    { name: "aura.train", storage: createJSONStorage(() => sessionStorage), partialize: ({ set: _s, reset: _r, ...rest }) => rest },
  ),
);
