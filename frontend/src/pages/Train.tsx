import { Chess } from "chess.js";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Board, { Hesitation } from "../components/Board";
import { api, CATEGORY_LABEL } from "../lib/api";

type Exercise = {
  attempt_id: number;
  mode: string;
  kind: "puzzle" | "game_position";
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

const KINDS: { kind: string; title: string; text: string }[] = [
  { kind: "loop", title: "Closed-loop training", text: "Measure → diagnose → intervene → practice → reassess → adapt. Recommended." },
  { kind: "mixed", title: "Mixed tactics", text: "Adaptive difficulty across all themes." },
  { kind: "theme", title: "Single theme", text: "Forks, pins, back rank, defence…" },
  { kind: "blind", title: "Blind calculation", text: "Write the whole line before touching a piece." },
  { kind: "candidates", title: "Candidate moves", text: "List up to 3 candidates first; scored vs Stockfish." },
  { kind: "retention", title: "Retention review", text: "Concepts due for spaced review, on new positions." },
  { kind: "pressure", title: "Pressure", text: "Shrinking clock, defensive and complex positions." },
  { kind: "endgame", title: "Endgame puzzles", text: "Endgame themes from the puzzle database." },
  { kind: "own_mistakes", title: "My game mistakes", text: "Positions where you went wrong in your games." },
];
const CATS = ["forks", "pins", "skewers", "discovered_attacks", "double_attacks", "deflection", "decoy", "removing_the_defender",
  "zwischenzug", "back_rank", "checkmate_patterns", "sacrifices", "defensive"];

export default function Train() {
  const [session, setSession] = useState<{ id: number; kind: string } | null>(null);
  const [theme, setTheme] = useState("forks");
  const [ex, setEx] = useState<Exercise | null>(null);
  const [fen, setFen] = useState<string>("");
  const [lastMove, setLastMove] = useState<[string, string] | null>(null);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(performance.now());
  const [line, setLine] = useState("");
  const [cands, setCands] = useState("");
  const [candsDone, setCandsDone] = useState(false);
  const [viewFen, setViewFen] = useState<string | null>(null);
  const servedAt = useRef(0);
  const hes = useRef<Hesitation>({ selection_changes: 0, cancelled_drags: 0, piece_selections: 0 });

  useEffect(() => {
    const t = setInterval(() => setNow(performance.now()), 200);
    return () => clearInterval(t);
  }, []);

  const elapsed = ex && !result ? Math.max(0, now - servedAt.current) : 0;
  const locked = !!ex?.min_think_ms && elapsed < (ex?.min_think_ms ?? 0) && !result;
  const remaining = ex?.time_limit_ms ? ex.time_limit_ms - elapsed : null;

  useEffect(() => {
    if (ex && remaining != null && remaining <= 0 && !result && !busy) giveUp(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remaining]);

  async function start(kind: string) {
    setError(null);
    const s = await api.post("/api/sessions", { kind, theme: kind === "theme" ? theme : undefined });
    setSession({ id: s.id, kind });
    await next(s.id);
  }

  async function next(sid = session?.id) {
    if (!sid) return;
    setBusy(true);
    setResult(null);
    setError(null);
    setLine("");
    setCands("");
    setCandsDone(false);
    setViewFen(null);
    try {
      const e: Exercise = await api.post(`/api/sessions/${sid}/next`);
      hes.current = { selection_changes: 0, cancelled_drags: 0, piece_selections: 0 };
      setEx(e);
      if (e.opponent_move) {
        setFen(e.initial_fen);
        setLastMove(null);
        setTimeout(() => {
          setFen(e.fen);
          setLastMove([e.opponent_move!.slice(0, 2), e.opponent_move!.slice(2, 4)]);
          servedAt.current = performance.now();
        }, 450);
      } else {
        setFen(e.fen);
        setLastMove(null);
      }
      servedAt.current = performance.now() + (e.opponent_move ? 450 : 0);
    } catch (err: any) {
      setEx(null);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function onMove(uci: string) {
    if (!ex || result || busy || locked) return false;
    if (ex.candidates && !candsDone) return false;
    const g = new Chess(fen);
    try {
      g.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
    } catch {
      return false;
    }
    setFen(g.fen());
    setLastMove([uci.slice(0, 2), uci.slice(2, 4)]);
    send(uci);
    return true;
  }

  async function send(uci: string) {
    if (!ex) return;
    setBusy(true);
    try {
      const r = await api.post(`/api/attempts/${ex.attempt_id}/move`, {
        uci, elapsed_ms: Math.round(performance.now() - servedAt.current), hesitation: hes.current,
      });
      if (r.locked) {
        setError(`Think first — board unlocks in ${(r.remaining_ms / 1000).toFixed(0)}s`);
        setFen(ex.fen);
        return;
      }
      if (r.legal === false) {
        setError("Illegal move");
        return;
      }
      if (!r.finished) {
        setTimeout(() => {
          setFen(r.fen);
          setLastMove([r.reply.slice(0, 2), r.reply.slice(2, 4)]);
        }, 300);
      } else setResult(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitLine() {
    if (!ex) return;
    setBusy(true);
    try {
      const moves = line.replace(/\d+\.(\.\.)?/g, " ").split(/[\s,]+/).filter(Boolean);
      const t = Math.round(performance.now() - servedAt.current);
      const r = await api.post(`/api/attempts/${ex.attempt_id}/line`, { moves, elapsed_ms: t, first_move_ms: t, hesitation: hes.current });
      setResult(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitCands() {
    if (!ex) return;
    try {
      await api.post(`/api/attempts/${ex.attempt_id}/candidates`, { moves: cands.split(/[\s,]+/).filter(Boolean) });
      setCandsDone(true);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function giveUp(timedOut = false) {
    if (!ex || result) return;
    setBusy(true);
    try {
      const r = await api.post(`/api/attempts/${ex.attempt_id}/give-up`, {
        timed_out: timedOut, elapsed_ms: Math.round(performance.now() - servedAt.current), hesitation: hes.current,
      });
      setResult(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function showLine(upto: number) {
    if (!result?.start_fen) return;
    const g = new Chess(result.start_fen);
    for (const m of result.solution_uci.slice(0, upto + 1)) g.move({ from: m.slice(0, 2), to: m.slice(2, 4), promotion: m[4] });
    setViewFen(g.fen());
  }

  if (!session) {
    return (
      <div className="space-y-4">
        <h1>Train</h1>
        {error && <div className="card border-bad/50 text-bad">{error}</div>}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {KINDS.map((k) => (
            <div key={k.kind} className={`card flex flex-col gap-2 ${k.kind === "loop" ? "border-accent/50" : ""}`}>
              <div className="font-medium">{k.title}</div>
              <div className="muted flex-1">{k.text}</div>
              {k.kind === "theme" && (
                <select className="input" value={theme} onChange={(e) => setTheme(e.target.value)}>
                  {CATS.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
                </select>
              )}
              <button className={k.kind === "loop" ? "btn-primary" : "btn"} onClick={() => start(k.kind).catch((e) => setError(e.message))}>
                Start
              </button>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const boardDisabled = !!result || busy || locked || (ex?.candidates && !candsDone) || !ex;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,640px)_1fr]">
      <div className="space-y-2">
        {ex && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="chip">{ex.mode}</span>
            {ex.loop_phase && <span className="chip border-accent/50 text-accent">loop: {ex.loop_phase}</span>}
            {ex.retention_probe && <span className="chip">retention: {ex.retention_probe}</span>}
            {ex.pressure_level && <span className="chip">pressure L{ex.pressure_level}</span>}
            {ex.concept && <span className="chip">{ex.concept}</span>}
            <span className="ml-auto text-ink-300">{ex.solver_color === "white" ? "White" : "Black"} to move</span>
          </div>
        )}
        {fen ? (
          <Board fen={viewFen ?? fen} orientation={ex?.solver_color ?? "white"} onMove={onMove} disabled={boardDisabled}
            lastMove={lastMove} onHesitation={(h) => (hes.current = h)} />
        ) : (
          <div className="card muted">{error ?? "Loading…"}</div>
        )}
        <div className="flex flex-wrap gap-2">
          {!result && ex && <button className="btn" onClick={() => giveUp(false)} disabled={busy}>Show solution</button>}
          {result && <button className="btn-primary" onClick={() => next()} disabled={busy}>Next exercise →</button>}
          {result && <Link className="btn" to={`/analysis?fen=${encodeURIComponent(result.start_fen ?? ex?.fen ?? "")}`}>Analyse position</Link>}
          <button className="btn ml-auto" onClick={() => { api.post(`/api/sessions/${session.id}/end`); setSession(null); setEx(null); setFen(""); setResult(null); }}>
            End session
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {error && <div className="card border-bad/50 text-sm text-bad">{error}</div>}
        {ex && !result && (
          <div className="card space-y-3">
            {ex.prompt && <div>{ex.prompt}</div>}
            {ex.opponent_san && <div className="muted">Opponent played <span className="font-mono text-ink-100">{ex.opponent_san}</span>. Find the best continuation ({ex.solution_len} move{ex.solution_len > 1 ? "s" : ""}).</div>}
            <div className="flex items-baseline gap-4">
              <div><div className="label">Time</div><div className="stat">{(elapsed / 1000).toFixed(0)}s</div></div>
              {remaining != null && <div><div className="label">Clock</div><div className={`stat ${remaining < 10000 ? "text-bad" : ""}`}>{Math.max(0, remaining / 1000).toFixed(0)}s</div></div>}
              {ex.rating && ex.mode !== "assessment" && <div><div className="label">Puzzle</div><div className="stat text-ink-300">{ex.rating}</div></div>}
            </div>
            {locked && <div className="rounded border border-warn/40 bg-warn/10 p-2 text-sm text-warn">Board locked — scan checks, captures and threats. {(((ex.min_think_ms ?? 0) - elapsed) / 1000).toFixed(0)}s</div>}
            {ex.candidates && !candsDone && (
              <div className="space-y-2">
                <div className="label">Your candidate moves (SAN, up to 3)</div>
                <input className="input font-mono" placeholder="e.g. Nxf7 Qh5 Rd1" value={cands} onChange={(e) => setCands(e.target.value)} />
                <button className="btn-primary" onClick={submitCands}>Lock candidates</button>
              </div>
            )}
            {ex.blind && (
              <div className="space-y-2">
                <div className="label">Blind calculation — write your moves (SAN), opponent replies are automatic</div>
                <textarea className="input h-20 font-mono" placeholder="e.g. Qxh7+ Kxh7 Rh3+ … (only your moves are required)" value={line} onChange={(e) => setLine(e.target.value)} />
                <button className="btn-primary" onClick={submitLine} disabled={!line.trim() || busy}>Submit line</button>
              </div>
            )}
          </div>
        )}
        {result && <Feedback r={result} onStep={showLine} />}
      </div>
    </div>
  );
}

function Feedback({ r, onStep }: { r: any; onStep: (i: number) => void }) {
  return (
    <div className="space-y-3">
      <div className={`card ${r.correct ? "border-good/50" : "border-bad/50"}`}>
        <div className={`text-lg font-semibold ${r.correct ? "text-good" : "text-bad"}`}>
          {r.correct ? "Correct" : r.timed_out ? "Time ran out" : "Not the best move"}
        </div>
        {r.rating && <div className="muted">Puzzle rating {r.rating.before} → <span className={r.rating.after >= r.rating.before ? "text-good" : "text-bad"}>{r.rating.after}</span></div>}
        {r.solution_san && (
          <div className="mt-2">
            <div className="label mb-1">Solution (click to view)</div>
            <div className="flex flex-wrap gap-1 font-mono text-sm">
              {r.solution_san.map((m: string, i: number) => (
                <button key={i} className={`chip hover:border-accent ${i % 2 ? "opacity-70" : "text-ink-100"}`} onClick={() => onStep(i)}>{m}</button>
              ))}
            </div>
          </div>
        )}
        {r.best_san && <div className="mt-2 text-sm">Better: <span className="font-mono">{r.best_san}</span> (you played {r.your_game_move} in the game)</div>}
        {r.comparison && <div className="muted mt-1">Stockfish: your move {r.comparison.user_san} {(r.comparison.user_cp / 100).toFixed(2)} vs best {r.comparison.best.san} {(r.comparison.best_cp / 100).toFixed(2)}</div>}
        {r.explanation?.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-300">{r.explanation.map((e: string) => <li key={e}>{e}</li>)}</ul>}
      </div>
      {r.error_dna && (
        <div className="card">
          <div className="label">Error DNA</div>
          <div className="font-medium text-bad">{CATEGORY_LABEL[r.error_dna.category]}</div>
          <div className="muted">{r.error_dna.label}</div>
          <details className="mt-2 text-xs text-ink-400">
            <summary className="cursor-pointer">Evidence used</summary>
            <pre className="mt-1 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(r.error_dna.evidence, null, 1)}</pre>
          </details>
        </div>
      )}
      {r.break && (
        <div className="card border-warn/50">
          <div className="font-medium text-warn">Break suggested</div>
          <div className="text-sm">{r.break.recommendation}</div>
          <div className="muted mt-1 text-xs">{r.break.reasons.join("; ")}. {r.break.disclaimer}</div>
        </div>
      )}
      <div className="card grid grid-cols-2 gap-2 text-sm">
        {r.retention && <div><div className="label">Next review</div>{r.retention.concept}: {r.retention.next_review_in_days} d</div>}
        {r.intervention && <div><div className="label">Intervention</div>{r.intervention.done}/{r.intervention.target}</div>}
        {r.loop_phase && <div><div className="label">Loop phase</div>{r.loop_phase}</div>}
        {r.band_change && <div><div className="label">Difficulty</div>band {r.band_change.from} → {r.band_change.to}</div>}
        {r.candidates && <div><div className="label">Candidates</div>score {r.candidates.score}</div>}
      </div>
    </div>
  );
}
