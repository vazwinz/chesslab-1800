import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar as RBar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTip, NumbersTable } from "../components/charts";
import Help from "../components/Help";
import RoutinePanel from "../components/RoutinePanel";
import { Bar, Empty, ErrorNote, Metric, PageHeader, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, dayShort, num, pct, secs } from "../lib/format";
import { SESSION_KINDS, TIME_CLASS, useMeta } from "../lib/meta";
import { usePrefs } from "../lib/prefs";
import { useRoutine } from "../lib/routine";
import { useColors } from "../lib/useColors";

export default function Home() {
  const [d, setD] = useState<any>(null);
  const [setup, setSetup] = useState<any>(null);
  const [loop, setLoop] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const meta = useMeta();
  const c = useColors();
  const { prefs } = usePrefs();
  const { routine, setRoutine } = useRoutine();

  useEffect(() => {
    api.get("/api/dashboard").then(setD).catch((e) => setErr(e.message));
    api.get("/api/setup").then(setSetup).catch(() => {});
    api.get("/api/cognitive/loop").then(setLoop).catch(() => {});
  }, []);

  if (err) return <ErrorNote>{err}</ErrorNote>;
  if (!d) return <Spinner label="Carregando…" />;
  const noPuzzles = setup && setup.puzzles === 0;
  const rr = d.real_rating;
  const main = rr?.main;
  const phase = loop?.phase;

  return (
    <div>
      <PageHeader title="Início" purpose="O seu ponto de partida: a rotina de hoje, onde você está em relação à meta e como o treino está indo." />

      {(noPuzzles || !d.games.length) && (
        <section className="mb-8">
          <h2 className="mb-3">Para começar</h2>
          <ol className="space-y-3">
            <Step done={!noPuzzles} n={1} title="Baixar os puzzles do Lichess" to="/configuracoes" cta="Baixar puzzles">
              Alguns milhões de puzzles de partidas reais. Uns 300 MB e cerca de 15 minutos de importação, uma vez só.
            </Step>
            <Step done={d.games.length > 0} n={2} title="Importar as suas partidas" to="/partidas" cta="Importar partidas">
              Pelo seu usuário do Chess.com ou colando um PGN. Elas mostram o seu rating real e os erros que mais se repetem.
            </Step>
            <Step done={(loop?.baseline?.attempts ?? 0) >= 20 || (phase && phase !== "measure")} n={3} title="Fazer os 20 puzzles de medição do ciclo" to="/treinar?modo=loop" cta="Começar o ciclo">
              O ciclo mede, encontra o seu erro mais comum e treina exatamente isso.
            </Step>
          </ol>
        </section>
      )}

      {routine && <div className="mb-10"><RoutinePanel r={routine} onChange={setRoutine} /></div>}

      <section className="mb-10">
        <div>
          <div className="flex items-center gap-2">
            <h2>Meta: {num(rr.goal)} no Chess.com</h2>
            <Help id="real_rating" />
          </div>
          {main ? (
            <>
              <div className="mt-3 flex flex-wrap items-end gap-x-10 gap-y-3">
                <div>
                  <div className="text-sm text-muted">Agora ({TIME_CLASS[main.time_class] ?? "partidas"})</div>
                  <div className="tnum text-3xl font-bold leading-none">{num(main.current)}</div>
                </div>
                <Metric label="Faltam" value={rr.to_goal > 0 ? num(rr.to_goal) : "meta batida"} tone={rr.to_goal <= 0 ? "good" : undefined} />
                <Metric label="Últimos 30 dias" value={main.change_30d == null ? "—" : `${main.change_30d > 0 ? "+" : ""}${main.change_30d}`}
                  tone={main.change_30d > 0 ? "good" : main.change_30d < 0 ? "bad" : undefined} />
                <Metric label="Melhor" value={num(main.best)} sub={`${num(main.games)} partidas`} />
              </div>
              <div className="mt-4 h-48">
                <ResponsiveContainer>
                  <LineChart data={main.series} margin={{ left: -12, right: 8, top: 8 }}>
                    <CartesianGrid stroke={c.rule} vertical={false} />
                    <XAxis dataKey="date" tick={c.axis} tickFormatter={dayShort} minTickGap={32} />
                    <YAxis tick={c.axis} domain={["dataMin - 30", (max: number) => Math.max(max + 30, rr.goal + 20)]} width={48} />
                    <Tooltip cursor={{ stroke: c.rule }} content={<ChartTip value={(v) => num(v)} title={(l) => `Partida de ${dayShort(String(l))}`} />} />
                    <ReferenceLine y={rr.goal} stroke={c.muted} strokeDasharray="4 4" label={{ value: `meta ${rr.goal}`, fill: c.muted, fontSize: 12, position: "insideTopLeft" }} />
                    <Line dataKey="elo" stroke={c.pen} strokeWidth={2} dot={main.series.length < 3 ? { r: 4, fill: c.pen, stroke: c.sheet, strokeWidth: 2 } : false}
                      activeDot={{ r: 4, stroke: c.sheet, strokeWidth: 2 }} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <NumbersTable head={["Partida", "Rating"]} rows={main.series.slice().reverse().map((p: any) => [dayShort(p.date), num(p.elo)])} />
              {rr.classes.length > 1 && (
                <p className="mt-1 text-sm text-muted">Outros ritmos: {rr.classes.filter((x: any) => x !== main && x.time_class !== main.time_class)
                  .map((x: any) => `${x.label} ${x.current}`).join(", ")}</p>
              )}
            </>
          ) : (
            <div className="mt-3">
              <Empty title="Sem rating real ainda" action={<Link className="btn-primary" to="/partidas">Importar partidas do Chess.com</Link>}>
                {d.games.length > 0
                  ? "As partidas importadas não trazem o rating dos jogadores no cabeçalho do PGN. Importe pelo seu usuário do Chess.com: essas partidas trazem, e o rating aparece aqui com a distância até a meta."
                  : "O AURA lê o seu rating no cabeçalho das partidas importadas. Importe pelo seu usuário do Chess.com e ele aparece aqui, com a distância até a meta."}
              </Empty>
            </div>
          )}
        </div>
      </section>

      <section className="mb-10">
        <div className="mb-3 flex items-center gap-2"><h2>Puzzles</h2><Help id="puzzle_vs_real" /></div>
        <div className="grid grid-cols-2 gap-x-8 gap-y-5 border-y border-rule py-5 sm:grid-cols-3 lg:grid-cols-5">
          <Metric label="Rating de puzzle" help="puzzle_rating" value={d.totals.attempts ? `${d.rating.current}${d.rating.provisional ? "?" : ""}` : "—"}
            sub={d.totals.attempts ? `margem ±${d.rating.rd}` : "sem exercícios ainda"} />
          <Metric label="Acerto" help="ci" value={pct(d.totals.accuracy.rate)}
            sub={d.totals.accuracy.n ? `IC 95%: ${pct(d.totals.accuracy.low)} a ${pct(d.totals.accuracy.high)}` : undefined} />
          <Metric label="Resolvidos" value={num(d.totals.solved)} sub={`de ${num(d.totals.attempts)}`} />
          <Metric label="Sequência" help="streak" value={num(d.totals.current_streak)} sub="acertos seguidos" />
          <Metric label="Tempo médio" value={secs(d.totals.median_solve_ms)} sub="mediana dos acertos" />
        </div>
        <div className="mt-6 grid gap-8 lg:grid-cols-2">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm text-muted">Evolução do rating de puzzle <Help id="rd" /></div>
            <div className="h-56">
              {d.rating.series.length > 1 ? (
                <ResponsiveContainer>
                  <LineChart data={d.rating.series} margin={{ left: -12, right: 8, top: 8 }}>
                    <CartesianGrid stroke={c.rule} vertical={false} />
                    <XAxis dataKey="ts" tick={c.axis} tickFormatter={tsTick(d.rating.series)} minTickGap={36} />
                    <YAxis tick={c.axis} domain={["auto", "auto"]} width={48} />
                    <Tooltip cursor={{ stroke: c.rule }} content={<ChartTip value={(v) => num(Math.round(v))} title={(t) => dateTime(String(t))} />} />
                    <Line dataKey="rating" stroke={c.pen} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: c.sheet, strokeWidth: 2 }} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : <Empty title="O gráfico aparece depois dos primeiros puzzles" action={<Link className="btn" to="/treinar">Treinar agora</Link>} />}
            </div>
            <NumbersTable head={["Quando", "Rating"]} rows={d.rating.series.slice().reverse().map((p: any) => [dateTime(p.ts), num(Math.round(p.rating))])} />
          </div>
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm text-muted">Minutos de treino por dia <Help id="daily_minutes" /></div>
            <div className="h-56">
              {!d.daily_minutes.some((x: any) => x.minutes > 0) ? <Empty title="Os minutos aparecem quando você treinar" /> : <ResponsiveContainer>
                <BarChart data={d.daily_minutes} margin={{ left: -20, right: 8, top: 8 }} barCategoryGap={2}>
                  <CartesianGrid stroke={c.rule} vertical={false} />
                  <XAxis dataKey="day" tick={c.axis} tickFormatter={dayShort} interval={6} />
                  <YAxis tick={c.axis} width={40} allowDecimals={false} />
                  <Tooltip cursor={{ fill: c.penSoft }} content={<ChartTip value={(v) => `${String(v).replace(".", ",")} min`} title={(l) => dayShort(String(l))} />} />
                  <RBar dataKey="minutes" fill={c.pen} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>}
            </div>
            <NumbersTable head={["Dia", "Minutos"]} rows={d.daily_minutes.filter((x: any) => x.minutes > 0).reverse().map((x: any) => [dayShort(x.day), String(x.minutes).replace(".", ",")])} />
          </div>
        </div>
      </section>

      <section className="mb-10 grid gap-8 lg:grid-cols-3">
        <ThemeList title="Temas mais fracos" rows={d.weakest_themes} tone="bad" />
        <ThemeList title="Temas mais fortes" rows={d.strongest_themes} tone="good" />
        <div>
          <div className="mb-2 flex items-center gap-2"><h2>Acerto por faixa</h2><Help id="bands" /></div>
          <ul className="space-y-2 text-sm">
            {d.by_band.map((b: any) => (
              <li key={b.band}>
                <div className="flex justify-between"><span>{b.band} <span className="text-faint">{b.range}</span></span><span className="tnum">{pct(b.rate)} <span className="text-faint">({num(b.n)})</span></span></div>
                <Bar value={b.rate} />
              </li>
            ))}
          </ul>
          <p className="mt-2 text-sm text-muted">Faixa atual: {d.band.label}</p>
        </div>
      </section>

      <section>
        <h2 className="mb-2">Últimas sessões</h2>
        {d.history.length === 0 ? <p className="text-muted">Nenhuma sessão ainda.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-muted"><tr><th className="py-2 font-normal">Quando</th><th className="font-normal">Modo</th><th className="text-right font-normal">Acertos</th><th className="text-right font-normal">Tempo</th></tr></thead>
              <tbody>
                {d.history.map((h: any) => (
                  <tr key={h.id} className="border-t border-rule">
                    <td className="py-2">{dateTime(h.started_at)}</td>
                    <td>{SESSION_KINDS[h.kind] ?? h.kind}{h.theme ? `: ${meta.categories[h.theme] ?? h.theme}` : ""}{h.break_suggested && <span className="ml-2 text-warn" title="pausa sugerida">pausa sugerida</span>}</td>
                    <td className="tnum text-right">{h.correct}/{h.attempts}</td>
                    <td className="tnum text-right text-muted">{String(h.minutes).replace(".", ",")} min</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <p className="mt-8 text-xs text-faint">Todos os números vêm dos seus exercícios e partidas salvos neste computador. Nada é estimado. {prefs.player_names ? `Usuários: ${prefs.player_names}.` : ""}</p>
    </div>
  );
}

function Step({ done, n, title, to, cta, children }: { done: boolean; n: number; title: string; to: string; cta: string; children: React.ReactNode }) {
  return (
    <li className={`flex flex-wrap items-center gap-4 rounded-xl border p-4 ${done ? "border-rule opacity-70" : "border-pen/40 bg-pen/5"}`}>
      <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold ${done ? "bg-good text-white" : "bg-pen text-pen-ink"}`}>{done ? "✓" : n}</span>
      <div className="min-w-[14rem] flex-1">
        <p className="font-bold">{title}</p>
        <p className="text-sm text-muted">{children}</p>
      </div>
      {!done && <Link className="btn-primary" to={to}>{cta}</Link>}
    </li>
  );
}

function ThemeList({ title, rows, tone }: { title: string; rows: any[]; tone: "good" | "bad" }) {
  const meta = useMeta();
  return (
    <div>
      <h2 className="mb-2">{title}</h2>
      {rows.length === 0 ? <p className="text-sm text-muted">Aparece quando um tema tiver 5 tentativas ou mais.</p> : (
        <ul className="space-y-2 text-sm">
          {rows.map((r) => (
            <li key={r.theme}>
              <div className="flex justify-between gap-2"><span>{meta.theme(r.theme)}</span><span className="tnum">{pct(r.rate)} <span className="text-faint">({num(r.n)})</span></span></div>
              <Bar value={r.rate} tone={tone} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Axis labels for a time series: dates, or hours when everything happened within a day or two. */
function tsTick(series: { ts: string }[]) {
  const span = series.length > 1 ? new Date(series[series.length - 1].ts).getTime() - new Date(series[0].ts).getTime() : 0;
  return span < 2 * 86400000
    ? (t: string) => new Date(t).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
    : (t: string) => new Date(t).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}
