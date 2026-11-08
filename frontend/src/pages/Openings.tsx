import { Chess } from "chess.js";
import { useEffect, useState } from "react";
import Board from "../components/Board";
import { api } from "../lib/api";

export default function Openings() {
  const [reps, setReps] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [color, setColor] = useState("white");
  const [lineForm, setLineForm] = useState<{ rid: number; name: string; moves: string; fen: string } | null>(null);
  const [drill, setDrill] = useState<{ line: any; color: string; ply: number; fen: string; feedback?: string } | null>(null);
  const [study, setStudy] = useState<any>(null);
  const [mistakes, setMistakes] = useState<any[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const load = () => { api.get("/api/openings").then(setReps); api.get("/api/openings/mistakes").then(setMistakes); };
  useEffect(load, []);

  async function create() { if (!name) return; await api.post("/api/openings", { name, color }); setName(""); load(); }
  async function addLine() {
    if (!lineForm) return;
    try { await api.post(`/api/openings/${lineForm.rid}/lines`, { name: lineForm.name || "Line", moves: lineForm.moves, start_fen: lineForm.fen || undefined }); setLineForm(null); setErr(null); load(); } catch (e: any) { setErr(e.message); }
  }

  function fenAt(line: any, ply: number) {
    const g = new Chess(line.start_fen);
    line.moves_uci.slice(0, ply).forEach((u: string) => g.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u[4] }));
    return g.fen();
  }
  function startDrill(line: any, repColor: string) {
    const startTurn = new Chess(line.start_fen).turn() === "w" ? "white" : "black";
    const ply = startTurn === repColor ? 0 : 1; // let the opponent's first move play itself
    setDrill({ line, color: repColor, ply, fen: fenAt(line, ply) });
    setStudy(null);
  }
  function onDrillMove(uci: string) {
    if (!drill) return false;
    const { line, ply } = drill;
    api.post(`/api/openings/lines/${line.id}/drill`, { ply, uci }).then((r) => {
      if (r.correct) {
        const nextPly = Math.min(line.moves_uci.length, ply + 2);
        const done = ply + 1 >= line.moves_uci.length;
        setDrill({ ...drill, ply: nextPly, fen: fenAt(line, done ? line.moves_uci.length : nextPly), feedback: done ? "Line complete ✓" : "✓" });
      } else {
        setDrill({ ...drill, fen: fenAt(line, ply), feedback: `Repertoire move: ${r.expected_san}` });
        load();
      }
    });
    return true;
  }

  return (
    <div className="space-y-4">
      <h1>Openings</h1>
      <div className="muted text-sm">Build a repertoire, drill it, and study the middlegame structure each line leads to. Write your own plans — understanding beats memorisation.</div>
      {err && <div className="card text-sm text-bad">{err}</div>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <div className="card flex flex-wrap gap-2">
            <input className="input flex-1" placeholder="New repertoire name" value={name} onChange={(e) => setName(e.target.value)} />
            <select className="input w-28" value={color} onChange={(e) => setColor(e.target.value)}><option value="white">White</option><option value="black">Black</option></select>
            <button className="btn-primary" onClick={create}>Create</button>
          </div>
          {reps.map((r) => (
            <div key={r.id} className="card space-y-2">
              <div className="flex items-center justify-between"><div className="font-medium">{r.name} <span className="chip">{r.color}</span></div>
                <div className="flex gap-1"><button className="btn" onClick={() => setLineForm({ rid: r.id, name: "", moves: "", fen: "" })}>+ line</button><button className="btn" onClick={() => api.del(`/api/openings/${r.id}`).then(load)}>Delete</button></div></div>
              {lineForm?.rid === r.id && (
                <div className="space-y-2 rounded border border-ink-700 p-2">
                  <input className="input" placeholder="Line name" value={lineForm!.name} onChange={(e) => setLineForm({ ...lineForm!, name: e.target.value })} />
                  <textarea className="input h-16 font-mono text-xs" placeholder="PGN or moves: 1. e4 e5 2. Nf3 Nc6 3. Bc4" value={lineForm!.moves} onChange={(e) => setLineForm({ ...lineForm!, moves: e.target.value })} />
                  <input className="input font-mono text-xs" placeholder="Optional start FEN" value={lineForm!.fen} onChange={(e) => setLineForm({ ...lineForm!, fen: e.target.value })} />
                  <button className="btn-primary" onClick={addLine}>Save line</button>
                </div>
              )}
              {r.lines.map((l: any) => (
                <div key={l.id} className="flex flex-wrap items-center gap-2 border-t border-ink-700 pt-2 text-sm">
                  <span className="font-medium">{l.name}</span>
                  <span className="truncate font-mono text-xs text-ink-400">{l.moves_san.join(" ")}</span>
                  <span className="ml-auto flex gap-1"><button className="btn" onClick={() => startDrill(l, r.color)}>Drill</button>
                    <button className="btn" onClick={() => { setDrill(null); api.get(`/api/openings/lines/${l.id}/study`).then((s) => setStudy({ ...s, line: l })); }}>Study</button></span>
                </div>
              ))}
            </div>
          ))}
          <div className="card"><h2>Common mistakes</h2>
            {mistakes.length === 0 ? <div className="muted">None recorded.</div> : <ul className="mt-1 text-sm">{mistakes.map((m) => <li key={`${m.line_id}-${m.ply}`}>{m.line}, move {Math.floor(m.ply / 2) + 1}: expected <span className="font-mono">{m.expected_san}</span> — wrong {m.wrong}/{m.n}</li>)}</ul>}
          </div>
        </div>
        <div className="space-y-2">
          {drill && (<>
            <Board fen={drill.fen} orientation={drill.color as any} onMove={onDrillMove} disabled={drill.ply >= drill.line.moves_uci.length} />
            <div className="text-sm">{drill.feedback ?? "Play your repertoire move."}</div>
          </>)}
          {study && (
            <div className="space-y-2">
              <Board fen={study.final_fen} disabled />
              <div className="card space-y-2 text-sm">
                <div className="label">Structure</div>
                <div>Open files: {study.structure.open_files.join(", ") || "none"}</div>
                {["white", "black"].map((c) => <div key={c}>{c}: isolated {study.structure[c].isolated.join(",") || "–"} · doubled {study.structure[c].doubled.join(",") || "–"} · passed {study.structure[c].passed.join(",") || "–"}</div>)}
                <div className="label pt-1">Stockfish plans from here</div>
                {study.engine_plans.map((p: any, i: number) => <div key={i} className="font-mono text-xs">{(p.cp / 100).toFixed(2)} {p.pv_san.slice(0, 8).join(" ")}</div>)}
                {study.engine_error && <div className="text-bad">{study.engine_error}</div>}
                <div className="label pt-1">Your notes on plans</div>
                <textarea className="input h-24" defaultValue={study.plans_notes} onBlur={(e) => api.put(`/api/openings/lines/${study.line.id}/plans`, { plans: e.target.value })} placeholder="Typical plans, pawn breaks, piece placement…" />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
