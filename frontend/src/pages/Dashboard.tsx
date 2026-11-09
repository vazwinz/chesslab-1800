import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, fmtMs, pct } from "../lib/api";

const axis = { stroke: "#8a919c", fontSize: 11 };
const tip = { contentStyle: { background: "#16181b", border: "1px solid #3a3f47", fontSize: 12 } };

export default function Dashboard() {
  const [d, setD] = useState<any>(null);
  const [plan, setPlan] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.get("/api/dashboard").then(setD).catch((e) => setErr(e.message));
    api.get("/api/plan/today").then(setPlan).catch(() => {});
  }, []);
  if (err) return <div className="card text-bad">Backend not reachable: {err}</div>;
  if (!d) return <div className="muted">Loading…</div>;
  const today = d.daily_minutes[d.daily_minutes.length - 1]?.minutes ?? 0;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h1>Dashboard</h1>
        <div className="muted">All numbers come from your stored attempts and games.</div>
      </div>
      {!d.has_data && (
        <div className="card border-accent/40">
          No training data yet. <Link className="text-accent underline" to="/train">Start a session</Link> (first import puzzles in <Link className="text-accent underline" to="/setup">Setup</Link>).
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Puzzle rating" value={d.totals.attempts ? `${d.rating.current}${d.rating.provisional ? "?" : ""}` : "—"} sub={d.totals.attempts ? `±${d.rating.rd} RD` : "no attempts"} />
        <Stat label="Solved" value={d.totals.solved} sub={`${d.totals.attempts} attempts`} />
        <Stat label="Accuracy" value={pct(d.totals.accuracy.rate)} sub={d.totals.accuracy.n ? `95% CI ${pct(d.totals.accuracy.low)}–${pct(d.totals.accuracy.high)}` : ""} />
        <Stat label="Today" value={`${today} min`} sub="measured solving time" />
        <Stat label="Streak" value={d.totals.current_streak} sub="consecutive correct" />
        <Stat label="Week" value={`${d.consistency.days_trained_last_7}/7`} sub={`plan streak ${d.consistency.streak_days} d`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card">
          <h2>Puzzle rating progression</h2>
          <div className="muted mb-2 text-xs">{d.rating.note}</div>
          <div className="h-56">
            {d.rating.series.length > 1 ? (
              <ResponsiveContainer>
                <LineChart data={d.rating.series}>
                  <CartesianGrid stroke="#2a2e34" vertical={false} />
                  <XAxis dataKey="ts" tick={axis} tickFormatter={(t) => t.slice(5, 10)} minTickGap={30} />
                  <YAxis tick={axis} domain={["auto", "auto"]} width={40} />
                  <Tooltip {...tip} />
                  <Line dataKey="rating" stroke="#8fbf6a" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            ) : <Empty />}
          </div>
        </div>
        <div className="card">
          <h2>Daily training time (28 days)</h2>
          <div className="h-56 pt-4">
            <ResponsiveContainer>
              <BarChart data={d.daily_minutes}>
                <CartesianGrid stroke="#2a2e34" vertical={false} />
                <XAxis dataKey="day" tick={axis} tickFormatter={(t) => t.slice(8)} interval={3} />
                <YAxis tick={axis} width={30} />
                <Tooltip {...tip} />
                <Bar dataKey="minutes" fill="#5fb36b" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <ThemeList title="Tactical weaknesses" rows={d.weakest_themes} bad />
        <ThemeList title="Strongest themes" rows={d.strongest_themes} />
        <div className="card">
          <h2>Success by rating range</h2>
          <table className="mt-2 w-full text-sm">
            <tbody>
              {d.by_band.map((b: any) => (
                <tr key={b.band} className="border-t border-ink-700">
                  <td className="py-1">{b.band}<div className="text-xs text-ink-400">{b.range}</div></td>
                  <td className="text-right tabular-nums">{pct(b.rate)}</td>
                  <td className="w-12 text-right text-xs text-ink-400">n={b.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="muted mt-2 text-xs">Current band: {d.band.label} · median solve {fmtMs(d.totals.median_solve_ms)}</div>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card">
          <h2>Today's plan</h2>
          {plan ? (
            <ul className="mt-2 space-y-1 text-sm">
              {plan.blocks.map((b: any) => (
                <li key={b.id} className="flex justify-between"><span className={b.completed ? "text-good line-through" : ""}>{b.title}</span><span className="text-ink-400">{b.minutes} min</span></li>
              ))}
            </ul>
          ) : <Empty />}
          <Link to="/plan" className="mt-2 inline-block text-sm text-accent">Open plan →</Link>
        </div>
        <div className="card">
          <h2>Training history</h2>
          <table className="mt-2 w-full text-sm">
            <tbody>
              {d.history.length === 0 && <tr><td className="muted">No sessions yet.</td></tr>}
              {d.history.map((h: any) => (
                <tr key={h.id} className="border-t border-ink-700">
                  <td className="py-1">{h.started_at.slice(0, 16).replace("T", " ")}</td>
                  <td>{h.kind}{h.theme ? ` · ${h.theme}` : ""}</td>
                  <td className="text-right tabular-nums">{h.correct}/{h.attempts}</td>
                  <td className="text-right text-ink-400">{h.minutes}m{h.break_suggested ? " ⚑" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h2>Real games (primary outcome)</h2>
        {d.games.length === 0 ? <div className="muted mt-1">Import your games to measure what matters: accuracy and errors in real play. <Link className="text-accent" to="/games">Import PGN →</Link></div> : (
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={d.games}>
                <CartesianGrid stroke="#2a2e34" vertical={false} />
                <XAxis dataKey="date" tick={axis} />
                <YAxis tick={axis} width={30} domain={[0, 100]} />
                <Tooltip {...tip} />
                <Line dataKey="accuracy" stroke="#8fbf6a" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: any; sub?: string }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className="stat">{value}</div>
      {sub && <div className="text-xs text-ink-400">{sub}</div>}
    </div>
  );
}

function ThemeList({ title, rows, bad }: { title: string; rows: any[]; bad?: boolean }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      {rows.length === 0 ? <div className="muted mt-1">Needs ≥5 attempts per theme.</div> : (
        <ul className="mt-2 space-y-1.5 text-sm">
          {rows.map((r) => (
            <li key={r.theme}>
              <div className="flex justify-between"><span>{r.theme}</span><span className="tabular-nums">{pct(r.rate)} <span className="text-xs text-ink-400">n={r.n}</span></span></div>
              <div className="h-1.5 rounded bg-ink-700"><div className={`h-1.5 rounded ${bad ? "bg-bad" : "bg-good"}`} style={{ width: `${(r.rate ?? 0) * 100}%` }} /></div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const Empty = () => <div className="muted flex h-full items-center justify-center text-sm">Not enough data yet</div>;
