import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, CATEGORY_LABEL, fmtMs, pct } from "../lib/api";

const TABS = ["Loop", "Profile", "Error DNA", "Retention", "Interventions", "Attention", "Pressure", "Prediction", "Science"] as const;
const axis = { stroke: "#8a919c", fontSize: 11 };
const tip = { contentStyle: { background: "#16181b", border: "1px solid #3a3f47", fontSize: 12 } };

export default function Cognitive() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Loop");
  return (
    <div className="space-y-4">
      <div>
        <h1>Cognitive Engine</h1>
        <div className="muted">Observable chess performance only — not IQ, brain activity or any clinical trait.</div>
      </div>
      <div className="flex gap-1 overflow-x-auto border-b border-ink-700 pb-px">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`whitespace-nowrap rounded-t px-3 py-1.5 text-sm ${tab === t ? "border border-b-0 border-ink-700 bg-ink-900 text-accent" : "text-ink-400 hover:text-ink-100"}`}>{t}</button>
        ))}
      </div>
      {tab === "Loop" && <LoopTab />}
      {tab === "Profile" && <ProfileTab />}
      {tab === "Error DNA" && <DnaTab />}
      {tab === "Retention" && <RetentionTab />}
      {tab === "Interventions" && <InterventionsTab />}
      {tab === "Attention" && <AttentionTab />}
      {tab === "Pressure" && <PressureTab />}
      {tab === "Prediction" && <PredictionTab />}
      {tab === "Science" && <ScienceTab />}
    </div>
  );
}

function useApi(path: string) {
  const [d, setD] = useState<any>(null);
  const [e, setE] = useState<string | null>(null);
  useEffect(() => { api.get(path).then(setD).catch((x) => setE(x.message)); }, [path]);
  return { d, e };
}

const Wrap = ({ e, d, children }: any) => (e ? <div className="card text-bad">{e}</div> : !d ? <div className="muted">Loading…</div> : children);
const Rate = ({ w }: { w: any }) => (!w || w.n === 0 ? <span className="text-ink-400">no data</span> : (
  <span className="tabular-nums">{pct(w.rate)} <span className="text-xs text-ink-400">[{pct(w.low)}–{pct(w.high)}] n={w.n}{w.sufficient === false ? " · insufficient" : ""}</span></span>
));

function LoopTab() {
  const { d, e } = useApi("/api/cognitive/loop");
  return (
    <Wrap d={d} e={e}>
      {d && (
        <div className="space-y-4">
          <div className="card">
            <div className="flex flex-wrap gap-2">
              {d.steps.map((s: string) => {
                const active = s === d.phase;
                return <span key={s} className={`rounded-full border px-3 py-1 text-sm ${active ? "border-accent bg-accent/15 text-accent" : "border-ink-600 text-ink-400"}`}>{s}</span>;
              })}
            </div>
            <div className="mt-3 text-sm">
              {d.phase === "measure" && <>Collecting a baseline: {d.baseline.attempts ?? 0}/{d.baseline.needed} mixed puzzles (or ≥3 analysed games).</>}
              {d.phase === "practice" && d.assignment && <>Practising <b>{d.assignment.title}</b> for <b>{CATEGORY_LABEL[d.assignment.category]}</b>{d.assignment.theme ? ` (${d.assignment.theme})` : ""}: {d.assignment.done}/{d.assignment.target}. {d.assignment.description}</>}
              {d.phase === "reassess" && <>Reassessment on mixed, non-targeted puzzles: {d.reassessment.done ?? 0}/{d.reassessment.needed}.</>}
              {d.phase === "diagnose" && <>Waiting for enough recurring errors to diagnose.</>}
            </div>
            <div className="muted mt-2 text-xs">Start “Closed-loop training” in Train to advance. Outcomes use real-game error rates when ≥3 analysed games exist before and after an intervention.</div>
          </div>
          <div className="card">
            <h2>Completed cycles</h2>
            {d.history.length === 0 ? <div className="muted mt-1">None yet.</div> : (
              <table className="mt-2 w-full text-sm"><tbody>
                {d.history.map((h: any) => (
                  <tr key={h.cycle_id} className="border-t border-ink-700">
                    <td className="py-1">{h.finished_at.slice(0, 10)}</td>
                    <td>{h.adaptation.intervention}</td>
                    <td>{CATEGORY_LABEL[h.adaptation.category]}</td>
                    <td className="tabular-nums">{pct(h.adaptation.pre?.rate, 1)} → {pct(h.adaptation.post?.rate, 1)} <span className="text-xs text-ink-400">({h.adaptation.post?.source})</span></td>
                    <td className={h.adaptation.improved ? "text-good" : h.adaptation.improved === false ? "text-bad" : "text-ink-400"}>{h.adaptation.improved == null ? "inconclusive" : h.adaptation.improved ? "improved" : "no improvement"}</td>
                  </tr>
                ))}
              </tbody></table>
            )}
          </div>
          <div className="card">
            <h2>Log</h2>
            <ul className="mt-2 space-y-1 font-mono text-xs text-ink-300">{d.log.slice().reverse().map((l: any, i: number) => <li key={i}>{l.ts.slice(0, 16)} [{l.phase}] {l.msg}</li>)}</ul>
          </div>
        </div>
      )}
    </Wrap>
  );
}

