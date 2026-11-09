import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { configureSound } from "./sound";

export type Prefs = {
  theme: "system" | "light" | "dark";
  board_theme: "torneio" | "grafite" | "madeira" | "oceano";
  show_coordinates: boolean;
  show_legal_moves: boolean;
  animation_ms: number;
  sound: boolean;
  volume: number;
  auto_next: boolean;
  notation: "figurine" | "letters";
  tour_done: boolean;
  player_names: string;
  update_check: boolean;
  dismissed_version: string | null;
  goal_rating: number;
  goal_time_class: "auto" | "bullet" | "blitz" | "rapid" | "daily";
  chesscom_username: string;
};

export const DEFAULT_PREFS: Prefs = {
  theme: "system", board_theme: "grafite", show_coordinates: true, show_legal_moves: true, animation_ms: 180,
  sound: true, volume: 0.7, auto_next: false, notation: "figurine", tour_done: true, player_names: "",
  update_check: true, dismissed_version: null, goal_rating: 1800, goal_time_class: "auto", chesscom_username: "",
};

type Ctx = { prefs: Prefs; ready: boolean; set: (p: Partial<Prefs>) => Promise<void>; dark: boolean };
const PrefsCtx = createContext<Ctx>({ prefs: DEFAULT_PREFS, ready: false, set: async () => {}, dark: false });

function applyTheme(theme: Prefs["theme"]) {
  const el = document.documentElement;
  if (theme === "system") delete el.dataset.theme;
  else el.dataset.theme = theme;
  try {
    localStorage.setItem("aura.theme", theme);
  } catch {
    /* storage unavailable: the server-side preference still applies on the next start */
  }
}

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT_PREFS);
  const [ready, setReady] = useState(false);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false);

  useEffect(() => {
    api.get<Prefs>("/api/prefs").then((p) => {
      setPrefs({ ...DEFAULT_PREFS, ...p });
      applyTheme(p.theme);
    }).catch(() => {}).finally(() => setReady(true));
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const on = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq?.addEventListener?.("change", on);
    return () => mq?.removeEventListener?.("change", on);
  }, []);

  useEffect(() => configureSound(prefs.sound, prefs.volume), [prefs.sound, prefs.volume]);

  const set = useCallback(async (p: Partial<Prefs>) => {
    setPrefs((cur) => ({ ...cur, ...p }));
    if (p.theme) applyTheme(p.theme);
    const saved = await api.put<Prefs>("/api/prefs", p);
    setPrefs({ ...DEFAULT_PREFS, ...saved });
  }, []);

  const dark = prefs.theme === "dark" || (prefs.theme === "system" && systemDark);
  const value = useMemo(() => ({ prefs, ready, set, dark }), [prefs, ready, set, dark]);
  return <PrefsCtx.Provider value={value}>{children}</PrefsCtx.Provider>;
}

export const usePrefs = () => useContext(PrefsCtx);
