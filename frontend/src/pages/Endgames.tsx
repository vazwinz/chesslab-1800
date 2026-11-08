import { Chess } from "chess.js";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Board from "../components/Board";
import { api } from "../lib/api";

export default function Endgames() {
  const [positions, setPositions] = useState<any[]>([]);
  const [cur, setCur] = useState<any>(null);
  const [fen, setFen] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [last, setLast] = useState<[string, string] | null>(null);

  useEffect(() => { api.get("/api/endgames").then(setPositions); }, []);

  function pick(p: any) { setCur(p); setFen(p.fen); setMsg(null); setDone(false); setLast(null); }

  function onMove(uci: string) {
    if (!cur || busy || done) return false;
    const g = new Chess(fen);
    try { g.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] }); } catch { return false; }
    setFen(g.fen());
    setBusy(true);
    api.post("/api/endgames/move", { position_id: cur.id, fen, uci }).then((r) => {
      if (r.move) { setFen(r.fen); setLast([r.move.slice(0, 2), r.move.slice(2, 4)]); }
      if (r.finished) { setDone(true); setMsg(r.success ? `Success (${r.result})` : `Failed (${r.result}) — try again`); }
    }).catch((e) => setMsg(e.message)).finally(() => setBusy(false));
    return true;
  }

  const modules = [...new Set(positions.map((p) => p.module))];
  const orient = cur ? (new Chess(cur.fen).turn() === "w" ? "white" : "black") : "white";
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,640px)]">
      <div className="space-y-3">
        <h1>Endgames</h1>
        <div className="muted text-sm">Play textbook positions against Stockfish until the goal is reached. For more, train <Link className="text-accent" to="/train">endgame puzzles</Link> from the Lichess database.</div>
        {modules.map((m) => (
          <div key={m} className="card">
            <div className="label mb-1">{m}</div>
            <div className="flex flex-wrap gap-2">{positions.filter((p) => p.module === m).map((p) => (
              <button key={p.id} className={`btn ${cur?.id === p.id ? "border-accent text-accent" : ""}`} onClick={() => pick(p)}>{p.title} <span className="text-xs text-ink-400">({p.goal})</span></button>
            ))}</div>
          </div>
        ))}
      </div>
      <div className="space-y-2">
        {cur ? (<>
          <Board fen={fen} orientation={orient} onMove={onMove} disabled={busy || done} lastMove={last} />
          <div className="card text-sm"><b>{cur.title}</b> — goal: {cur.goal} as {orient}. <span className="text-ink-400">{cur.hint}</span>
            {msg && <div className={`mt-1 ${msg.startsWith("Success") ? "text-good" : "text-bad"}`}>{msg}</div>}
            <div className="mt-2 flex gap-2"><button className="btn" onClick={() => pick(cur)}>Restart</button></div></div>
        </>) : <div className="card muted">Choose a position.</div>}
      </div>
    </div>
  );
}
