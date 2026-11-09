import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

/** One step of today's routine (GET /api/routine/today). The app counts `done` by itself. */
export type RoutineStep = {
  id: number;
  key: "own_mistakes" | "loop" | "retention" | "endgame" | "openings" | "games";
  title: string;
  why: string;
  to: string;
  done: number;
  target: number;
  unit: string;
  minutes: number;
  completed: boolean;
};

export type RoutineDay = {
  day: string;
  light_day: boolean;
  light_day_advice: { light_day: boolean };
  steps: RoutineStep[];
  current: RoutineStep["key"] | null;
  finished: boolean;
  minutes_left: number;
  streak_days: number;
};

/** Today's routine, and a reload to call after something that may count for it. */
export function useRoutine() {
  const [routine, setRoutine] = useState<RoutineDay | null>(null);
  const reload = useCallback(() => api.get<RoutineDay>("/api/routine/today").then(setRoutine).catch(() => {}), []);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { routine, reload, setRoutine };
}

export const stepFor = (r: RoutineDay | null, key: string) => r?.steps.find((s) => s.key === key) ?? null;
export const nextStep = (r: RoutineDay | null) => r?.steps.find((s) => !s.completed) ?? null;
