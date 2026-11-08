import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, CATEGORY_LABEL } from "../lib/api";

export default function Games() {
  const [games, setGames] = useState<any[]>([]);
  const [pgn, setPgn] = useState("");
  const [names, setNames] = useState(() => { try { return localStorage.getItem("chesslab.names") ?? ""; } catch { return ""; } });
  const [color, setColor] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState<any>(null);

  const load = () => api.get("/api/games").then(setGames).catch((e) => setMsg(e.message));
  useEffect(() => { load(); }, []);

  async function importGames(analyze: boolean) {
    setBusy(true); setMsg(analyze ? "Importing and analysing with Stockfish (can take a while per game)…" : "Importing…");
    try { localStorage.setItem("chesslab.names", names); } catch { /* ignore */ }
    try {
      const r = await api.post("/api/games/import", { pgn, analyze, user_color: color || undefined, player_names: names ? names.split(",").map((s) => s.trim()) : undefined });
      setMsg(`Imported ${r.imported}, duplicates ${r.duplicates}, unknown colour ${r.unknown_user_color}${r.errors.length ? `, errors: ${r.errors.join("; ")}` : ""}`);
      setPgn(""); load();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  }
  async function analyze(id: number, user_color?: string) {
    setBusy(true); setMsg("Analysing…");
    try { await api.post(`/api/games/${id}/analyze${user_color ? `?user_color=${user_color}` : ""}`); setMsg("Done"); load(); open(id); } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  }
  const open = (id: number) => api.get(`/api/games/${id}`).then(setDetail);
  async function onFile(f: File | undefined) { if (f) setPgn(await f.text()); }

  return (
    <div className="space-y-4">
      <h1>Games</h1>
      <div className="card space-y-2">
        <div className="muted text-sm">Your real games are the primary outcome measure. Paste or upload a PGN (e.g. exported from Chess.com → Archive → Download).</div>
        <div className="grid gap-2 sm:grid-cols-2">
          <input className="input" placeholder="Your usernames, comma separated" value={names} onChange={(e) => setNames(e.target.value)} />
          <select className="input" value={color} onChange={(e) => setColor(e.target.value)}><option value="">Detect my colour from names</option><option value="white">I played White</option><option value="black">I played Black</option></select>
        </div>
        <textarea className="input h-32 font-mono text-xs" placeholder="[Event ...]" value={pgn} onChange={(e) => setPgn(e.target.value)} />
        <div className="flex flex-wrap items-center gap-2">
          <input type="file" accept=".pgn,text/plain" className="text-sm" onChange={(e) => onFile(e.target.files?.[0])} />
          <button className="btn" disabled={busy || pgn.length < 10} onClick={() => importGames(false)}>Import</button>
          <button className="btn-primary" disabled={busy || pgn.length < 10} onClick={() => importGames(true)}>Import + analyse</button>
        </div>
        {msg && <div className="text-sm text-ink-300">{msg}</div>}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card overflow-x-auto">
          <table className="w-full text-sm"><thead className="text-left text-ink-400"><tr><th>Date</th><th>Game</th><th>Res</th><th>Acc</th><th>Blunders</th><th /></tr></thead><tbody>
            {games.length === 0 && <tr><td colSpan={6} className="muted py-2">No games imported.</td></tr>}
            {games.map((g) => (
              <tr key={g.id} className="border-t border-ink-700">
                <td className="py-1">{g.date ?? "?"}</td><td>{g.white} – {g.black}</td><td>{g.result}</td>
                <td className="tabular-nums">{g.metrics?.accuracy ?? "—"}</td><td>{g.metrics?.blunders ?? "—"}</td>
                <td className="text-right">{g.analyzed ? <button className="btn" onClick={() => open(g.id)}>View</button> : g.user_color ? <button className="btn" disabled={busy} onClick={() => analyze(g.id)}>Analyse</button> : (
                  <span className="flex justify-end gap-1"><button className="btn" onClick={() => analyze(g.id, "white")}>as W</button><button className="btn" onClick={() => analyze(g.id, "black")}>as B</button></span>)}</td>
              </tr>
            ))}
          </tbody></table>
        </div>
        {detail && (
          <div className="card space-y-2">
            <h2>{detail.white} – {detail.black} ({detail.result})</h2>
            <div className="grid grid-cols-3 gap-2 text-sm">
              <div><div className="label">Accuracy</div>{detail.metrics.accuracy}</div><div><div className="label">ACPL</div>{detail.metrics.acpl}</div><div><div className="label">Errors/100</div>{detail.metrics.errors_per_100}</div>
            </div>
            <ul className="space-y-1 text-sm">
              {detail.mistakes.map((m: any) => (
                <li key={m.ply} className="flex flex-wrap items-center gap-2 border-t border-ink-700 pt-1">
                  <span className={`chip ${m.severity === "blunder" ? "border-bad/60 text-bad" : m.severity === "mistake" ? "border-warn/60 text-warn" : ""}`}>{m.severity}</span>
                  <span className="font-mono">{Math.floor(m.ply / 2) + 1}{m.ply % 2 ? "…" : "."} {m.move}</span>
                  <span className="text-ink-400">best {m.best}</span>
                  <span className="text-xs">{CATEGORY_LABEL[m.category]}</span>
                  <Link className="ml-auto text-xs text-accent" to={`/analysis?fen=${encodeURIComponent(m.fen)}`}>analyse</Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
