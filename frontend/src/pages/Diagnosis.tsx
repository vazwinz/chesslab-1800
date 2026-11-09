import { ReactNode, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Bar as RBar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTip, NumbersTable } from "../components/charts";
import Help from "../components/Help";
import { Bar, Empty, ErrorNote, PageHeader, Spinner, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { dateOnly, dateTime, num, pct, secs } from "../lib/format";
import { useMeta } from "../lib/meta";
import { useColors } from "../lib/useColors";

type TabKey = "ciclo" | "erros" | "retencao" | "fadiga" | "pressao" | "perfil" | "previsao" | "intervencoes" | "ciencia";
const TABS: { value: TabKey; label: string }[] = [
  { value: "ciclo", label: "Ciclo" },
  { value: "erros", label: "Error DNA" },
  { value: "retencao", label: "Retenção" },
  { value: "fadiga", label: "Fadiga" },
  { value: "pressao", label: "Pressão" },
  { value: "perfil", label: "Perfil" },
  { value: "previsao", label: "Previsão" },
  { value: "intervencoes", label: "O que funciona" },
  { value: "ciencia", label: "Ciência" },
];

export default function Diagnosis() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.some((t) => t.value === params.get("aba")) ? params.get("aba") : "ciclo") as TabKey;
  return (
    <div>
      <PageHeader title="Diagnóstico"
        purpose="O que os seus exercícios e partidas mostram sobre como você erra e como aprende. Abra depois de alguns dias de treino para decidir o que treinar." />
      <Tabs value={tab} onChange={(v) => setParams({ aba: v }, { replace: true })} items={TABS} />
      <div className="pt-6">
        {tab === "ciclo" && <LoopTab />}
        {tab === "erros" && <DnaTab />}
        {tab === "retencao" && <RetentionTab />}
        {tab === "fadiga" && <FatigueTab />}
        {tab === "pressao" && <PressureTab />}
        {tab === "perfil" && <ProfileTab />}
        {tab === "previsao" && <PredictionTab />}
        {tab === "intervencoes" && <InterventionsTab />}
        {tab === "ciencia" && <ScienceTab />}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ helpers
function useApi(path: string) {
  const [d, setD] = useState<any>(null);
  const [e, setE] = useState<string | null>(null);
  useEffect(() => {
    setD(null);
    setE(null);
    api.get(path).then(setD).catch((x) => setE(x.message));
  }, [path]);
  return { d, e };
}

function Wrap({ d, e, children }: { d: any; e: string | null; children: () => ReactNode }) {
  if (e) return <ErrorNote>{e}</ErrorNote>;
  if (!d) return <Spinner label="Carregando…" />;
  return <>{children()}</>;
}

function Intro({ children, help }: { children: ReactNode; help?: string }) {
  return <p className="mb-6 max-w-prose text-muted">{children}{help && <> <Help id={help} /></>}</p>;
}

function Section({ title, help, children, hint }: { title: string; help?: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <section className="border-t border-rule py-6 first:border-t-0 first:pt-0">
      <h2 className="flex items-center gap-2">{title}{help && <Help id={help} />}</h2>
      {hint && <p className="mt-1 max-w-prose text-sm text-muted">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** A success rate with its 95% interval and sample size; never a bare percentage. */
function Rate({ w, unit = "exercícios" }: { w: any; unit?: string }) {
  if (!w || !w.n) return <span className="text-faint">sem dados</span>;
  return (
    <span className="tnum">
      <b>{pct(w.rate)}</b>{" "}
      <span className="text-sm text-muted">(IC {pct(w.low)} a {pct(w.high)}, {num(w.n)} {unit})</span>
      {w.sufficient === false && <span className="ml-1.5 text-sm text-warn">poucos dados</span>}
    </span>
  );
}

/** A difference in points of score (0.12 → "12 pontos acima"). */
function points(x: number | null | undefined) {
  if (x == null) return "—";
  const p = Math.round(x * 100);
  if (p === 0) return "igual ao esperado";
  return `${Math.abs(p)} ${Math.abs(p) === 1 ? "ponto" : "pontos"} ${p > 0 ? "acima" : "abaixo"} do esperado`;
}

const cap = (t: string | undefined) => (t ? `${t[0].toUpperCase()}${t.slice(1)}` : "");

const pawns = (cp: number | null | undefined) =>
  cp == null ? "—" : `${(cp / 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} ${Math.abs(cp) === 100 ? "peão" : "peões"}`;

// ------------------------------------------------------------------ loop
const STEPS: { key: string; name: string; text: string }[] = [
  { key: "measure", name: "Medir", text: "20 puzzles variados, ou 3 partidas analisadas." },
  { key: "diagnose", name: "Diagnosticar", text: "Acha o erro que mais se repete." },
  { key: "intervene", name: "Intervir", text: "Escolhe um treino feito para esse erro." },
  { key: "practice", name: "Praticar", text: "30 exercícios do treino escolhido." },
  { key: "reassess", name: "Reavaliar", text: "20 puzzles variados de novo." },
  { key: "adapt", name: "Adaptar", text: "Compara antes e depois e aprende o que funciona para você." },
];

function LoopTab() {
  const { d, e } = useApi("/api/cognitive/loop");
  const meta = useMeta();
  return (
    <Wrap d={d} e={e}>{() => {
      const idx = d.phase === "done" ? STEPS.length : STEPS.findIndex((s) => s.key === d.phase);
      const a = d.assignment;
      const target = d.diagnosis?.target;
      return (
        <>
          <Intro help="loop">O ciclo é o modo principal de treino. Ele mede, encontra o seu erro mais comum, treina exatamente esse erro e mede de novo para ver se funcionou.</Intro>
          <ol className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6" aria-label="Etapas do ciclo">
            {STEPS.map((s, i) => {
              const done = i < idx, now = i === idx;
              return (
                <li key={s.key} aria-current={now ? "step" : undefined}
                  className={`rounded-xl border p-3 ${now ? "border-pen bg-pen/5" : "border-rule"} ${done ? "opacity-60" : ""}`}>
                  <div className="flex items-center gap-2">
                    <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${now ? "bg-pen text-pen-ink" : done ? "bg-good text-white" : "bg-sunk text-muted"}`}>
                      {done ? "✓" : i + 1}
                    </span>
                    <span className="font-bold">{s.name}</span>
                  </div>
                  <p className="mt-1 text-sm text-muted">{s.text}</p>
                </li>
              );
            })}
          </ol>

          <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
            <div className="space-y-4">
              <h2>Agora</h2>
              {d.phase === "measure" && (
                <div>
                  <p>Medição: {num(d.baseline.attempts ?? 0)} de {num(d.baseline.needed)} puzzles{d.baseline.games ? `, ${num(d.baseline.games)} partidas analisadas` : ""}.</p>
                  <div className="mt-2 max-w-sm"><Bar value={(d.baseline.attempts ?? 0) / (d.baseline.needed || 20)} /></div>
                </div>
              )}
              {d.phase === "diagnose" && <p>O ciclo está esperando erros suficientes para escolher um alvo. Continue treinando: cada erro entra no Error DNA.</p>}
              {target && (
                <div className="rounded-xl border border-rule p-4">
                  <p className="text-sm text-muted">Alvo deste ciclo</p>
                  <p className="mt-0.5 text-lg font-bold">{meta.dna(target)}</p>
                  <p className="text-muted">{cap(meta.error_dna[target]?.short)}{d.diagnosis.theme ? `. Tema mais comum: ${meta.theme(d.diagnosis.theme)}.` : "."}</p>
                  {meta.error_dna[target]?.tip && <p className="mt-2 text-sm">{meta.error_dna[target].tip}</p>}
                </div>
              )}
              {a && d.phase === "practice" && (
                <div>
                  <p><b>{a.title}</b>: {a.description}</p>
                  <div className="mt-2 flex max-w-sm items-center gap-3"><Bar value={a.done / (a.target || 1)} /><span className="tnum shrink-0 text-sm text-muted">{num(a.done)} de {num(a.target)}</span></div>
                </div>
              )}
              {d.phase === "reassess" && (
                <div>
                  <p>Reavaliação com puzzles variados: {num(d.reassessment.done ?? 0)} de {num(d.reassessment.needed)}.</p>
                  <div className="mt-2 max-w-sm"><Bar value={(d.reassessment.done ?? 0) / (d.reassessment.needed || 20)} /></div>
                </div>
              )}
              <Link className="btn-primary" to="/treinar?modo=loop">Continuar o ciclo</Link>
              <p className="text-sm text-muted">O resultado compara a frequência do erro antes e depois. Quando houver pelo menos 3 partidas analisadas antes e 3 depois da intervenção, a comparação usa as suas partidas, não os puzzles.</p>
            </div>
            <div>
              <h2>Registro</h2>
              {d.log.length === 0 ? <p className="mt-2 text-sm text-muted">Nada registrado ainda.</p> : (
                <ul className="mt-2 space-y-1.5 text-sm">
                  {d.log.slice().reverse().map((l: any, i: number) => (
                    <li key={i} className="flex gap-3"><span className="tnum shrink-0 text-faint">{dateTime(l.ts)}</span><span>{logText(l, meta)}</span></li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <Section title="Ciclos concluídos" hint="Frequência do erro alvo antes e depois de cada ciclo. Menor é melhor.">
            {d.history.length === 0 ? <p className="text-sm text-muted">Nenhum ciclo concluído ainda. Um ciclo completo tem cerca de 70 exercícios.</p> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-muted"><tr><th className="py-2 font-normal">Fim</th><th className="font-normal">Treino</th><th className="font-normal">Erro alvo</th><th className="text-right font-normal">Antes → depois</th><th className="pl-4 font-normal">Resultado</th></tr></thead>
                  <tbody>
                    {d.history.map((h: any) => {
                      const ad = h.adaptation || {};
                      return (
                        <tr key={h.cycle_id} className="border-t border-rule">
                          <td className="py-2">{dateOnly(h.finished_at)}</td>
                          <td>{meta.intervention(ad.intervention)}</td>
                          <td>{meta.dna(ad.category)}</td>
                          <td className="tnum text-right">{pct(ad.pre?.rate, 1)} → {pct(ad.post?.rate, 1)} <span className="text-faint">({ad.post?.source === "games" ? "partidas" : "puzzles"})</span></td>
                          <td className={`pl-4 font-bold ${ad.improved ? "text-good" : ad.improved === false ? "text-bad" : "text-muted"}`}>
                            {ad.improved == null ? "inconclusivo (poucos dados)" : ad.improved ? "✓ o erro diminuiu" : "✗ não diminuiu"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </>
      );
    }}</Wrap>
  );
}

function logText(l: any, meta: ReturnType<typeof useMeta>): string {
  const t = logBody(l, meta);
  return t ? `${t[0].toUpperCase()}${t.slice(1)}` : "";
}

function logBody(l: any, meta: ReturnType<typeof useMeta>): string {
  switch (l.code) {
    case "cycle_started": return "ciclo iniciado.";
    case "baseline_sufficient": return `medição completa com ${num(l.attempts ?? 0)} puzzles${l.games ? ` e ${num(l.games)} partidas` : ""}.`;
    case "no_recurring_error": return `nenhum erro recorrente ainda, coletando mais dados.`;
    case "target": {
      const cat = l.category ?? String(l.msg ?? "").replace(/^alvo = /, "");
      return `alvo escolhido: ${meta.dna(cat)}${l.theme ? ` (tema ${meta.theme(l.theme)})` : ""}.`;
    }
    case "assigned": {
      const key = l.intervention ?? String(l.msg ?? "").replace(/^intervenção escolhida: /, "");
      return `treino escolhido: ${meta.intervention(key)}.`;
    }
    case "practice_done": return `prática concluída${l.exercises ? ` (${num(l.exercises)} exercícios)` : ""}.`;
    case "outcome_recorded":
      return l.updated === false ? `resultado inconclusivo, poucos dados na reavaliação.`
        : l.improved ? `o erro diminuiu.` : `o erro não diminuiu.`;
    case "reassessment_reused": return "a reavaliação do ciclo anterior virou a medição deste ciclo.";
    default: return `${l.msg ?? ""}`;
  }
}

// ------------------------------------------------------------------ error DNA
function DnaTab() {
  const { d, e } = useApi("/api/cognitive/error-dna");
  const meta = useMeta();
  return (
    <Wrap d={d} e={e}>{() => (
      <>
        <Intro help="error_dna">Cada erro seu, nos puzzles e nas partidas analisadas, recebe um tipo, com regras fixas a partir do Stockfish, do tabuleiro e do seu tempo. O tipo que mais se repete é o que mais vale treinar.</Intro>
        <p className="mb-4 text-sm text-muted">Últimos {d.window_days} dias: {num(d.puzzle_attempts)} puzzles e {num(d.game_moves_analyzed)} lances de partidas analisados. Os erros recentes pesam mais.</p>
        {d.patterns.length === 0 ? (
          <Empty title="Nenhum erro classificado ainda"
            action={<><Link className="btn-primary" to="/treinar">Treinar</Link><Link className="btn" to="/partidas">Importar partidas</Link></>}>
            Resolva puzzles ou importe as suas partidas. Cada erro recebe um tipo e aparece aqui, do mais comum para o menos comum.
          </Empty>
        ) : (
          <ul className="divide-y divide-rule border-y border-rule">
            {d.patterns.map((p: any) => {
              const info = meta.error_dna[p.category];
              return (
                <li key={p.category} className="py-4">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <h3>{info?.name ?? p.category}</h3>
                    {p.recurring && <span className="chip border-bad/50 text-bad">recorrente</span>}
                    <span className="tnum ml-auto text-sm text-muted">{pct(p.share)} dos erros recentes</span>
                  </div>
                  <div className="mt-2"><Bar value={p.share} tone={p.recurring ? "bad" : "pen"} /></div>
                  <p className="mt-2 text-muted">{info?.short ? `${cap(info.short)}.` : p.label}</p>
                  <p className="mt-1 text-sm text-muted">
                    {num(p.count)} {p.count === 1 ? "erro" : "erros"}: {num(p.from_puzzles)} em puzzles e {num(p.from_games)} em partidas
                    {p.top_themes.length > 0 && <>. Temas: {p.top_themes.map((t: any) => `${meta.theme(t[0])} (${t[1]})`).join(", ")}</>}
                    {Object.keys(p.phases || {}).length > 0 && <>. Nas partidas: {Object.entries(p.phases).map(([k, v]: any) => `${meta.phases[k] ?? k} (${v})`).join(", ")}</>}.
                  </p>
                  {info && (
                    <details className="mt-2 text-sm">
                      <summary className="cursor-pointer text-pen">Como o AURA reconhece e o que fazer</summary>
                      <p className="mt-1">{info.how}</p>
                      <p className="mt-1 font-bold">{info.tip}</p>
                    </details>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <Section title="Como os erros são classificados" hint="As regras são testadas nesta ordem. A primeira que se encaixa decide o tipo do erro.">
          <ol className="list-decimal space-y-2 pl-5">
            {d.priority.map((k: string) => (
              <li key={k}><b>{meta.error_dna[k]?.name ?? k}</b>: {meta.error_dna[k]?.how}</li>
            ))}
          </ol>
          <p className="mt-3 text-sm text-faint">São pistas para o treino, tiradas do que dá para medir. O AURA não sabe o que você pensou na hora.</p>
        </Section>
      </>
    )}</Wrap>
  );
}

// ------------------------------------------------------------------ retention
function RetentionTab() {
  const { d, e } = useApi("/api/cognitive/retention");
  const meta = useMeta();
  return (
    <Wrap d={d} e={e}>{() => {
      const maxN = Math.max(1, ...d.curve.map((b: any) => b.new_positions_n));
      return (
        <>
          <Intro help="retention">Mostra se você continua acertando um tema depois de um tempo sem vê-lo. Acertar puzzles novos dias depois é o melhor sinal de que você aprendeu a ideia, e não só decorou uma posição.</Intro>
          <Section title="Acerto em puzzles novos, por tempo sem ver o tema"
            hint="Cada linha junta os puzzles resolvidos depois de um intervalo sem o tema. Puzzles repetidos ficam de fora.">
            {d.curve.every((b: any) => !b.new_positions_n) ? <p className="text-sm text-muted">Aparece quando você voltar a um tema depois de um tempo.</p> : (
              <ul className="max-w-xl space-y-3">
                {d.curve.map((b: any) => (
                  <li key={b.delay}>
                    <div className="flex justify-between gap-3 text-sm"><span>{b.delay}</span>
                      <span className="tnum">{b.new_positions_n ? <><b>{pct(b.new_positions_success)}</b> <span className="text-muted">({num(b.new_positions_n)} puzzles)</span></> : <span className="text-faint">sem dados</span>}</span></div>
                    <div className="mt-1" style={{ opacity: 0.35 + 0.65 * (b.new_positions_n / maxN) }}><Bar value={b.new_positions_success} /></div>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-sm text-faint">{d.note}</p>
          </Section>
          <Section title="Temas em revisão" hint="Cada tema volta para revisão em intervalos cada vez maiores. Quando você erra, o intervalo encolhe.">
            {d.concepts.length === 0 ? (
              <Empty title="Nenhum tema em revisão ainda" action={<Link className="btn" to="/treinar">Treinar</Link>}>
                A revisão começa sozinha quando você resolve puzzles: cada tema entra na fila com o primeiro puzzle.
              </Empty>
            ) : (
              <>
                <div className="mb-3 flex flex-wrap items-center gap-3">
                  <span>{d.due_count ? `${num(d.due_count)} ${d.due_count === 1 ? "tema está" : "temas estão"} na hora de revisar.` : "Nenhum tema na hora de revisar agora."}</span>
                  {d.due_count > 0 && <Link className="btn-primary btn-sm" to="/treinar?modo=retention">Revisar agora</Link>}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-muted"><tr>
                      <th className="py-2 font-normal">Tema</th><th className="font-normal">Próxima revisão</th>
                      <th className="text-right font-normal">Intervalo</th><th className="text-right font-normal">Puzzles novos certos</th>
                      <th className="text-right font-normal">Revisões certas</th><th className="text-right font-normal">Erros</th></tr></thead>
                    <tbody>
                      {d.concepts.map((c: any) => (
                        <tr key={c.concept} className="border-t border-rule">
                          <td className="py-2">{meta.theme(c.concept)}</td>
                          <td>{c.due ? <span className="font-bold text-warn">agora</span> : dateOnly(c.due_at)}</td>
                          <td className="tnum text-right">{String(c.interval_days).replace(".", ",")} {c.interval_days === 1 ? "dia" : "dias"}</td>
                          <td className="tnum text-right">{c.transfer.n ? `${num(c.transfer.ok)} de ${num(c.transfer.n)}` : "—"}</td>
                          <td className="tnum text-right">{num(c.reps)}</td>
                          <td className="tnum text-right">{num(c.lapses)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </Section>
        </>
      );
    }}</Wrap>
  );
}

// ------------------------------------------------------------------ fatigue
function FatigueTab() {
  const { d, e } = useApi("/api/cognitive/attention");
  const c = useColors();
  return (
    <Wrap d={d} e={e}>{() => {
      const s = d.latest;
      const ld = d.light_day;
      return (
        <>
          <Intro help="fatigue">Durante a sessão, o AURA compara o começo e o fim: o seu acerto, levando em conta a dificuldade de cada puzzle, e o seu tempo. Se os dois pioram de forma consistente, ele sugere uma pausa.</Intro>
          {!s ? (
            <Empty title="Nenhuma sessão ainda" action={<Link className="btn-primary" to="/treinar">Treinar</Link>}>
              A análise aparece a partir de 16 exercícios numa mesma sessão.
            </Empty>
          ) : (
            <>
              <Section title="Última sessão">
                <p className={`text-lg font-bold ${s.suggest_break ? "text-warn" : ""}`}>
                  {s.suggest_break ? "Queda detectada: hora de uma pausa" : s.status === "estável" ? "Estável" : `${s.status[0].toUpperCase()}${s.status.slice(1)}`}
                </p>
                <p className="text-sm text-muted">{num(s.n)} exercícios em {String(s.minutes).replace(".", ",")} min.</p>
                {s.recommendation && <p className="mt-2">{s.recommendation}</p>}
                {s.reasons?.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm">{s.reasons.map((r: string) => <li key={r}>{r[0].toUpperCase()}{r.slice(1)}.</li>)}</ul>}
                {s.early_residual != null && (
                  <dl className="mt-4 grid max-w-xl grid-cols-[auto_1fr_1fr] gap-x-6 gap-y-2 text-sm">
                    <dt />
                    <dd className="text-muted">Começo</dd>
                    <dd className="text-muted">Fim (últimos 8)</dd>
                    <dt>Acerto vs. esperado</dt>
                    <dd className="tnum font-bold">{points(s.early_residual)}</dd>
                    <dd className="tnum font-bold">{points(s.late_residual)}</dd>
                    <dt>Tempo mediano</dt>
                    <dd className="tnum font-bold">{secs(s.early_median_ms)}</dd>
                    <dd className="tnum font-bold">{secs(s.late_median_ms)}</dd>
                  </dl>
                )}
              </Section>
              {s.series.length > 1 && (
                <Section title="Cada exercício da sessão"
                  hint="Barra para cima: acertou, e quanto mais alta, mais difícil era. Barra para baixo: errou, e quanto mais funda, mais fácil era. Uma fila de barras para baixo no fim é o sinal de cansaço.">
                  <div className="h-48">
                    <ResponsiveContainer>
                      <BarChart data={s.series} margin={{ left: 0, right: 8, top: 8 }} barCategoryGap={2}>
                        <CartesianGrid stroke={c.rule} vertical={false} />
                        <XAxis dataKey="i" tick={c.axis} interval="preserveStartEnd" minTickGap={16} />
                        <YAxis tick={c.axis} width={40} domain={[-1, 1]} ticks={[-1, -0.5, 0, 0.5, 1]} tickFormatter={(v) => String(Math.round(v * 100))} />
                        <ReferenceLine y={0} stroke={c.muted} />
                        <Tooltip cursor={{ fill: c.penSoft }} content={<ChartTip
                          value={(_, r) => (r.correct ? "Acertou" : "Errou")}
                          title={(l, r) => `Exercício ${l}${r.expected != null ? `, chance esperada de acerto ${pct(r.expected)}` : ""}`} />} />
                        <RBar dataKey="residual" maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
                          {s.series.map((p: any) => <Cell key={p.i} fill={p.correct ? c.good : c.bad} />)}
                        </RBar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <h3 className="mt-6 text-sm font-normal text-muted">Tempo por exercício</h3>
                  <div className="h-40">
                    <ResponsiveContainer>
                      <LineChart data={s.series.map((p: any) => ({ ...p, s: p.total_ms == null ? null : p.total_ms / 1000 }))} margin={{ left: 0, right: 8, top: 8 }}>
                        <CartesianGrid stroke={c.rule} vertical={false} />
                        <XAxis dataKey="i" tick={c.axis} interval="preserveStartEnd" minTickGap={16} />
                        <YAxis tick={c.axis} width={40} domain={[0, "auto"]} tickFormatter={(v) => `${v.toLocaleString("pt-BR")} s`} />
                        <Tooltip cursor={{ stroke: c.rule }} content={<ChartTip value={(_, r) => secs(r.total_ms)} title={(l) => `Exercício ${l}`} />} />
                        <Line dataKey="s" stroke={c.pen} strokeWidth={2} dot={s.series.length < 3 ? { r: 4, fill: c.pen, stroke: c.sheet, strokeWidth: 2 } : false}
                          activeDot={{ r: 4, stroke: c.sheet, strokeWidth: 2 }} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <NumbersTable head={["Exercício", "Resultado", "Chance esperada", "Tempo"]}
                    rows={s.series.map((p: any) => [p.i, p.correct ? "acertou" : "errou", pct(p.expected), secs(p.total_ms)])} />
                  <p className="mt-3 text-sm text-faint">{s.disclaimer}</p>
                </Section>
              )}
            </>
          )}
          <Section title="Dia leve" hint="Recomendado quando o AURA sugeriu pausa em 2 sessões nos últimos 3 dias, ou quando o resultado desses dias ficou bem abaixo do esperado.">
            <p><b>{ld.light_day ? "Recomendado hoje" : "Não precisa hoje"}</b></p>
            <p className="mt-1 text-sm text-muted">
              Pausas sugeridas nos últimos 3 dias: {num(ld.break_flags_3d)}. Resultado desses dias: {ld.n_3d ? `${points(ld.residual_3d)} (${num(ld.n_3d)} exercícios)` : "sem exercícios"}.
            </p>
            {ld.light_day && <Link className="btn mt-3" to="/plano">Abrir o plano do dia</Link>}
          </Section>
        </>
      );
    }}</Wrap>
  );
}

// ------------------------------------------------------------------ pressure
function PressureTab() {
  const { d, e } = useApi("/api/cognitive/pressure");
  return (
    <Wrap d={d} e={e}>{() => {
      const played = Object.keys(d.by_level).length > 0;
      return (
        <>
          <Intro help="pressure">Puzzles com um relógio que encurta a cada nível, de 60 s até 12 s, e posições mais complexas. O AURA mede a qualidade das decisões separada da velocidade, para mostrar se o relógio piora as suas escolhas.</Intro>
          <div className="mb-6 flex flex-wrap items-center gap-3">
            <span>Nível atual: <b>{d.current.level}</b> de {d.levels.length}, com {d.current.seconds} s por puzzle.</span>
            <Link className="btn-primary btn-sm" to="/treinar?modo=pressure">Treinar sob pressão</Link>
          </div>
          {!played ? (
            <Empty title="Nenhum puzzle de pressão ainda">Comece pelo nível 1. Você sobe de nível quando decide bem e dentro do tempo, e desce quando o relógio vence.</Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-muted"><tr>
                  <th className="py-2 font-normal">Nível</th><th className="font-normal">Relógio</th><th className="text-right font-normal">Puzzles</th>
                  <th className="pl-4 font-normal">Decisões certas</th><th className="text-right font-normal">Tempo estourado</th>
                  <th className="text-right font-normal">Tempo usado</th><th className="text-right font-normal">Perda quando erra</th></tr></thead>
                <tbody>
                  {d.levels.map((l: any) => {
                    const r = d.by_level[l.level];
                    return (
                      <tr key={l.level} className={`border-t border-rule ${l.level === d.current.level ? "bg-pen/5" : ""}`}>
                        <td className="py-2 font-bold">{l.level}</td>
                        <td className="tnum">{l.seconds} s</td>
                        <td className="tnum text-right">{num(r?.n ?? 0)}</td>
                        <td className="pl-4">{r ? <Rate w={r.decision_quality} unit="decisões" /> : <span className="text-faint">—</span>}</td>
                        <td className="tnum text-right">{r ? pct(r.timeout_rate.rate) : "—"}</td>
                        <td className="tnum text-right">{r?.mean_time_used != null ? pct(r.mean_time_used) : "—"}</td>
                        <td className="tnum text-right">{pawns(r?.mean_cp_loss_when_wrong)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-3 max-w-prose text-sm text-faint">Tempo usado é a fração do relógio gasta nas decisões. Perda quando erra é a média do quanto o lance errado piorou a posição segundo o Stockfish, limitada a 10 peões por lance para um mate perdido não distorcer a média. {d.note}</p>
        </>
      );
    }}</Wrap>
  );
}

// ------------------------------------------------------------------ profile
function ProfileTab() {
  const { d, e } = useApi("/api/cognitive/profile");
  return (
    <Wrap d={d} e={e}>{() => (
      <>
        <Intro help="ci">Como você se sai em cada habilidade que dá para medir nos exercícios e nas partidas. Cada porcentagem vem com o intervalo de confiança: com poucos exercícios, a faixa é larga.</Intro>
        <p className="mb-2 text-sm text-muted">Base: {num(d.sample.puzzle_attempts)} exercícios e {num(d.sample.analysed_games)} partidas analisadas nos últimos {d.window_days} dias.</p>
        <div className="grid gap-x-10 md:grid-cols-2">
          <Skill title="Reconhecimento de padrões" text={d.pattern_recognition.description}>
            <Rate w={d.pattern_recognition} />
            {d.pattern_recognition.rating_adjusted_residual != null && <p className="text-sm text-muted">Levando em conta a dificuldade: {points(d.pattern_recognition.rating_adjusted_residual)}.</p>}
          </Skill>
          <Skill title="Cálculo" text={d.calculation.description}>
            <ul className="space-y-1">{Object.entries(d.calculation.by_length).map(([k, v]: any) => (
              <li key={k}>{k} {k === "1" ? "lance" : "lances"}: <Rate w={v} /></li>
            ))}</ul>
            <p className="mt-1 text-sm">Linha mais longa dominada: {d.calculation.depth_reached ? `${d.calculation.depth_reached} lances` : "ainda nenhuma (precisa de 50% de acerto em 5 puzzles)"}.</p>
            <p className="text-sm">Às cegas: <Rate w={d.calculation.blind_accuracy} /></p>
          </Skill>
          <Skill title="Detecção de ameaças" text={d.threat_detection.description}>
            <p>Puzzles de defesa: <Rate w={d.threat_detection.defensive_puzzles} /></p>
            <p className="text-sm">Nas partidas: {d.threat_detection.game_missed_threats_per_100 == null ? "sem dados" : `${String(d.threat_detection.game_missed_threats_per_100).replace(".", ",")} ameaças ignoradas a cada 100 lances`} ({num(d.threat_detection.game_moves_analysed)} lances analisados).</p>
          </Skill>
          <Skill title="Lances candidatos" text={d.candidate_generation.description} help="candidates">
            {d.candidate_generation.n ? <p><b className="tnum">{pct(d.candidate_generation.mean_score)}</b> <span className="text-sm text-muted">de nota média em {num(d.candidate_generation.n)} posições</span></p>
              : <p className="text-faint">Sem dados. <Link className="link" to="/treinar?modo=candidates">Treinar lances candidatos</Link></p>}
          </Skill>
          <Skill title="Tabuleiro visível vs. às cegas" text={d.working_memory_load.description} help="blind">
            <ul className="space-y-1">{d.working_memory_load.by_length.map((r: any) => (
              <li key={r.solution_len}>{r.solution_len} {r.solution_len === 1 ? "lance" : "lances"}: visível <Rate w={r.board} />; às cegas <Rate w={r.blind} /></li>
            ))}</ul>
          </Skill>
          <Skill title="Tempo até o primeiro lance" text="Mediana do tempo até você mexer a primeira peça.">
            <p>Quando acerta: <b className="tnum">{secs(d.decision_latency.median_correct_ms)}</b> <span className="text-sm text-muted">({num(d.decision_latency.n_correct)} puzzles)</span></p>
            <p>Quando erra: <b className="tnum">{secs(d.decision_latency.median_wrong_ms)}</b> <span className="text-sm text-muted">({num(d.decision_latency.n_wrong)} puzzles)</span></p>
          </Skill>
          <Skill title="Consistência sob pressão" text={d.time_pressure_consistency.description} help="pressure">
            <p>Com relógio: <Rate w={d.time_pressure_consistency.pressure_quality} unit="decisões" /></p>
            <p>Sem relógio: <Rate w={d.time_pressure_consistency.normal_quality} /></p>
            <p className="text-sm">Tempo estourado: {num(d.time_pressure_consistency.pressure_timeouts.timeouts)} de {num(d.time_pressure_consistency.pressure_timeouts.n)}.</p>
            <p className="text-sm">Erros nas partidas com pouco tempo no relógio: <Rate w={d.time_pressure_consistency.game_low_clock_error_rate} unit="lances" /></p>
          </Skill>
        </div>
        <p className="mt-6 text-sm text-faint">{d.disclaimer}</p>
      </>
    )}</Wrap>
  );
}

function Skill({ title, text, help, children }: { title: string; text: string; help?: string; children: ReactNode }) {
  return (
    <section className="border-t border-rule py-5">
      <h3 className="flex items-center gap-2">{title}{help && <Help id={help} />}</h3>
      <p className="mt-0.5 text-sm text-muted">{text}.</p>
      <div className="mt-2 space-y-1">{children}</div>
    </section>
  );
}

// ------------------------------------------------------------------ prediction
function PredictionTab() {
  const { d, e } = useApi("/api/cognitive/prediction");
  return (
    <Wrap d={d} e={e}>{() => (
      <>
        <Intro help="prediction">Para onde a tendência atual aponta, com uma faixa onde o próximo valor provavelmente cai. Só aparece com dados suficientes e não é uma promessa de rating.</Intro>
        <Section title="Partidas">
          {d.games.status !== "ok" ? (
            <Empty title={`Precisa de ${d.games.needed} partidas analisadas`} action={<Link className="btn" to="/partidas">Importar partidas</Link>}>
              Você tem {num(d.games.games)}. A previsão usa a precisão e as capivaradas de cada partida.
            </Empty>
          ) : (
            <div className="grid gap-8 sm:grid-cols-2">
              <Trend t={d.games.accuracy} unit={d.games.x_unit} label="Precisão da partida" fmt={(v) => String(Math.round(v))} help="game_accuracy" />
              <Trend t={d.games.blunders_per_100} unit={d.games.x_unit} label="Capivaradas a cada 100 lances" fmt={(v) => v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} lowerIsBetter />
            </div>
          )}
        </Section>
        <Section title="Rating de puzzle">
          {d.puzzle_rating.status !== "ok" ? (
            <Empty title={`Precisa de ${d.puzzle_rating.needed} dias de treino`} action={<Link className="btn" to="/treinar">Treinar</Link>}>
              Você tem {num(d.puzzle_rating.days)} {d.puzzle_rating.days === 1 ? "dia" : "dias"} com puzzles.
            </Empty>
          ) : <Trend t={d.puzzle_rating.rating} unit="day" label="Rating de puzzle" fmt={(v) => String(Math.round(v))} help="puzzle_rating" />}
        </Section>
        <p className="mt-2 max-w-prose text-sm text-faint">{d.disclaimer}</p>
      </>
    )}</Wrap>
  );
}

function Trend({ t, unit, label, fmt, help, lowerIsBetter }: { t: any; unit: string; label: string;
  fmt: (v: number) => string; help?: string; lowerIsBetter?: boolean }) {
  const per = unit === "game" ? "a cada 30 partidas" : "a cada 30 dias";
  const ahead = (h: number) => (unit === "game" ? `Daqui a ${h} partidas` : `Daqui a ${h} dias`);
  return (
    <div>
      <h3 className="flex items-center gap-2">{label}{help && <Help id={help} />}</h3>
      {t?.status !== "ok" ? <p className="mt-1 text-sm text-muted">Os valores variam pouco demais para traçar uma tendência.</p> : (
        <>
          <p className="mt-1">
            Tendência: <b className="tnum">{t.slope_per_30d > 0 ? "+" : ""}{fmt(t.slope_per_30d)}</b> {per}
            <span className="text-sm text-muted"> (IC 95% de {fmt(t.slope_per_30d_ci[0])} a {fmt(t.slope_per_30d_ci[1])})</span>
          </p>
          <p className={`text-sm ${t.direction_certain ? ((t.slope_per_30d > 0) !== !!lowerIsBetter ? "text-good" : "text-bad") : "text-muted"}`}>
            {t.direction_certain ? ((t.slope_per_30d > 0) !== !!lowerIsBetter ? "A melhora é consistente." : "A piora é consistente.") : "Ainda não dá para dizer se está subindo ou descendo."}
          </p>
          <ul className="mt-2 space-y-1 text-sm">
            {t.forecasts.map((f: any) => (
              <li key={f.days_ahead}>{ahead(f.days_ahead)}: <b className="tnum">{fmt(f.value)}</b> <span className="text-muted">(provavelmente entre {fmt(f.pi_low)} e {fmt(f.pi_high)})</span></li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ interventions
function InterventionsTab() {
  const { d, e } = useApi("/api/cognitive/interventions");
  const pr = useApi("/api/cognitive/principles");
  const meta = useMeta();
  return (
    <Wrap d={d} e={e}>{() => {
      const tested = d.effectiveness.filter((r: any) => r.trials > 0);
      return (
        <>
          <Intro>Cada ciclo testa um treino contra o seu erro alvo. O AURA conta quantas vezes cada treino funcionou com você e passa a escolher mais os que funcionam.</Intro>
          <Section title="Resultados com você" hint="Poucos ciclos e sem grupo de controle: é uma pista, não uma prova.">
            {tested.length === 0 ? <p className="text-sm text-muted">Nenhum treino foi testado até o fim ainda. O primeiro resultado sai quando você completar um ciclo.</p> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-muted"><tr><th className="py-2 font-normal">Treino</th><th className="font-normal">Erro alvo</th>
                    <th className="text-right font-normal">Ciclos</th><th className="text-right font-normal">Chance de funcionar</th><th className="text-right font-normal">Queda média do erro</th></tr></thead>
                  <tbody>
                    {tested.map((r: any) => (
                      <tr key={r.intervention + r.category} className="border-t border-rule">
                        <td className="py-2">{r.title}</td><td>{meta.dna(r.category)}</td>
                        <td className="tnum text-right">{num(r.trials)}</td>
                        <td className="tnum text-right">{pct(r.p_improves)}</td>
                        <td className="tnum text-right">{effectText(r.mean_effect)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
          <Section title="Os treinos do AURA">
            <ul className="grid gap-x-10 md:grid-cols-2">
              {d.catalog.map((i: any) => (
                <li key={i.key} className="border-t border-rule py-4">
                  <h3>{i.title}</h3>
                  <p className="text-muted">{i.description}</p>
                  <p className="mt-1 text-sm">Para: {i.targets.map((t: string) => meta.dna(t)).join(", ")}.</p>
                  {pr.d && <p className="text-sm text-faint">Princípios: {i.principles.map((p: string) => pr.d.validated_principles[p]?.name ?? p).join(", ")}.</p>}
                </li>
              ))}
            </ul>
          </Section>
        </>
      );
    }}</Wrap>
  );
}

/** Mean drop of the target error rate, in percentage points (positive = the error became rarer). */
function effectText(x: number) {
  const v = Math.round(x * 1000) / 10;
  const f = (n: number) => `${n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} ${n === 1 ? "ponto" : "pontos"}`;
  return v > 0 ? f(v) : v < 0 ? `subiu ${f(-v)}` : "nenhuma";
}

// ------------------------------------------------------------------ science
const EXPERIMENTAL: Record<string, string> = {
  error_dna: "Error DNA", intervention_effectiveness: "O que funciona", fatigue_detection: "Fadiga",
  pressure_complexity: "Complexidade no modo pressão", performance_prediction: "Previsão",
  retention_transfer_probe: "Retenção em puzzles novos",
};

function ScienceTab() {
  const { d, e } = useApi("/api/cognitive/principles");
  return (
    <Wrap d={d} e={e}>{() => (
      <>
        <Intro>Os princípios de aprendizagem em que o treino se apoia, com as referências, e o que ainda é experimental.</Intro>
        <Section title="Princípios com boa evidência" hint={d.note}>
          <ul className="grid gap-x-10 md:grid-cols-2">
            {Object.entries(d.validated_principles).map(([k, p]: any) => (
              <li key={k} className="border-t border-rule py-4">
                <h3>{p.name}</h3>
                <p className="text-muted">{p.summary}</p>
                <p className="mt-1 text-sm">No AURA: {p.used_by.join("; ")}.</p>
                <ul className="mt-1 text-xs text-faint">{p.references.map((r: string) => <li key={r}>{r}</li>)}</ul>
              </li>
            ))}
          </ul>
        </Section>
        <Section title="Experimental" hint="Funciona com regras e estatística simples sobre os seus dados. Útil para orientar o treino, mas sem validação científica própria.">
          <ul className="space-y-3">
            {Object.entries(d.experimental_features).map(([k, v]: any) => (
              <li key={k}><b>{EXPERIMENTAL[k] ?? k}</b>: <span className="text-muted">{v}</span></li>
            ))}
          </ul>
        </Section>
      </>
    )}</Wrap>
  );
}
