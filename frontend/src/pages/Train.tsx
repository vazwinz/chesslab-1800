import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import AnalysisBoard from "../components/AnalysisBoard";
import Board, { Badge, Hesitation } from "../components/Board";
import Explain from "../components/Explain";
import Help from "../components/Help";
import { Empty, ErrorNote, PageHeader, SanText, Spinner } from "../components/ui";
import { nextStep, stepFor, useRoutine } from "../lib/routine";
import { api } from "../lib/api";
import { tryMove, walk } from "../lib/chess";
import { clock, num } from "../lib/format";
import { LOOP_PHASE, MODE_LABEL, SESSION_KINDS, TRAIN_MODES as MODES, useMeta } from "../lib/meta";
import { usePrefs } from "../lib/prefs";
import { moveSound, play } from "../lib/sound";
import { Exercise, useTrain } from "../lib/trainStore";


export default function Train() {
  const st = useTrain();
  const [params, setParams] = useSearchParams();
  const [err, setErr] = useState<string | null>(null);
  const [puzzleCount, setPuzzleCount] = useState<number | null>(null);
  const [loop, setLoop] = useState<any>(null);
  const [theme, setTheme] = useState("forks");
  const meta = useMeta();
  const nav = useNavigate();

  useEffect(() => {
    api.get("/api/puzzles/stats").then((s) => setPuzzleCount(s.count)).catch(() => {});
    api.get("/api/cognitive/loop").then(setLoop).catch(() => {});
  }, []);

  const start = useCallback(async (kind: string, themeKey?: string) => {
    setErr(null);
    try {
      const s = await api.post("/api/sessions", { kind, theme: kind === "theme" ? themeKey : undefined });
      useTrain.getState().set({ session: { id: s.id, kind, theme: s.theme }, ex: null, result: null, ribbon: [], fen: "" });
    } catch (e: any) {
      setErr(e.message);
    }
  }, []);

  // "?modo=loop" from another screen: start that mode, or switch to it if another session is open
  useEffect(() => {
    const m = params.get("modo");
    if (!m || puzzleCount == null) return;
    setParams({}, { replace: true });
    if (st.session?.kind === m) return;
    if (!puzzleCount && m !== "own_mistakes") return;
    void (async () => {
      if (st.session) {
        await api.post(`/api/sessions/${st.session.id}/end`).catch(() => {});
        useTrain.getState().reset();
      }
      await start(m);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, puzzleCount]);

  if (st.session) return <Session />;

  const phase = loop?.phase;
  return (
    <div>
      <PageHeader title="Treinar" help="loop"
        purpose="Escolha um modo. Se não souber qual, use o treino em ciclo: ele mede você, acha o seu erro mais recorrente e treina exatamente isso." />
      {err && <div className="mb-4"><ErrorNote>{err}</ErrorNote></div>}
      {puzzleCount === 0 && (
        <div className="mb-6">
          <Empty title="Ainda não há puzzles no banco"
            action={<button className="btn-primary" onClick={() => nav("/configuracoes")}>Baixar puzzles do Lichess</button>}>
            O download leva alguns minutos. Dá para treinar com os seus erros de partida enquanto isso.
          </Empty>
        </div>
      )}
      <section className="panel mb-8 flex flex-wrap items-center gap-x-8 gap-y-4 p-5 sm:p-6">
        <div className="min-w-[16rem] flex-1">
          <h2 className="text-xl">Treino em ciclo</h2>
          <p className="mt-1 max-w-prose text-muted">Medir, diagnosticar, praticar o seu erro mais comum e medir de novo. O ciclo guarda o progresso entre os dias.</p>
          {loop && (
            <p className="mt-2 text-sm">
              Fase atual: <b>{LOOP_PHASE[phase] ?? phase}</b>
              {phase === "measure" && ` (${loop.baseline.attempts ?? 0} de ${loop.baseline.needed} puzzles de medição)`}
              {phase === "practice" && loop.assignment && ` — ${meta.intervention(loop.assignment.intervention)} para ${meta.dna(loop.assignment.category)}: ${loop.assignment.done} de ${loop.assignment.target}`}
              {phase === "reassess" && ` (${loop.reassessment.done ?? 0} de ${loop.reassessment.needed})`}
            </p>
          )}
        </div>
        <button className="btn-primary px-6" onClick={() => start("loop")} disabled={!puzzleCount}>
          {phase && phase !== "measure" ? "Continuar o ciclo" : "Começar o ciclo"}
        </button>
      </section>

      <h2 className="mb-3">Outros modos</h2>
      <ul className="divide-y divide-rule border-y border-rule">
        {MODES.map((m) => (
          <li key={m.kind} className="flex flex-wrap items-center gap-3 py-4">
            <div className="min-w-[14rem] flex-1">
              <div className="flex items-center gap-2 font-bold">{SESSION_KINDS[m.kind]}{m.help && <Help id={m.help} />}</div>
              <p className="max-w-prose text-sm text-muted">{m.when}</p>
            </div>
            {m.kind === "theme" && (
              <select className="input w-auto" value={theme} onChange={(e) => setTheme(e.target.value)} aria-label="Tema">
                {Object.entries(meta.categories).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            )}
            <button className="btn" onClick={() => start(m.kind, theme)} disabled={!puzzleCount && m.kind !== "own_mistakes"}>Começar</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ the session */
/** Milliseconds since the exercise was shown. The clock starts after the opponent's move has been
 *  played on the board, so an answer given before that counts as 0, never as a negative time
 *  (which the server refuses). */
const sinceServed = (servedAt: number) => Math.max(0, Math.round(Date.now() - servedAt));

function Session() {
  const st = useTrain();
  const { session, ex, fen, lastMove, result, servedAt, ribbon } = st;
  const { prefs } = usePrefs();
  const meta = useMeta();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const [badges, setBadges] = useState<Badge[]>([]);
  const [line, setLine] = useState("");
  const [cands, setCands] = useState("");
  const [view, setView] = useState<"play" | "analysis">("play");
  const [step, setStep] = useState<number | null>(null); // solution viewer
  const [explain, setExplain] = useState(false);
  const [preview, setPreview] = useState<{ fen: string; lastMove: [string, string] | null } | null>(null);
  const hes = useRef<Hesitation>({ selection_changes: 0, cancelled_drags: 0, piece_selections: 0 });
  const seq = useRef(0);
  const set = st.set;
  const { routine, reload: reloadRoutine } = useRoutine();

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  const next = useCallback(async () => {
    if (!session || busy) return;
    const my = ++seq.current;
    setBusy(true);
    setErr(null);
    setBadges([]);
    setLine("");
    setCands("");
    setStep(null);
    setExplain(false);
    setPreview(null);
    setView("play");
    try {
      const e: Exercise = await api.post(`/api/sessions/${session.id}/next`);
      if (my !== seq.current) return;
      hes.current = { selection_changes: 0, cancelled_drags: 0, piece_selections: 0 };
      if (e.opponent_move) {
        set({ ex: e, result: null, fen: e.initial_fen, lastMove: null, servedAt: Date.now() + 10_000, candsDone: false });
        window.setTimeout(() => {
          if (my !== seq.current) return;
          const r = tryMove(e.initial_fen, e.opponent_move!);
          moveSound(r?.move);
          set({ fen: e.fen, lastMove: [e.opponent_move!.slice(0, 2), e.opponent_move!.slice(2, 4)],
            servedAt: Date.now() + prefs.animation_ms });
        }, 280);
      } else {
        play("start");
        set({ ex: e, result: null, fen: e.fen, lastMove: null, servedAt: Date.now(), candsDone: false });
      }
    } catch (e: any) {
      if (my === seq.current) {
        set({ ex: null });
        setErr(e.message);
      }
    } finally {
      if (my === seq.current) setBusy(false);
    }
  }, [session, busy, set, prefs.animation_ms]);

  useEffect(() => {
    if (session && !ex && !err) void next();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.id]);

  const elapsed = ex && !result ? Math.max(0, now - servedAt) : 0;
  const locked = !!ex?.min_think_ms && !result && elapsed < ex.min_think_ms;
  const remaining = ex?.time_limit_ms && !result ? ex.time_limit_ms - elapsed : null;

  const finish = useCallback((r: any, square?: string) => {
    set({ result: r, ribbon: [...useTrain.getState().ribbon, r.correct ? "ok" : r.timed_out ? "time" : "bad"] });
    if (square) setBadges([{ square, kind: r.correct ? "good" : "bad" }]);
    play(r.correct ? "correct" : "wrong");
    void reloadRoutine();
    if (r.correct && prefs.auto_next) window.setTimeout(() => void nextRef.current(), 1100);
  }, [set, prefs.auto_next, reloadRoutine]);
  const nextRef = useRef(next);
  nextRef.current = next;

  const giveUp = useCallback(async (timedOut = false) => {
    if (!ex || result || busy) return;
    setBusy(true);
    try {
      const r = await api.post(`/api/attempts/${ex.attempt_id}/give-up`, { timed_out: timedOut,
        elapsed_ms: sinceServed(servedAt), hesitation: hes.current });
      finish(r);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }, [ex, result, busy, servedAt, finish]);

  useEffect(() => {
    if (remaining != null && remaining <= 0 && !busy) void giveUp(true);
  }, [remaining, busy, giveUp]);

  function onMove(uci: string) {
    if (!ex || result || busy || locked || (ex.candidates && !st.candsDone) || ex.blind) return false;
    const r = tryMove(fen, uci);
    if (!r) return false;
    moveSound(r.move);
    const before = fen;
    set({ fen: r.fen, lastMove: [uci.slice(0, 2), uci.slice(2, 4)] });
    void send(uci, before);
    return true;
  }

  async function send(uci: string, before: string) {
    if (!ex) return;
    setBusy(true);
    try {
      const r = await api.post(`/api/attempts/${ex.attempt_id}/move`, {
        uci, elapsed_ms: sinceServed(servedAt), hesitation: hes.current });
      if (r.locked) {
        set({ fen: before });
        setErr(`Pense primeiro: o tabuleiro libera em ${Math.ceil(r.remaining_ms / 1000)} s.`);
        return;
      }
      if (r.legal === false) {
        set({ fen: before });
        return;
      }
      if (!r.finished) {
        setBadges([{ square: uci.slice(2, 4), kind: "good" }]);
        window.setTimeout(() => {
          const rr = tryMove(useTrain.getState().fen, r.reply);
          moveSound(rr?.move);
          set({ fen: r.fen, lastMove: [r.reply.slice(0, 2), r.reply.slice(2, 4)] });
          setBadges([]);
        }, 320);
      } else finish(r, uci.slice(2, 4));
    } catch (e: any) {
      set({ fen: before });
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitLine() {
    if (!ex) return;
    setBusy(true);
    try {
      const moves = line.replace(/\d+\.(\.\.)?/g, " ").split(/[\s,]+/).filter(Boolean);
      const t = sinceServed(servedAt);
      finish(await api.post(`/api/attempts/${ex.attempt_id}/line`, { moves, elapsed_ms: t, first_move_ms: t, hesitation: hes.current }));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitCands() {
    if (!ex) return;
    try {
      await api.post(`/api/attempts/${ex.attempt_id}/candidates`, { moves: cands.split(/[\s,]+/).filter(Boolean) });
      set({ candsDone: true });
      setErr(null);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function end() {
    if (session) await api.post(`/api/sessions/${session.id}/end`).catch(() => {});
    st.reset();
  }

  // solution viewer
  const solution = useMemo(() => (result?.start_fen && result.solution_uci ? walk(result.start_fen, result.solution_uci) : []), [result]);
  const showStep = (i: number | null) => {
    setPreview(null);
    if (i == null || !solution.length) return setStep(null);
    const k = Math.max(-1, Math.min(solution.length - 1, i));
    if (k >= 0 && (step == null || k > step)) moveSound({ san: solution[k].san, flags: solution[k].flags });
    setStep(k);
  };
  const shown = preview ?? (step != null && result
    ? step < 0 ? { fen: result.start_fen, lastMove: null } : { fen: solution[step].fen, lastMove: solution[step].lastMove }
    : null);

  // keyboard: Enter/Espaço próximo · E explicar · A analisar · ← → solução · Esc voltar
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea, select, [role=dialog]")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return; // Ctrl+A selects text, it doesn't open the analysis
      if (view === "analysis") {
        if (e.key === "Escape") setView("play");
        return;
      }
      if (!result) return;
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); void next(); }
      if (e.key === "e" || e.key === "E") setExplain(true);
      if (e.key === "a" || e.key === "A") setView("analysis");
      if (e.key === "ArrowRight") { e.preventDefault(); showStep(step == null ? 0 : step + 1); }
      if (e.key === "ArrowLeft") { e.preventDefault(); showStep(step == null ? -1 : step - 1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!session) return null;
  const sessionTitle = SESSION_KINDS[session.kind] ?? session.kind;
  const rStep = stepFor(routine, session.kind);
  const rNext = nextStep(routine);

  if (view === "analysis" && result) {
    const played: string[] = [];
    return (
      <div>
        <AnalysisBoard startFen={result.start_fen ?? ex?.fen ?? fen} initialMoves={played} orientation={ex?.solver_color}
          header={<>
            <button className="btn" onClick={() => setView("play")}>Voltar ao puzzle</button>
            <button className="btn-primary" onClick={() => void next()}>Próximo puzzle</button>
            <span className="text-sm text-muted">Analisando a posição do puzzle. Mexa as peças à vontade: nada aqui conta no seu rating.</span>
          </>} />
      </div>
    );
  }

  const ratingDelta = result?.rating ? result.rating.after - result.rating.before : 0;
  const severityTone = result ? (result.correct ? "text-good" : "text-bad") : "";
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,400px)]">
      {/* the board stays in view while the result and the explanation scroll past it */}
      <div className="min-w-0 lg:sticky lg:top-6 lg:self-start">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h1 className="text-xl">{sessionTitle}</h1>
          {ex?.loop_phase && <span className="chip border-pen/40 text-pen">ciclo: {LOOP_PHASE[ex.loop_phase] ?? ex.loop_phase}</span>}
          {ex && ex.mode !== "standard" && <span className="chip">{MODE_LABEL[ex.mode] ?? ex.mode}</span>}
          {ex?.pressure_level && <span className="chip">nível {ex.pressure_level}</span>}
          {ex?.concept && <span className="chip">{meta.theme(ex.concept)}</span>}
          {rStep && (
            <span className={`chip ${rStep.completed ? "border-good/50 text-good" : "border-pen/40 text-pen"}`}>
              rotina: {Math.min(rStep.done, rStep.target)}/{rStep.target}{rStep.completed ? " ✓" : ""}
            </span>
          )}
          <button className="btn-quiet btn-sm ml-auto" onClick={end}>Encerrar sessão</button>
        </div>
        <div className="relative">
          {fen ? (
            <Board fen={shown?.fen ?? fen} orientation={ex?.solver_color ?? "white"} onMove={onMove}
              interactive={!!ex && !result && !busy && !locked && !(ex.candidates && !st.candsDone) && !ex.blind && !shown}
              lastMove={shown ? shown.lastMove : lastMove} badges={shown ? [] : badges}
              onHesitation={(h) => (hes.current = h)} reserve={170} id="train" />
          ) : (
            <div className="flex aspect-square max-h-[70vh] w-full items-center justify-center rounded-md border border-rule">
              {err ? <span className="max-w-xs text-center text-muted">{err}</span> : <Spinner label="Carregando o puzzle…" />}
            </div>
          )}
          {locked && (
            <div className="pointer-events-none absolute inset-x-0 top-3 z-30 mx-auto w-fit max-w-[90%] rounded-full bg-ink/85 px-4 py-2 text-sm font-bold text-paper shadow-lg">
              Pense primeiro: xeques, capturas e ameaças. Libera em {Math.ceil(((ex?.min_think_ms ?? 0) - elapsed) / 1000)} s
            </div>
          )}
        </div>
        {ribbon.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1" aria-label={`Resultados da sessão: ${ribbon.filter((r) => r === "ok").length} de ${ribbon.length}`}>
            {ribbon.slice(-40).map((r, i) => (
              <span key={i} title={r === "ok" ? "acerto" : r === "time" ? "tempo esgotado" : "erro"}
                className={`ribbon-in h-3.5 w-3.5 rounded-[3px] ${r === "ok" ? "bg-good" : r === "time" ? "border-2 border-warn" : "border-2 border-bad"}`} />
            ))}
            <span className="tnum ml-2 text-sm text-muted">{ribbon.filter((r) => r === "ok").length}/{ribbon.length}</span>
          </div>
        )}
      </div>

      <aside className="min-w-0 space-y-5">
        {err && <ErrorNote>{err}{!ex && <button className="link ml-2" onClick={() => void next()}>Tentar de novo</button>}</ErrorNote>}
        {ex && !result && (
          <div className="space-y-4">
            <div>
              <p className="text-lg font-bold">{ex.solver_color === "white" ? "Brancas jogam" : "Pretas jogam"}</p>
              {ex.prompt ? <p className="text-muted">{ex.prompt}</p> : (
                <p className="text-muted">
                  {ex.opponent_san && <>O adversário jogou <b className="text-ink"><SanText san={ex.opponent_san} /></b>. </>}
                  Ache a melhor continuação ({ex.solution_len === 1 ? "1 lance" : `${ex.solution_len} lances seus`}).
                </p>
              )}
            </div>
            <div className="flex items-end gap-8">
              <div><div className="text-sm text-muted">Tempo</div><div className="stat">{clock(elapsed)}</div></div>
              {remaining != null && (
                <div><div className="text-sm text-muted">Relógio</div><div className={`stat ${remaining < 10000 ? "text-bad" : ""}`}>{clock(remaining)}</div></div>
              )}
              {ex.rating && ex.mode !== "assessment" && <div><div className="text-sm text-muted">Puzzle</div><div className="stat text-muted">{ex.rating}</div></div>}
            </div>
            {ex.candidates && !st.candsDone && (
              <div className="space-y-2">
                <label className="label flex items-center gap-2">Seus lances candidatos (até 3) <Help id="candidates" /></label>
                <input className="input" placeholder="ex.: Cxf7 Dh5 Td1  (ou Nxf7 Qh5 Rd1)" value={cands} onChange={(e) => setCands(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submitCands()} />
                <button className="btn-primary" onClick={submitCands} disabled={!cands.trim()}>Confirmar candidatos</button>
              </div>
            )}
            {ex.blind && (
              <div className="space-y-2">
                <label className="label flex items-center gap-2">Escreva só os seus lances, em ordem <Help id="blind" /></label>
                <textarea className="input h-24" placeholder="ex.: Dxh7+ Th3+ …  (letras em inglês também valem: Qxh7+ Rh3+)" value={line}
                  onChange={(e) => setLine(e.target.value)} />
                <button className="btn-primary" onClick={submitLine} disabled={!line.trim() || busy}>Enviar a linha</button>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <button className="btn" onClick={() => giveUp(false)} disabled={busy}>Ver solução</button>
            </div>
          </div>
        )}

        {result && (
          <div className="space-y-5">
            <div>
              <p className={`text-xl font-bold ${severityTone}`}>
                {result.correct ? "Correto" : result.timed_out ? "O tempo acabou" : "Não foi o melhor lance"}
              </p>
              {result.rating && (
                <p className="tnum text-muted">
                  Rating de puzzle {num(result.rating.before)} → <b className={ratingDelta >= 0 ? "text-good" : "text-bad"}>{num(result.rating.after)}</b>
                  {" "}({ratingDelta >= 0 ? "+" : ""}{ratingDelta})
                </p>
              )}
              {result.best_san && <p className="mt-1">Melhor: <b><SanText san={result.best_san} /></b>. Na partida você jogou <SanText san={result.your_game_move} />.</p>}
            </div>
            {rStep?.completed && (
              <div className="rounded-lg border border-good/40 bg-good/10 px-4 py-3">
                <p className="font-bold text-good">Passo da rotina feito: {rStep.title}.</p>
                {rNext ? (
                  <Link className="btn-primary mt-2" to={rNext.to}>Próximo passo: {rNext.title}</Link>
                ) : <p className="text-sm text-muted">A rotina de hoje está feita. Pode continuar treinando: tudo conta.</p>}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <button className="btn-primary" onClick={() => void next()} disabled={busy}>Próximo puzzle <span className="kbd ml-1 border-pen-ink/30 bg-transparent text-pen-ink/80">Enter</span></button>
              <button className="btn" onClick={() => setExplain(true)} disabled={explain}>Explicar <span className="kbd">E</span></button>
              <button className="btn" onClick={() => setView("analysis")}>Analisar posição <span className="kbd">A</span></button>
            </div>

            {solution.length > 0 && (
              <div>
                <div className="mb-1 flex items-center gap-2 text-sm text-muted">Solução <span className="text-faint">(clique ou use ← →)</span></div>
                <div className="flex flex-wrap gap-1">
                  <button className={`move border border-rule ${step === -1 ? "bg-pen/15" : ""}`} onClick={() => showStep(-1)}>início</button>
                  {solution.map((m, i) => (
                    <button key={i} className={`move border ${step === i ? "border-pen bg-pen/15" : "border-rule"} ${i % 2 ? "text-muted" : ""}`} onClick={() => showStep(i)}>
                      <SanText san={m.san} />
                    </button>
                  ))}
                  {step != null && <button className="link ml-2 text-sm" onClick={() => showStep(null)}>voltar ao tabuleiro</button>}
                </div>
              </div>
            )}

            {result.error_dna && (
              <div className="border-l-4 border-bad/60 pl-3">
                <div className="flex items-center gap-2 font-bold">Error DNA: {meta.dna(result.error_dna.category)} <Help id="error_dna" /></div>
                <p className="text-sm text-muted">{meta.error_dna[result.error_dna.category]?.short}</p>
              </div>
            )}
            {result.explanation?.length > 0 && !explain && (
              <ul className="max-w-prose list-disc space-y-1 pl-5 text-sm text-muted">{result.explanation.map((e: string) => <li key={e}>{e}</li>)}</ul>
            )}
            {result.break && (
              <div className="rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm">
                <p className="font-bold">Hora de uma pausa <Help id="fatigue" /></p>
                <p>{result.break.recommendation}</p>
                <p className="mt-1 text-muted">{result.break.reasons.join("; ")}.</p>
              </div>
            )}
            <dl className="grid grid-cols-2 gap-3 text-sm">
              {result.retention && <div><dt className="text-muted">Próxima revisão do tema</dt><dd>{meta.theme(result.retention.concept)}: {reviewIn(result.retention.next_review_in_days)}</dd></div>}
              {result.intervention && <div><dt className="text-muted">Intervenção</dt><dd className="tnum">{result.intervention.done} de {result.intervention.target}</dd></div>}
              {result.band_change && <div><dt className="text-muted">Dificuldade</dt><dd>{result.band_change.to > result.band_change.from ? "subiu de faixa" : "desceu de faixa"} <Help id="bands" /></dd></div>}
              {result.candidates && <div><dt className="text-muted">Candidatos</dt><dd>nota {String(result.candidates.score).replace(".", ",")}</dd></div>}
              {result.game_url && <div className="col-span-2"><a className="link" href={result.game_url} target="_blank" rel="noreferrer">Ver a partida de origem no Lichess</a></div>}
            </dl>

            {explain && (
              <div className="hair pt-4">
                <Explain autoLoad request={{ attempt_id: result.attempt_id }}
                  onPreview={(f, lm) => { setStep(null); setPreview({ fen: f, lastMove: lm }); }} />
                {preview && <button className="link mt-2 text-sm" onClick={() => setPreview(null)}>voltar ao tabuleiro</button>}
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

/** Days until the next spaced review, in words. */
function reviewIn(days: number) {
  if (days < 0.75) return "ainda hoje";
  if (days < 1.5) return "amanhã";
  const d = Math.round(days);
  return d < 30 ? `em ${d} dias` : `em ${Math.round(d / 7)} semanas`;
}