function ProfileTab() {
  const { d, e } = useApi("/api/cognitive/profile");
  return (
    <Wrap d={d} e={e}>
      {d && (
        <div className="grid gap-3 md:grid-cols-2">
          <div className="card"><h2>Pattern recognition</h2><div className="muted text-xs">{d.pattern_recognition.description}</div><div className="mt-2"><Rate w={d.pattern_recognition} /></div>
            <div className="text-xs text-ink-400">vs. difficulty: {d.pattern_recognition.rating_adjusted_residual ?? "—"}</div></div>
          <div className="card"><h2>Calculation</h2><div className="muted text-xs">{d.calculation.description}</div>
            <div className="mt-2 space-y-1 text-sm">{Object.entries(d.calculation.by_length).map(([k, v]: any) => <div key={k}>{k} move{k === "1" ? "" : "s"}: <Rate w={v} /></div>)}</div>
            <div className="mt-1 text-sm">Depth reached: {d.calculation.depth_reached ?? "—"} · Blind: <Rate w={d.calculation.blind_accuracy} /></div></div>
          <div className="card"><h2>Threat detection</h2><div className="muted text-xs">{d.threat_detection.description}</div><div className="mt-2 text-sm">Defensive puzzles: <Rate w={d.threat_detection.defensive_puzzles} /></div>
            <div className="text-sm">Missed threats / 100 game moves: {d.threat_detection.game_missed_threats_per_100 ?? "—"} <span className="text-xs text-ink-400">({d.threat_detection.game_moves_analysed} moves)</span></div></div>
          <div className="card"><h2>Candidate generation</h2><div className="muted text-xs">{d.candidate_generation.description}</div><div className="mt-2 text-sm">{d.candidate_generation.n ? `${pct(d.candidate_generation.mean_score)} (n=${d.candidate_generation.n})` : "no data — use Candidate moves mode"}</div></div>
          <div className="card"><h2>Working-memory load</h2><div className="muted text-xs">{d.working_memory_load.description}</div>
            <div className="mt-2 space-y-1 text-sm">{d.working_memory_load.by_length.map((r: any) => <div key={r.solution_len}>{r.solution_len}: board <Rate w={r.board} /> · blind <Rate w={r.blind} /></div>)}</div></div>
          <div className="card"><h2>Decision latency</h2><div className="mt-1 text-sm">Median first move — correct: {fmtMs(d.decision_latency.median_correct_ms)} (n={d.decision_latency.n_correct}) · wrong: {fmtMs(d.decision_latency.median_wrong_ms)} (n={d.decision_latency.n_wrong})</div></div>
          <div className="card md:col-span-2"><h2>Consistency under time pressure</h2><div className="muted text-xs">{d.time_pressure_consistency.description}</div>
            <div className="mt-2 grid gap-1 text-sm sm:grid-cols-2">
              <div>Pressure quality: <Rate w={d.time_pressure_consistency.pressure_quality} /></div>
              <div>Normal quality: <Rate w={d.time_pressure_consistency.normal_quality} /></div>
              <div>Timeouts: {d.time_pressure_consistency.pressure_timeouts.timeouts}/{d.time_pressure_consistency.pressure_timeouts.n}</div>
              <div>Game errors in time trouble: <Rate w={d.time_pressure_consistency.game_low_clock_error_rate} /></div>
            </div></div>
          <div className="muted md:col-span-2 text-xs">{d.disclaimer} Sample: {d.sample.puzzle_attempts} attempts, {d.sample.analysed_games} games.</div>
        </div>
      )}
    </Wrap>
  );
}

