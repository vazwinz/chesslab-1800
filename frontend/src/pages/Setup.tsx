import { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function Setup() {
  const [s, setS] = useState<any>(null);
  const [path, setPath] = useState("");
  const [limit, setLimit] = useState("");
  const [minR, setMinR] = useState("");
  const [maxR, setMaxR] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.get("/api/setup").then(setS).catch((e) => setErr(e.message));
  useEffect(() => {
    load();
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, []);

  async function start(download: boolean) {
    setErr(null);
    try {
      await api.post("/api/setup/import", {
        download, path: download ? undefined : path,
        limit: limit ? +limit : undefined, min_rating: minR ? +minR : undefined, max_rating: maxR ? +maxR : undefined,
      });
      load();
    } catch (e: any) { setErr(e.message); }
  }

  if (!s) return <div className="muted">Loading…</div>;
  const imp = s.import;
  const running = imp.status === "running";
  return (
    <div className="max-w-3xl space-y-4">
      <h1>Setup</h1>
      {err && <div className="card text-sm text-bad">{err}</div>}
      <div className="card space-y-1 text-sm">
        <div><span className="label mr-2">Engine</span>{s.engine.ok ? <span className="text-good">{s.engine.name}</span> : <span className="text-bad">{s.engine.error}</span>}</div>
        <div className="text-xs text-ink-400">{s.engine.path}</div>
        <div><span className="label mr-2">Puzzles</span>{s.puzzles.toLocaleString()}</div>
        <div><span className="label mr-2">Data</span><span className="font-mono text-xs">{s.data_dir}</span></div>
      </div>

      <div className="card space-y-3">
        <h2>Lichess puzzle database</h2>
        <div className="muted text-sm">
          Downloads the official dump from database.lichess.org (CC0, a few hundred MB) and imports it. The full import takes roughly 10–20 minutes; you can keep training with what is already imported. Re-running later updates existing puzzles.
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          <input className="input" placeholder="Limit (optional)" value={limit} onChange={(e) => setLimit(e.target.value)} />
          <input className="input" placeholder="Min rating" value={minR} onChange={(e) => setMinR(e.target.value)} />
          <input className="input" placeholder="Max rating" value={maxR} onChange={(e) => setMaxR(e.target.value)} />
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-primary" disabled={running} onClick={() => start(true)}>Download and import from Lichess</button>
        </div>
        <div className="flex gap-2">
          <input className="input font-mono text-xs" placeholder="…or path to a lichess_db_puzzle.csv.zst you already have" value={path} onChange={(e) => setPath(e.target.value)} />
          <button className="btn" disabled={running || !path} onClick={() => start(false)}>Import file</button>
        </div>
        {imp.status !== "idle" && (
          <div className="rounded border border-ink-700 bg-ink-850 p-3 text-sm">
            <div>Status: <b className={imp.status === "failed" ? "text-bad" : imp.status === "done" ? "text-good" : "text-warn"}>{imp.status}</b> {imp.phase && imp.phase !== imp.status ? `· ${imp.phase}` : ""}</div>
            {imp.phase === "download" && (
              <>
                <div className="mt-1 h-2 rounded bg-ink-700"><div className="h-2 rounded bg-accent" style={{ width: imp.total_bytes ? `${(100 * imp.downloaded) / imp.total_bytes}%` : "5%" }} /></div>
                <div className="mt-1 text-xs text-ink-400">{(imp.downloaded / 1e6).toFixed(0)} / {imp.total_bytes ? (imp.total_bytes / 1e6).toFixed(0) : "?"} MB · {imp.rate_mb_s} MB/s</div>
              </>
            )}
            {(imp.phase === "import" || imp.status === "done") && (
              <div className="mt-1 text-xs text-ink-300">read {imp.rows_read?.toLocaleString()} · inserted {imp.inserted?.toLocaleString()} · updated {imp.updated?.toLocaleString()} · invalid {imp.invalid?.toLocaleString()}{imp.rows_per_s ? ` · ${imp.rows_per_s.toLocaleString()} rows/s` : ""}{imp.seconds ? ` · ${imp.seconds}s` : ""}</div>
            )}
            {imp.error && <div className="mt-1 text-bad">{imp.error}</div>}
          </div>
        )}
      </div>
      <div className="muted text-xs">Puzzle data © lichess.org contributors, released under CC0. Engine: Stockfish (GPL-3.0).</div>
    </div>
  );
}
