import { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function Plan() {
  const [p, setP] = useState<any>(null);
  const [cons, setCons] = useState<any>(null);
  const [cfg, setCfg] = useState<any[] | null>(null);
  const load = () => { api.get("/api/plan/today").then(setP); api.get("/api/plan/consistency").then(setCons); };
  useEffect(load, []);
  if (!p) return <div className="muted">Loading…</div>;
  const total = p.blocks.reduce((s: number, b: any) => s + b.minutes, 0);
  const done = p.blocks.filter((b: any) => b.completed).reduce((s: number, b: any) => s + b.minutes, 0);
  return (
    <div className="space-y-4">
      <h1>Daily plan · {p.day}</h1>
      {p.light_day_advice.light_day && !p.light_day && (
        <div className="card border-warn/50 text-sm">Your recent sessions show repeated performance drops. A lighter day is recommended.
          <button className="btn ml-2" onClick={() => api.post("/api/plan/today/regenerate", { light: true }).then(setP)}>Switch to light day</button></div>
      )}
      <div className="card space-y-2">
        <div className="flex justify-between text-sm"><span>{p.light_day ? "Light day" : "Full day"}</span><span className="tabular-nums">{done}/{total} min</span></div>
        <div className="h-2 rounded bg-ink-700"><div className="h-2 rounded bg-good" style={{ width: `${total ? (100 * done) / total : 0}%` }} /></div>
        {p.blocks.map((b: any) => (
          <label key={b.id} className="flex items-center gap-3 border-t border-ink-700 py-2">
            <input type="checkbox" className="h-4 w-4 accent-[#8fbf6a]" checked={b.completed} onChange={(e) => api.post(`/api/plan/blocks/${b.id}`, { completed: e.target.checked }).then((x) => { setP(x); api.get("/api/plan/consistency").then(setCons); })} />
            <span className={`flex-1 ${b.completed ? "text-ink-400 line-through" : ""}`}>{b.title}</span><span className="text-ink-400">{b.minutes} min</span>
          </label>
        ))}
        <div className="flex gap-2 pt-1"><button className="btn" onClick={() => api.post("/api/plan/today/regenerate", { light: !p.light_day }).then(setP)}>{p.light_day ? "Use full day" : "Use light day"}</button>
          <button className="btn" onClick={() => api.get("/api/plan/config").then(setCfg)}>Configure</button></div>
      </div>
      {cfg && (
        <div className="card space-y-2">
          {cfg.map((b, i) => (
            <div key={b.key} className="flex items-center gap-2"><span className="flex-1 text-sm">{b.title}</span>
              <input className="input w-20" type="number" min={0} value={b.minutes} onChange={(e) => setCfg(cfg.map((x, j) => (j === i ? { ...x, minutes: +e.target.value } : x)))} /><span className="text-xs text-ink-400">min</span></div>
          ))}
          <button className="btn-primary" onClick={() => api.put("/api/plan/config", cfg).then(() => setCfg(null))}>Save (applies from the next new day)</button>
        </div>
      )}
      {cons && (
        <div className="card">
          <h2>Consistency (28 days)</h2>
          <div className="mt-2 grid grid-cols-7 gap-1">
            {cons.series.map((s: any) => (
              <div key={s.day} title={`${s.day}: ${s.completed_min}/${s.planned_min} min`} className="aspect-square rounded" style={{ background: s.completion == null ? "#202328" : `rgba(95,179,107,${0.15 + 0.85 * s.completion})` }} />
            ))}
          </div>
          <div className="muted mt-2 text-sm">Streak {cons.streak_days} d · trained {cons.days_trained_last_7}/7 days this week · completion {cons.completion_last_7 == null ? "—" : `${Math.round(cons.completion_last_7 * 100)}%`}</div>
        </div>
      )}
    </div>
  );
}
