import { useEffect, useRef, useState } from "react";
import { api } from "./api";

export type EngineLine = { move: string; san: string; cp: number; mate: number | null; pv: string[]; pv_san: string[]; depth: number };
export type EngineResult = { fen: string; engine: string; lines: EngineLine[]; terminal: boolean; result: string | null };

/** Live Stockfish analysis of `fen` while `enabled`: debounced, at most one request in flight and
 *  always for the latest position (fast navigation never queues a pile of old analyses). */
export function useEngine(fen: string | null, enabled: boolean, depth = 18, multipv = 3) {
  const [res, setRes] = useState<EngineResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const want = useRef<string | null>(null);
  const inflight = useRef(false);
  const opts = useRef({ enabled, depth, multipv });
  opts.current = { enabled, depth, multipv };

  async function run() {
    if (inflight.current || !opts.current.enabled) return;
    const target = want.current;
    if (!target) return;
    inflight.current = true;
    setBusy(true);
    try {
      const r = await api.post<EngineResult>("/api/engine/analyse", { fen: target, depth: opts.current.depth,
        multipv: opts.current.multipv });
      setRes(r);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      inflight.current = false;
      setBusy(false);
      if (opts.current.enabled && want.current && want.current !== target) void run();
    }
  }

  useEffect(() => {
    want.current = enabled ? fen : null;
    if (!enabled || !fen) return;
    const t = setTimeout(run, 160);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fen, enabled, depth, multipv]);

  const current = res && fen && res.fen.split(" ").slice(0, 4).join(" ") === fen.split(" ").slice(0, 4).join(" ") ? res : null;
  return { result: current, busy, error };
}
