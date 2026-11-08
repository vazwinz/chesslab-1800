import { Chess } from "chess.js";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Board from "../components/Board";
import { api } from "../lib/api";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export default function Analysis() {
  const [params] = useSearchParams();
  const [startFen, setStartFen] = useState(params.get("fen") || START);
  const [moves, setMoves] = useState<string[]>([]); // uci
  const [cursor, setCursor] = useState(0);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [fenInput, setFenInput] = useState("");
  const [pgnInput, setPgnInput] = useState("");
  const [engine, setEngine] = useState<any>(null);
  const [coach, setCoach] = useState<any>(null);
  const [depth, setDepth] = useState(18);
  const [multipv, setMultipv] = useState(3);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const { fen, sans, status, pgn } = useMemo(() => {
    const g = new Chess(startFen);
    const sans: string[] = [];
    let fen = g.fen();
    moves.forEach((u, i) => {
      const m = g.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u[4] });
      sans.push(m.san);
      if (i < cursor) fen = g.fen();
    });
    if (cursor === 0) fen = startFen;
    const at = new Chess(fen);
    const status = at.isCheckmate() ? "Checkmate" : at.isStalemate() ? "Stalemate" : at.isDraw() ? "Draw" : at.inCheck() ? "Check" : "";
    const full = new Chess(startFen);
    if (startFen !== START) { full.header("SetUp", "1", "FEN", startFen); }
    moves.forEach((u) => full.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u[4] }));
    return { fen, sans, status, pgn: full.pgn() };
  }, [startFen, moves, cursor]);

  useEffect(() => { setEngine(null); setCoach(null); }, [fen]);

  function onMove(uci: string) {
    const g = new Chess(fen);
    try { g.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] }); } catch { return false; }
    const next = [...moves.slice(0, cursor), uci];
    setMoves(next);
    setCursor(next.length);
    return true;
  }

  function loadFen() {
    try { new Chess(fenInput.trim()); setStartFen(fenInput.trim()); setMoves([]); setCursor(0); setErr(null); } catch (e: any) { setErr(`Invalid FEN: ${e.message}`); }
  }
  async function loadPgn() {
    try {
      const r = await api.post("/api/board/pgn", { pgn: pgnInput });
      setStartFen(r.start_fen); setMoves(r.moves_uci); setCursor(r.moves_uci.length); setErr(null);
    } catch (e: any) { setErr(e.message); }
  }
  async function analyse() {
    setBusy(true); setErr(null);
    try { setEngine(await api.post("/api/engine/analyse", { fen, depth, multipv })); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  async function explain() {
    setBusy(true); setErr(null);
    try {
      const last = cursor > 0 ? moves[cursor - 1] : undefined;
      if (last) {
        const g = new Chess(startFen);
        moves.slice(0, cursor - 1).forEach((u) => g.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u[4] }));
        setCoach(await api.post("/api/coach/explain", { fen: g.fen(), move: last }));
      } else setCoach(await api.post("/api/coach/explain", { fen }));
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  const lm = cursor > 0 ? ([moves[cursor - 1].slice(0, 2), moves[cursor - 1].slice(2, 4)] as [string, string]) : null;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,640px)_1fr]">
      <div className="space-y-2">
        <Board fen={fen} orientation={orientation} onMove={onMove} lastMove={lm} />
        <div className="flex flex-wrap gap-2">
          <button className="btn" onClick={() => setCursor(0)}>⏮</button>
          <button className="btn" onClick={() => setCursor(Math.max(0, cursor - 1))}>◀</button>
          <button className="btn" onClick={() => setCursor(Math.min(moves.length, cursor + 1))}>▶</button>
          <button className="btn" onClick={() => setCursor(moves.length)}>⏭</button>
          <button className="btn" onClick={() => { const n = moves.slice(0, Math.max(0, cursor - 1)); setMoves(n); setCursor(n.length); }}>Undo</button>
          <button className="btn" onClick={() => { setMoves([]); setCursor(0); }}>Restart</button>
          <button className="btn" onClick={() => setOrientation(orientation === "white" ? "black" : "white")}>Flip</button>
          {status && <span className="chip self-center border-warn/50 text-warn">{status}</span>}
        </div>
      </div>
      <div className="space-y-3">
        {err && <div className="card text-sm text-bad">{err}</div>}
        <div className="card space-y-2">
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-sm">Depth <input className="input w-16" type="number" min={1} max={40} value={depth} onChange={(e) => setDepth(+e.target.value)} /></label>
            <label className="text-sm">Lines <input className="input w-14" type="number" min={1} max={5} value={multipv} onChange={(e) => setMultipv(+e.target.value)} /></label>
            <button className="btn-primary" onClick={analyse} disabled={busy}>Stockfish</button>
            <button className="btn" onClick={explain} disabled={busy}>Explain {cursor > 0 ? "last move" : "position"}</button>
          </div>
          {engine && (
            <div className="space-y-1 font-mono text-sm">
              <div className="text-xs text-ink-400">{engine.engine} · depth {engine.lines[0]?.depth}{engine.cached ? " · cached" : ""}</div>
              {engine.lines.map((l: any, i: number) => (
                <div key={i} className="flex gap-2"><span className="w-16 shrink-0 tabular-nums text-accent">{l.mate != null ? `#${l.mate}` : (l.cp / 100).toFixed(2)}</span><span className="truncate text-ink-300">{l.pv_san.slice(0, 10).join(" ")}</span></div>
              ))}
              <div className="text-xs text-ink-400">Scores from the side to move's point of view.</div>
            </div>
          )}
          {coach && <div className="rounded border border-ink-700 bg-ink-850 p-2 text-sm">{coach.text}<div className="mt-1 text-xs text-ink-400">Source: {coach.provider === "none" ? "rule-based from Stockfish output" : coach.provider}</div></div>}
        </div>
        <div className="card">
          <div className="label mb-1">Moves</div>
          <div className="flex flex-wrap gap-1 font-mono text-sm">
            {sans.map((s, i) => (
              <button key={i} onClick={() => setCursor(i + 1)} className={`rounded px-1 ${i + 1 === cursor ? "bg-accent/20 text-accent" : "hover:bg-ink-700"}`}>
                {i % 2 === 0 ? `${Math.floor(i / 2) + 1}. ` : ""}{s}
              </button>
            ))}
            {sans.length === 0 && <span className="muted">Play a move on the board.</span>}
          </div>
        </div>
        <div className="card space-y-2">
          <div className="label">FEN</div>
          <div className="flex gap-2"><input className="input font-mono text-xs" readOnly value={fen} /><button className="btn" onClick={() => navigator.clipboard?.writeText(fen)}>Copy</button></div>
          <div className="flex gap-2"><input className="input font-mono text-xs" placeholder="Paste FEN" value={fenInput} onChange={(e) => setFenInput(e.target.value)} /><button className="btn" onClick={loadFen}>Load</button></div>
          <div className="label pt-2">PGN</div>
          <textarea className="input h-20 font-mono text-xs" readOnly value={pgn} />
          <textarea className="input h-20 font-mono text-xs" placeholder="Paste PGN" value={pgnInput} onChange={(e) => setPgnInput(e.target.value)} />
          <button className="btn" onClick={loadPgn}>Load PGN</button>
        </div>
      </div>
    </div>
  );
}