function DnaTab() {
  const { d, e } = useApi("/api/cognitive/error-dna");
  return (
    <Wrap d={d} e={e}>
      {d && (
        <div className="space-y-3">
          <div className="muted text-sm">Last {d.window_days} days · {d.puzzle_attempts} puzzle attempts · {d.game_moves_analyzed} analysed game moves. Recency-weighted (half-life 3 weeks). Experimental heuristic labels.</div>
          {d.patterns.length === 0 ? <div className="card muted">No classified mistakes yet.</div> : (
            <>
              <div className="card h-64">
                <ResponsiveContainer>
                  <BarChart data={d.patterns.map((p: any) => ({ ...p, name: CATEGORY_LABEL[p.category] }))} layout="vertical" margin={{ left: 40 }}>
                    <CartesianGrid stroke="#2a2e34" horizontal={false} />
                    <XAxis type="number" tick={axis} />
                    <YAxis type="category" dataKey="name" tick={axis} width={150} />
                    <Tooltip {...tip} />
                    <Bar dataKey="recent_weight" fill="#e0645c" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="card overflow-x-auto">
                <table className="w-full text-sm"><thead className="text-left text-ink-400"><tr><th>Category</th><th>Count</th><th>Games</th><th>Puzzles</th><th>Recurring</th><th>Top themes</th></tr></thead><tbody>
                  {d.patterns.map((p: any) => (
                    <tr key={p.category} className="border-t border-ink-700"><td className="py-1">{CATEGORY_LABEL[p.category]}</td><td>{p.count}</td><td>{p.from_games}</td><td>{p.from_puzzles}</td>
                      <td>{p.recurring ? <span className="text-bad">yes</span> : "no"}</td><td className="text-xs">{p.top_themes.map((t: any) => `${t[0]} (${t[1]})`).join(", ")}</td></tr>
                  ))}
                </tbody></table>
              </div>
            </>
          )}
          <details className="card text-sm"><summary className="cursor-pointer">How mistakes are classified</summary>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-ink-300">{d.priority.map((k: string) => <li key={k}>{d.categories[k]}</li>)}</ol>
            <div className="muted mt-2 text-xs">The first matching rule wins. See docs/COGNITIVE_ENGINE.md for exact thresholds.</div>
          </details>
        </div>
      )}
    </Wrap>
  );
}

function RetentionTab() {
  const { d, e } = useApi("/api/cognitive/retention");
  return (
    <Wrap d={d} e={e}>
      {d && (
        <div className="space-y-3">
          <div className="muted text-sm">{d.note}</div>
          <div className="card">
            <h2>Success vs. delay since last exposure</h2>
            <table className="mt-2 w-full text-sm"><thead className="text-left text-ink-400"><tr><th>Delay</th><th>All</th><th>New positions only</th></tr></thead><tbody>
              {d.curve.map((b: any) => <tr key={b.delay} className="border-t border-ink-700"><td className="py-1">{b.delay}</td><td>{b.n ? `${pct(b.success)} (n=${b.n})` : "—"}</td><td>{b.new_positions_n ? `${pct(b.new_positions_success)} (n=${b.new_positions_n})` : "—"}</td></tr>)}
            </tbody></table>
          </div>
          <div className="card overflow-x-auto">
            <h2>Concepts ({d.due_count} due)</h2>
            <table className="mt-2 w-full text-sm"><thead className="text-left text-ink-400"><tr><th>Concept</th><th>Interval</th><th>Reps</th><th>Lapses</th><th>Transfer</th><th>Recall</th><th>Due</th></tr></thead><tbody>
              {d.concepts.map((c: any) => <tr key={c.concept} className="border-t border-ink-700"><td className="py-1">{c.concept}</td><td>{c.interval_days} d</td><td>{c.reps}</td><td>{c.lapses}</td><td>{c.transfer.ok}/{c.transfer.n}</td><td>{c.recall.ok}/{c.recall.n}</td><td>{c.due ? <span className="text-warn">due</span> : c.due_at.slice(0, 10)}</td></tr>)}
            </tbody></table>
          </div>
        </div>
      )}
    </Wrap>
  );
}

function InterventionsTab() {
  const { d, e } = useApi("/api/cognitive/interventions");
  return (
    <Wrap d={d} e={e}>
      {d && (
        <div className="space-y-3">
          <div className="card">
            <h2>What has worked for you</h2>
            <div className="muted text-xs">Beta posterior P(intervention reduced the error). Few trials, no control group → a hint, not proof.</div>
            {d.effectiveness.length === 0 ? <div className="muted mt-2">No completed intervention blocks yet.</div> : (
              <table className="mt-2 w-full text-sm"><tbody>{d.effectiveness.map((r: any) => (
                <tr key={r.intervention + r.category} className="border-t border-ink-700"><td className="py-1">{r.title}</td><td>{CATEGORY_LABEL[r.category]}</td><td>{r.trials} trials</td><td className="tabular-nums">P={r.p_improves}</td><td className="tabular-nums">Δ {pct(r.mean_effect, 1)}</td></tr>
              ))}</tbody></table>
            )}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {d.catalog.map((i: any) => (
              <div key={i.key} className="card">
                <div className="font-medium">{i.title}</div>
                <div className="muted text-sm">{i.description}</div>
                <div className="mt-2 flex flex-wrap gap-1">{i.targets.map((t: string) => <span key={t} className="chip">{CATEGORY_LABEL[t]}</span>)}</div>
                <div className="mt-1 text-xs text-ink-400">Principles: {i.principles.join(", ").replace(/_/g, " ")}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Wrap>
  );
}

function AttentionTab() {
  const { d, e } = useApi("/api/cognitive/attention");
  return (
    <Wrap d={d} e={e}>
      {d && (
        <div className="space-y-3">
          <div className="card">
            <h2>Latest session</h2>
            {!d.latest ? <div className="muted">No sessions yet.</div> : (
              <>
                <div className="mt-1 text-sm">Status: <b className={d.latest.suggest_break ? "text-warn" : ""}>{d.latest.status}</b> · {d.latest.n} attempts · {d.latest.minutes} min</div>
                {d.latest.reasons?.length > 0 && <div className="text-sm text-warn">{d.latest.reasons.join("; ")}</div>}
                <div className="mt-2 h-48">
                  <ResponsiveContainer>
                    <LineChart data={d.latest.series}>
                      <CartesianGrid stroke="#2a2e34" vertical={false} />
                      <XAxis dataKey="i" tick={axis} />
                      <YAxis yAxisId="l" tick={axis} width={30} domain={[-1, 1]} />
                      <YAxis yAxisId="r" orientation="right" tick={axis} width={40} tickFormatter={(v) => `${Math.round(v / 1000)}s`} />
                      <Tooltip {...tip} />
                      <Line yAxisId="l" dataKey="residual" stroke="#8fbf6a" dot />
                      <Line yAxisId="r" dataKey="total_ms" stroke="#d9a441" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="muted text-xs">Green: result minus expected (given puzzle difficulty). Amber: solving time. {d.latest.disclaimer}</div>
              </>
            )}
          </div>
          <div className="card text-sm">Lighter day recommended: <b>{d.light_day.light_day ? "yes" : "no"}</b> <span className="text-ink-400">(break flags in 3 days: {d.light_day.break_flags_3d}; difficulty-adjusted result: {d.light_day.residual_3d?.toFixed?.(2) ?? "—"}, n={d.light_day.n_3d})</span></div>
        </div>
      )}
    </Wrap>
  );
}

function PressureTab() {
  const { d, e } = useApi("/api/cognitive/pressure");
  return (
    <Wrap d={d} e={e}>
      {d && (
        <div className="card overflow-x-auto">
          <h2>Pressure ladder — current level {d.current.level} ({d.current.seconds}s)</h2>
          <div className="muted text-xs">{d.note}</div>
          <table className="mt-2 w-full text-sm"><thead className="text-left text-ink-400"><tr><th>Level</th><th>Clock</th><th>n</th><th>Decision quality</th><th>Timeouts</th><th>Time used</th><th>cp lost when wrong</th></tr></thead><tbody>
            {d.levels.map((l: any) => {
              const r = d.by_level[l.level];
              return <tr key={l.level} className="border-t border-ink-700"><td className="py-1">{l.level}</td><td>{l.seconds}s</td><td>{r?.n ?? 0}</td><td>{r ? <Rate w={r.decision_quality} /> : "—"}</td><td>{r ? pct(r.timeout_rate.rate) : "—"}</td><td>{r?.mean_time_used != null ? pct(r.mean_time_used) : "—"}</td><td>{r?.mean_cp_loss_when_wrong ?? "—"}</td></tr>;
            })}
          </tbody></table>
        </div>
      )}
    </Wrap>
  );
}

function Trend({ t, unit }: { t: any; unit: string }) {
  if (!t || t.status !== "ok") return <div className="muted">insufficient data</div>;
  return (
    <div className="text-sm">
      <div>Trend: {t.slope_per_30d > 0 ? "+" : ""}{t.slope_per_30d} {unit}/30 {""}days <span className="text-xs text-ink-400">95% CI [{t.slope_per_30d_ci.join(", ")}]{t.direction_certain ? "" : " — direction not established"}</span></div>
      {t.forecasts.map((f: any) => <div key={f.days_ahead}>+{f.days_ahead}: {f.value} <span className="text-xs text-ink-400">(95% prediction interval {f.pi_low} – {f.pi_high})</span></div>)}
    </div>
  );
}

function PredictionTab() {
  const { d, e } = useApi("/api/cognitive/prediction");
  return (
    <Wrap d={d} e={e}>
      {d && (
        <div className="space-y-3">
          <div className="card border-warn/40 text-sm">{d.disclaimer}</div>
          <div className="card"><h2>Real games</h2>
            {d.games.status !== "ok" ? <div className="muted">Needs {d.games.needed} analysed games (have {d.games.games}).</div> : (
              <div className="mt-2 grid gap-3 sm:grid-cols-2"><div><div className="label">Accuracy</div><Trend t={d.games.accuracy} unit="pts" /></div><div><div className="label">Blunders / 100 moves</div><Trend t={d.games.blunders_per_100} unit="" /></div></div>
            )}</div>
          <div className="card"><h2>Puzzle rating</h2>
            {d.puzzle_rating.status !== "ok" ? <div className="muted">Needs {d.puzzle_rating.needed} training days (have {d.puzzle_rating.days}).</div> : <Trend t={d.puzzle_rating.rating} unit="pts" />}</div>
        </div>
      )}
    </Wrap>
  );
}

function ScienceTab() {
  const { d, e } = useApi("/api/cognitive/principles");
  return (
    <Wrap d={d} e={e}>
      {d && (
        <div className="space-y-3">
          <div className="muted text-sm">{d.note}</div>
          <div className="grid gap-3 md:grid-cols-2">
            {Object.entries(d.validated_principles).map(([k, p]: any) => (
              <div key={k} className="card">
                <div className="flex items-center justify-between"><div className="font-medium">{p.name}</div><span className="chip border-good/50 text-good">validated</span></div>
                <div className="muted text-sm">{p.summary}</div>
                <div className="mt-1 text-xs text-ink-400">Used by: {p.used_by.join("; ")}</div>
                <ul className="mt-1 list-disc pl-4 text-xs text-ink-400">{p.references.map((r: string) => <li key={r}>{r}</li>)}</ul>
              </div>
            ))}
          </div>
          <div className="card"><h2>Experimental features</h2>
            <ul className="mt-2 space-y-2 text-sm">{Object.entries(d.experimental_features).map(([k, v]: any) => <li key={k}><span className="chip mr-2 border-warn/50 text-warn">experimental</span><b>{k.replace(/_/g, " ")}</b> — <span className="text-ink-300">{v}</span></li>)}</ul></div>
        </div>
      )}
    </Wrap>
  );
}
