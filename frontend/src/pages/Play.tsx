import { Chess } from "chess.js";
import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import BlunderAlarm from "../components/BlunderAlarm";
import Board, { Badge } from "../components/Board";
import EvalBar from "../components/EvalBar";
import Icon from "../components/Icon";
import MoveList, { ListMove } from "../components/MoveList";
import { ErrorNote, PageHeader, SanText, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { moveArrow } from "../lib/arrows";
import { START_FEN, tryMove } from "../lib/chess";
import { dateOnly } from "../lib/format";
import { useMeta } from "../lib/meta";
import { Judgment, PlayGame, PlayResult, usePlay } from "../lib/playStore";
import { usePrefs } from "../lib/prefs";
import { RoutineDay, stepFor, useRoutine } from "../lib/routine";
import { moveSound, play } from "../lib/sound";

type Level = { elo: number; name: string };
type Color = "white" | "black";
/** Where a game starts. `practice`: not an even start (an endgame, one of your mistakes, a FEN),
 *  so the result does not move your level. */
type StartChoice = { fen: string; label: string; opening: string | null; color: Color | null; practice: boolean };
type StartKind = "initial" | "opening" | "repertoire" | "endgame" | "mistake" | "fen";

const CLOCKS: Record<string, { base: number; inc: number } | null> = {
  none: null, "5+3": { base: 300, inc: 3 }, "10+5": { base: 600, inc: 5 }, "15+10": { base: 900, inc: 10 }, "30+0": { base: 1800, inc: 0 },
};
const VERDICT: Record<string, { label: string; tone: string }> = {
  best: { label: "Melhor lance", tone: "text-good" },
  good: { label: "Bom lance", tone: "text-good" },
  inaccuracy: { label: "Imprecisão", tone: "text-warn" },
  mistake: { label: "Erro", tone: "text-bad" },
  blunder: { label: "Capivarada", tone: "text-bad" },
};

function gameFrom(startFen: string, moves: string[]): Chess {
  const g = new Chess(startFen);
  for (const u of moves) g.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u[4] || undefined });
  return g;
}

function outcome(g: Chess): PlayResult | null {
  if (g.isCheckmate()) return { result: g.turn() === "w" ? "0-1" : "1-0", reason: "xeque-mate" };
  if (g.isStalemate()) return { result: "1/2-1/2", reason: "afogamento" };
  if (g.isInsufficientMaterial()) return { result: "1/2-1/2", reason: "material insuficiente" };
  if (g.isThreefoldRepetition()) return { result: "1/2-1/2", reason: "repetição tripla" };
  if (g.isDraw()) return { result: "1/2-1/2", reason: "regra dos 50 lances" };
  return null;
}

const nameFor = (elo: number, levels: Level[]) => levels.reduce((n, l) => (elo >= l.elo ? l.name : n), levels[0]?.name ?? "");
const clockText = (ms: number) => {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
const userScore = (result: string, color: Color) => (result === "1/2-1/2" ? 0.5 : (result === "1-0") === (color === "white") ? 1 : 0);
/** Centipawns (White's view) to what the evaluation bar takes: mate scores come as 10000 - moves. */
const evalParts = (cp: number | null) =>
  cp == null ? { cp: null, mate: null }
    : Math.abs(cp) >= 9000 ? { cp: null, mate: Math.sign(cp) * Math.max(1, 10000 - Math.abs(cp)) } : { cp, mate: null };

export default function Play() {
  const game = usePlay((s) => s.game);
  const setGame = usePlay((s) => s.setGame);
  const { prefs } = usePrefs();
  const [params, setParams] = useSearchParams();
  const [st, setSt] = useState<any>(null);
  const [starts, setStarts] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  const { routine, reload: reloadRoutine } = useRoutine();
  const reloadState = useCallback(() => {
    api.get("/api/play/state").then(setSt).catch((e) => setErr(e.message));
    void reloadRoutine();
  }, [reloadRoutine]);
  useEffect(() => {
    reloadState();
    api.get("/api/play/starts").then(setStarts).catch(() => setStarts({ openings: [], repertoire: [], endgames: [], mistakes: [] }));
  }, [reloadState]);

  const levels: Level[] = st?.levels ?? [];
  const begin = useCallback((s: StartChoice, colorOverride?: Color, levelOverride?: number) => {
    let g0: Chess;
    try {
      g0 = new Chess(s.fen);
    } catch {
      setErr("Essa posição (FEN) é inválida.");
      return;
    }
    if (outcome(g0)) {
      setErr("Essa posição já terminou: escolha outra.");
      return;
    }
    const pick: Color = prefs.play_color === "random" ? (Math.random() < 0.5 ? "white" : "black") : prefs.play_color;
    const userColor = colorOverride ?? s.color ?? pick;
    const level = levelOverride ?? (prefs.play_auto_level ? st?.suggested_level ?? 800 : prefs.play_level);
    const clock = CLOCKS[prefs.play_clock] ?? null;
    const g: PlayGame = {
      id: Date.now(), startFen: g0.fen(), startLabel: s.label, opening: s.opening, practice: s.practice, moves: [],
      userColor, level, levelName: nameFor(level, levels), clock, timeLeftMs: clock ? clock.base * 1000 : null,
      turnStartedAt: Date.now(), hintsLeft: prefs.play_hints, helped: false,
      judgments: [], streak: 0, bestStreak: 0, engineEval: null, over: null,
    };
    setErr(null);
    setGame(g);
    if (window.location.search) setParams({}, { replace: true }); // the position from the link is used up
    play("start");
    window.scrollTo(0, 0);
  }, [prefs, st, levels, setGame, setParams]);

  // /jogar?fen=…&cor=…&rotulo=…&auto=1 comes from the game review and the analysis board: the game
  // starts right away, once, on arrival. A game in progress is never thrown away for it: the note
  // below says so and the position waits in "Nova partida".
  const urlFen = params.get("fen");
  const urlColor: Color | null = params.get("cor") === "black" ? "black" : params.get("cor") === "white" ? "white" : null;
  const urlStart: StartChoice | null = urlFen
    ? { fen: urlFen, label: params.get("rotulo") || "Posição escolhida", opening: null, color: urlColor, practice: true } : null;
  const waiting = !!urlStart && params.get("auto") === "1" && !!game && !game.over;
  const arrival = useRef(false);
  useEffect(() => {
    if (arrival.current || !st) return;
    arrival.current = true;
    if (!urlStart || params.get("auto") !== "1") return;
    const cur = usePlay.getState().game;
    if (!cur || cur.over) begin(urlStart);
  }, [urlFen, st]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <PageHeader title="Jogar"
        purpose="Uma partida contra o computador num nível que acompanha você. Cada lance seu é conferido na hora; os erros acendem o vermelhão e viram revisão e treino." />
      {err && <div className="mb-4"><ErrorNote>{err}</ErrorNote></div>}
      {waiting && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-rule bg-sunk px-3 py-2 text-sm">
          <span>Você tem uma partida em andamento. Termine ou abandone ela; depois a posição que você escolheu fica pronta em <b>Nova partida</b>.</span>
          <button className="btn-quiet btn-sm ml-auto" onClick={() => setParams({}, { replace: true })}>Esquecer a posição</button>
        </div>
      )}
      {game ? (
        <GameView key={game.id} levels={levels} onAgain={begin} onNew={() => setGame(null)} refreshState={reloadState} routine={routine} />
      ) : (
        <Setup st={st} starts={starts} levels={levels} onStart={begin} initial={urlStart} routine={routine} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ setup */
function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[];
  onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={value === o.value ? "btn-primary btn-sm" : "btn btn-sm"}>{o.label}</button>
      ))}
    </div>
  );
}

function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="label mb-0">{label}</div>
      {children}
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

function Check({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm">
      <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--pen))]" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {children}
    </label>
  );
}

function Setup({ st, starts, levels, onStart, initial, routine }: { st: any; starts: any; levels: Level[];
  onStart: (s: StartChoice) => void; initial: StartChoice | null; routine: RoutineDay | null }) {
  const { prefs, set } = usePrefs();
  const meta = useMeta();
  const [kind, setKind] = useState<StartKind>(initial ? "fen" : "initial");
  const [openingId, setOpeningId] = useState("italiana");
  const [repId, setRepId] = useState("");
  const [endId, setEndId] = useState("");
  const [mistakeId, setMistakeId] = useState<number | null>(null);
  const [fenIn, setFenIn] = useState(initial?.fen ?? "");
  const [lvl, setLvl] = useState(prefs.play_level);
  useEffect(() => setLvl(prefs.play_level), [prefs.play_level]);

  const kinds: { value: StartKind; label: string }[] = [
    { value: "initial", label: "Início" }, { value: "opening", label: "Abertura" },
    ...(starts?.repertoire?.length ? [{ value: "repertoire" as StartKind, label: "Seu repertório" }] : []),
    { value: "endgame", label: "Final" },
    ...(starts?.mistakes?.length ? [{ value: "mistake" as StartKind, label: "Seus erros" }] : []),
    { value: "fen", label: "FEN" },
  ];
  const choice: StartChoice | { error: string } = useMemo(() => {
    if (kind === "initial") return { fen: START_FEN, label: "Posição inicial", opening: null, color: null, practice: false };
    if (kind === "opening") {
      const o = starts?.openings?.find((x: any) => x.id === openingId) ?? starts?.openings?.[0];
      return o ? { fen: o.fen, label: o.name, opening: o.name, color: null, practice: false } : { error: "Carregando…" };
    }
    if (kind === "repertoire") {
      const r = starts?.repertoire?.find((x: any) => x.id === repId) ?? starts?.repertoire?.[0];
      return r ? { fen: r.fen, label: r.name, opening: r.name, color: r.color, practice: false } : { error: "Nenhuma linha no repertório." };
    }
    if (kind === "endgame") {
      const e = starts?.endgames?.find((x: any) => x.id === endId) ?? starts?.endgames?.[0];
      if (!e) return { error: "Carregando…" };
      return { fen: e.fen, label: `Final: ${e.name}`, opening: null, color: e.fen.split(" ")[1] === "w" ? "white" : "black", practice: true };
    }
    if (kind === "mistake") {
      const m = starts?.mistakes?.find((x: any) => x.id === mistakeId);
      return m ? { fen: m.fen, label: `Antes do seu erro contra ${m.opponent}`, opening: null, color: m.color, practice: true }
        : { error: "Escolha um dos seus erros na lista." };
    }
    try {
      const g = new Chess(fenIn.trim());
      const same = !!initial && fenIn === initial.fen;
      return { fen: g.fen(), label: same ? initial!.label : "Posição colada (FEN)", opening: null,
        color: same ? initial!.color : null, practice: true };
    } catch {
      return { error: fenIn.trim() ? "FEN inválido." : "Cole um FEN." };
    }
  }, [kind, openingId, repId, endId, mistakeId, fenIn, starts, initial]);

  const auto = prefs.play_auto_level;
  const ok = !("error" in choice);
  const gamesStep = stepFor(routine, "games");
  const before = routine?.steps.find((s) => s.key !== "games" && !s.completed) ?? null;
  const forcedColor = "error" in choice ? null : choice.color;
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section className="panel space-y-6 p-5 sm:p-6">
        <h2 className="text-xl">Nova partida</h2>
        {gamesStep && (
          <p className="rounded-lg bg-sunk px-3 py-2 text-sm">
            {gamesStep.completed ? "As partidas da rotina de hoje estão feitas. Jogar mais continua valendo para o seu nível."
              : <>Rotina de hoje: partida <b>{gamesStep.done + 1} de {gamesStep.target}</b>. Contam as que começam do início, de uma abertura ou do repertório.
                {before && <> A rotina deixa as partidas para o fim: ainda falta <Link className="link" to={before.to}>{before.title}</Link>.</>}</>}
          </p>
        )}
        <Field label="Nível do computador"
          hint={auto ? "O nível automático é o seu nível contra o AURA: vitória sobe, derrota desce. Os níveis são aproximados, não são o rating de um site." : undefined}>
          <div className="space-y-2">
            <label className="flex cursor-pointer items-center gap-2">
              <input type="radio" name="lvl" className="accent-[rgb(var(--pen))]" checked={auto} onChange={() => void set({ play_auto_level: true })} />
              <span>Automático: <b className="tnum">{st?.suggested_level ?? "…"}</b> · {st?.level_name ?? ""} <span className="text-muted">(acompanha você)</span></span>
            </label>
            <label className="flex cursor-pointer items-center gap-2">
              <input type="radio" name="lvl" className="accent-[rgb(var(--pen))]" checked={!auto} onChange={() => void set({ play_auto_level: false })} />
              <span>Escolher o nível</span>
            </label>
            {!auto && (
              <div className="flex flex-wrap items-center gap-3 pl-6">
                <input type="range" min={400} max={2500} step={50} value={lvl} aria-label="Nível"
                  onChange={(e) => setLvl(+e.target.value)} onPointerUp={() => void set({ play_level: lvl })}
                  onKeyUp={() => void set({ play_level: lvl })} className="min-w-[10rem] flex-1 accent-[rgb(var(--pen))]" />
                <span className="tnum shrink-0 font-bold">{lvl} · {nameFor(lvl, levels)}</span>
              </div>
            )}
          </div>
        </Field>
        <Field label="Suas peças" hint={forcedColor ? `Esta posição define a cor: você joga de ${forcedColor === "white" ? "Brancas" : "Pretas"}.` : undefined}>
          <Seg label="Suas peças" value={prefs.play_color} onChange={(v) => void set({ play_color: v })}
            options={[{ value: "white", label: "Brancas" }, { value: "black", label: "Pretas" }, { value: "random", label: "Sorteio" }]} />
        </Field>
        <Field label="Começar de">
          <Seg label="Começar de" value={kind} onChange={setKind} options={kinds} />
          <div className="space-y-2 pt-2">
            {kind === "opening" && (
              <select className="input" value={openingId} onChange={(e) => setOpeningId(e.target.value)} aria-label="Abertura">
                {(starts?.openings ?? []).map((o: any) => <option key={o.id} value={o.id}>{o.name}: {o.moves}</option>)}
              </select>
            )}
            {kind === "repertoire" && (
              <select className="input" value={repId} onChange={(e) => setRepId(e.target.value)} aria-label="Linha do repertório">
                {(starts?.repertoire ?? []).map((r: any) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            )}
            {kind === "endgame" && (
              <select className="input" value={endId} onChange={(e) => setEndId(e.target.value)} aria-label="Final">
                {(starts?.endgames ?? []).map((e: any) => (
                  <option key={e.id} value={e.id}>{e.module}: {e.name} ({e.goal === "win" ? "ganhe" : "segure o empate"})</option>
                ))}
              </select>
            )}
            {kind === "mistake" && (
              <>
                <ul className="max-h-72 divide-y divide-rule overflow-y-auto rounded-lg border border-rule" aria-label="Seus erros">
                  {(starts?.mistakes ?? []).map((m: any) => (
                    <li key={m.id}>
                      <button type="button" onClick={() => setMistakeId(m.id)} aria-pressed={mistakeId === m.id}
                        className={`flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left text-sm hover:bg-sunk ${mistakeId === m.id ? "bg-pen/10" : ""}`}>
                        <span className={`chip ${m.severity === "blunder" ? "border-bad/50 text-bad" : "border-warn/50 text-warn"}`}>{meta.severity(m.severity)}</span>
                        <b><SanText san={m.move} /></b><span className="text-muted">melhor <SanText san={m.best} /></span>
                        <span className="ml-auto text-xs text-muted">contra {m.opponent}{m.date ? `, ${dateOnly(m.date)}` : ""}</span>
                      </button>
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-muted">Você recomeça da posição em que errou, para acertar desta vez e seguir jogando.</p>
              </>
            )}
            {kind === "fen" && (
              <input className="input text-sm" placeholder="Cole um FEN" value={fenIn} onChange={(e) => setFenIn(e.target.value)} aria-label="FEN" />
            )}
            {ok && choice.practice && <p className="text-xs text-muted">Partida de treino: não muda o seu nível. Só contam as que começam do início, de uma abertura ou do seu repertório.</p>}
            {!ok && kind !== "initial" && <p className="text-sm text-muted">{choice.error}</p>}
          </div>
        </Field>
        <Field label="Relógio" hint="Só o seu relógio corre. Acabou o tempo, acabou a partida.">
          <Seg label="Relógio" value={prefs.play_clock} onChange={(v) => void set({ play_clock: v })}
            options={[{ value: "none", label: "Sem relógio" }, { value: "5+3", label: "5+3" }, { value: "10+5", label: "10+5" },
              { value: "15+10", label: "15+10" }, { value: "30+0", label: "30 min" }]} />
        </Field>
        <Field label="Vermelhão nos seus erros">
          <Seg label="Vermelhão" value={prefs.play_alarm} onChange={(v) => void set({ play_alarm: v })}
            options={[{ value: "forte", label: "Tela vermelha" }, { value: "leve", label: "Só a borda" }, { value: "desligado", label: "Desligado" }]} />
          <p className="text-xs text-muted">Só avisa que você errou: não para a partida, não explica e não deixa voltar. O lance certo aparece no fim.</p>
          <div className="pt-1">
            <Check checked={prefs.play_punish} onChange={(v) => void set({ play_punish: v })}>
              O AURA sempre pune as suas capivaradas, mesmo nos níveis baixos
            </Check>
          </div>
        </Field>
        <Field label="Ajudas" hint="Usar dica tira a partida do seu nível (ela ainda vai para a revisão). Não existe voltar lance.">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <label className="flex items-center gap-2 text-sm">Dicas por partida
              <select className="input w-auto py-1" value={prefs.play_hints} onChange={(e) => void set({ play_hints: +e.target.value })}>
                {[0, 1, 2, 3, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <Check checked={prefs.play_show_eval} onChange={(v) => void set({ play_show_eval: v })}>Barra de avaliação</Check>
          </div>
        </Field>
        <button type="button" className="btn-primary px-8 py-3 text-base" disabled={!ok || !st}
          onClick={() => ok && onStart(choice)}>
          <Icon name="play" size={20} />Jogar
        </button>
      </section>
      <aside className="space-y-6"><Progress st={st} /></aside>
    </div>
  );
}

function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const lo = Math.min(...values), hi = Math.max(...values), w = 300, h = 56;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 4 - ((v - lo) / Math.max(1, hi - lo)) * (h - 8)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-14 w-full" role="img"
      aria-label={`Seu nível nas últimas ${values.length} partidas: de ${Math.round(values[0])} para ${Math.round(values[values.length - 1])}`}>
      <polyline points={pts} fill="none" stroke="rgb(var(--pen))" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round"
        vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Progress({ st }: { st: any }) {
  if (!st) return <Spinner label="Carregando o seu nível…" />;
  const hist: any[] = st.history ?? [];
  return (
    <section className="panel space-y-4 p-5">
      <div>
        <h2>Seu nível contra o AURA</h2>
        <p className="mt-1 text-sm text-muted">
          {st.games ? `${st.games} ${st.games === 1 ? "partida valendo" : "partidas valendo"}: ${st.wins} ${st.wins === 1 ? "vitória" : "vitórias"}, ${st.draws} ${st.draws === 1 ? "empate" : "empates"}, ${st.losses} ${st.losses === 1 ? "derrota" : "derrotas"}.`
            : `Começa em ${Math.round(st.rating)} (${st.seed ?? "ponto de partida"}) e se ajusta a cada partida que você joga sem ajuda.`}
        </p>
      </div>
      <p className="stat text-4xl">{Math.round(st.rating)}</p>
      <Spark values={hist.map((x) => x.rating)} />
      {hist.length > 0 && (
        <ul className="space-y-1 text-sm" aria-label="Últimas partidas valendo">
          {hist.slice(-6).reverse().map((h, i) => (
            <li key={i} className="flex items-center gap-2">
              <span className={`w-5 font-bold ${h.score === 1 ? "text-good" : h.score === 0 ? "text-bad" : "text-muted"}`}
                title={h.score === 1 ? "vitória" : h.score === 0 ? "derrota" : "empate"}>{h.score === 1 ? "V" : h.score === 0 ? "D" : "E"}</span>
              <span className="text-muted">contra o nível {h.level}</span>
              <span className="tnum ml-auto">{Math.round(h.rating)}</span>
              {h.game_id && <Link className="link text-xs" to={`/partidas/${h.game_id}`}>revisar</Link>}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-faint">Este nível é só contra o computador. O seu rating real continua vindo das suas partidas importadas.</p>
    </section>
  );
}

/* ------------------------------------------------------------------ the game */
type Hint = { uci: string; full: boolean };

function GameView({ levels, onAgain, onNew, refreshState, routine }: { levels: Level[];
  onAgain: (s: StartChoice, color?: Color, level?: number) => void; onNew: () => void; refreshState: () => void;
  routine: RoutineDay | null }) {
  const g = usePlay((s) => s.game)!;
  const patch = usePlay((s) => s.patch);
  const { prefs } = usePrefs();
  const [thinking, setThinking] = useState(false);
  const [alarm, setAlarm] = useState<Judgment | null>(null);
  const [hint, setHint] = useState<Hint | null>(null);
  const [lastJ, setLastJ] = useState<Judgment | null>(g.judgments[g.judgments.length - 1] ?? null);
  const [shake, setShake] = useState(0);
  const [note, setNote] = useState<ReactNode>(null);
  const [confirmResign, setConfirmResign] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [boardPx, setBoardPx] = useState(480);
  const busy = useRef(false);
  const id = g.id;
  /** This game, or null once another one has replaced it (requests in flight must not touch it). */
  const current = () => {
    const c = usePlay.getState().game;
    return c && c.id === id ? c : null;
  };

  const chess = useMemo(() => gameFrom(g.startFen, g.moves), [g.startFen, g.moves]);
  const fen = chess.fen();
  const hist = chess.history({ verbose: true });
  const last = hist[hist.length - 1];
  const turn: Color = chess.turn() === "w" ? "white" : "black";
  const myTurn = !g.over && turn === g.userColor;
  const engineColor: Color = g.userColor === "white" ? "black" : "white";

  // Looking back at the moves already played (← → Home End, the buttons, a click in the move list) is
  // view only: the game goes on underneath. The computer still answers, your clock still runs, nothing
  // is undone, and the pieces move only in the live position. `view` = moves shown, null = live.
  const [view, setView] = useState<number | null>(null);
  const liveCursor = hist.length;
  const cursor = view == null ? liveCursor : Math.min(view, liveCursor);
  const viewing = cursor < liveCursor;
  const shown = hist[cursor - 1];
  const go = (c: number) => {
    const n = Math.max(0, Math.min(liveCursor, c));
    if (n === cursor + 1 && hist[cursor]) moveSound(hist[cursor]);
    setView(n >= liveCursor ? null : n);
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof Element && e.target.closest("input, textarea, select, [contenteditable='true']")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return; // Alt+← is the browser's "back"
      if (e.key === "ArrowLeft") { e.preventDefault(); go(cursor - 1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); go(cursor + 1); }
      else if (e.key === "Home") { e.preventDefault(); go(0); }
      else if (e.key === "End") { e.preventDefault(); go(liveCursor); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const finishGame = useCallback(async (end: PlayResult, moves: string[]) => {
    const cur = current();
    if (!cur || cur.over) return;
    usePlay.getState().patch({ over: { ...end }, moves });
    const sc = userScore(end.result, cur.userColor);
    play(sc === 1 ? "correct" : sc === 0 ? "wrong" : "start");
    let summary: any;
    try {
      summary = await api.post("/api/play/finish", {
        start_fen: cur.startFen, moves, user_color: cur.userColor, level: cur.level, result: end.result, reason: end.reason,
        helped: cur.helped, practice: cur.practice, time_control: cur.clock ? `${cur.clock.base}+${cur.clock.inc}` : null,
        opening: cur.opening,
      });
      refreshState();
    } catch (e: any) {
      summary = { error: e.message };
    }
    if (current()) usePlay.getState().patch({ over: { ...end, summary } });
  }, [id, refreshState]); // eslint-disable-line react-hooks/exhaustive-deps

  // the computer's move whenever it is its turn (the red never holds it back)
  useEffect(() => {
    if (g.over || turn === g.userColor || busy.current) return;
    const cur0 = current();
    if (!cur0) return;
    busy.current = true;
    setThinking(true);
    const fenNow = fen, movesNow = cur0.moves, t0 = Date.now();
    const lj = cur0.judgments[cur0.judgments.length - 1];
    // after a blunder the punishing reply, whatever the level (unless switched off)
    const punish = prefs.play_punish && lj && lj.ply === movesNow.length - 1 && lj.verdict === "blunder" && lj.reply_uci ? lj : null;
    const ask: Promise<{ move: string; eval_cp: number | null }> = punish
      ? Promise.resolve({ move: punish.reply_uci!, eval_cp: -punish.eval_after_cp })
      : api.post("/api/play/move", { fen: fenNow, level: cur0.level });
    ask.then(async (r) => {
      const wait = 350 + Math.random() * 450 - (Date.now() - t0);
      if (wait > 0) await new Promise((res) => setTimeout(res, wait));
      const cur = current();
      if (!cur || cur.over || cur.moves.length !== movesNow.length) return; // you resigned or ran out of time meanwhile
      const mv = tryMove(fenNow, r.move);
      if (!mv) return;
      moveSound(mv.move);
      const moves = [...movesNow, r.move];
      usePlay.getState().patch({ moves, engineEval: r.eval_cp ?? cur.engineEval, turnStartedAt: Date.now() });
      if (punish) setNote(<>Sem perdão: o AURA jogou <b><SanText san={mv.move.san} /></b>, o lance que pune a sua capivarada.</>);
      const end = outcome(gameFrom(cur.startFen, moves));
      if (end) void finishGame(end, moves);
    }).catch((e) => setNote(e.message)).finally(() => {
      busy.current = false;
      setThinking(false);
    });
  }, [fen, g.over, thinking]); // eslint-disable-line react-hooks/exhaustive-deps

  // your clock (only yours runs)
  useEffect(() => {
    if (!g.clock || g.over) return;
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(t);
  }, [g.clock, g.over]);
  const myTime = g.clock && g.timeLeftMs != null ? (myTurn ? g.timeLeftMs - (now - g.turnStartedAt) : g.timeLeftMs) : null;
  const flagged = myTime != null && myTime <= 0 && myTurn;
  useEffect(() => {
    if (flagged) void finishGame({ result: g.userColor === "white" ? "0-1" : "1-0", reason: "tempo esgotado" }, g.moves);
  }, [flagged]); // eslint-disable-line react-hooks/exhaustive-deps

  const onMove = (uci: string) => {
    if (viewing || !myTurn || thinking || busy.current || flagged) return false;
    const fenBefore = fen;
    const r = tryMove(fenBefore, uci);
    if (!r) return false;
    moveSound(r.move);
    setHint(null);
    setNote(null);
    const moves = [...g.moves, uci];
    const timeLeftMs = g.clock && g.timeLeftMs != null
      ? Math.max(0, g.timeLeftMs - (Date.now() - g.turnStartedAt)) + g.clock.inc * 1000 : g.timeLeftMs;
    patch({ moves, timeLeftMs, turnStartedAt: Date.now() });
    const ply = moves.length - 1;
    const end = outcome(gameFrom(g.startFen, moves));
    busy.current = true;
    setThinking(true);
    api.post<any>("/api/play/judge", { fen: fenBefore, move: uci }).then((j) => {
      const cur = current();
      if (!cur || cur.moves.length !== moves.length) return;
      const judged: Judgment = { ...j, ply, fen_before: fenBefore };
      const bad = j.verdict === "mistake" || j.verdict === "blunder";
      const streak = bad ? 0 : cur.streak + 1;
      usePlay.getState().patch({ judgments: [...cur.judgments, judged], streak, bestStreak: Math.max(cur.bestStreak, streak),
        engineEval: -j.eval_after_cp });
      setLastJ(judged);
      if (bad && !end && prefs.play_alarm !== "desligado") {
        setShake((x) => x + 1);
        setAlarm(judged);
      }
    }).catch(() => { /* judging is a bonus: the game goes on */ }).finally(() => {
      busy.current = false;
      setThinking(false);
      if (end) void finishGame(end, moves);
    });
    return true;
  };

  const askHint = async () => {
    if (!myTurn || thinking) return;
    setView(null); // a hint is about the live position: show it
    if (hint && !hint.full) return setHint({ ...hint, full: true }); // already paid for: show the whole move
    if (g.hintsLeft <= 0) return;
    try {
      const r = await api.post<any>("/api/engine/analyse", { fen, depth: 14, multipv: 1 });
      const best = r.lines?.[0]?.move;
      if (!best || !current()) return;
      setHint({ uci: best, full: false });
      patch({ hintsLeft: g.hintsLeft - 1, helped: true });
    } catch (e: any) {
      setNote(e.message);
    }
  };

  const offerDraw = () => {
    if (g.moves.length < 20) return setNote("O AURA recusou o empate: ainda é cedo.");
    if (g.engineEval != null && g.engineEval > 30) return setNote("O AURA recusou o empate: ele acha que está melhor.");
    void finishGame({ result: "1/2-1/2", reason: "empate combinado" }, g.moves);
  };

  const resign = () => {
    if (!confirmResign) return setConfirmResign(true);
    setConfirmResign(false);
    void finishGame({ result: g.userColor === "white" ? "0-1" : "1-0", reason: "abandono" }, g.moves);
  };

  const counts = { inaccuracy: 0, mistake: 0, blunder: 0 };
  for (const j of g.judgments) if (j.verdict in counts) counts[j.verdict as keyof typeof counts] += 1;
  const marks: Record<number, ListMove["mark"]> = {};
  for (const j of g.judgments) if (j.verdict === "inaccuracy" || j.verdict === "mistake" || j.verdict === "blunder") marks[j.ply] = j.verdict;
  const startTurn = g.startFen.split(" ")[1] === "b" ? "b" : "w";
  const startNumber = Number(g.startFen.split(" ")[5] || 1);
  // the evaluation and the hint belong to the live position: not shown while looking back
  const ev = evalParts(viewing || g.engineEval == null ? null : engineColor === "white" ? g.engineEval : -g.engineEval);
  const arrows = hint?.full && !viewing ? [moveArrow(hint.uci, "best")!] : [];
  const badges: Badge[] = hint && !hint.full && !viewing ? [{ square: hint.uci.slice(0, 2), kind: "best" }] : [];
  const moveNo = (ply: number) => {
    const idx = ply + (startTurn === "b" ? 1 : 0);
    return `${startNumber + Math.floor(idx / 2)}${idx % 2 ? "…" : "."}`;
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
      <div className="min-w-0 xl:sticky xl:top-6 xl:self-start">
        <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
          <span className="font-bold">AURA {g.level}</span><span className="text-muted">· {g.levelName}</span>
          {thinking && !g.over && turn === engineColor && <Spinner label="pensando…" />}
          <span className="ml-auto text-xs text-muted">{g.startLabel}{g.practice ? " · treino" : ""}</span>
        </div>
        <div className="flex items-start gap-2">
          {prefs.play_show_eval && <EvalBar cp={ev.cp} mate={ev.mate} orientation={g.userColor} height={boardPx} />}
          <div key={shake} className={`min-w-0 flex-1 ${shake ? "board-shake" : ""}`}>
            <Board fen={viewing ? (shown?.after ?? g.startFen) : fen} orientation={g.userColor} onMove={onMove}
              interactive={!viewing && myTurn && !thinking && !flagged}
              lastMove={viewing ? (shown ? [shown.from, shown.to] : null) : last ? [last.from, last.to] : null}
              arrows={arrows} badges={badges} reserve={250} id="play" onSize={setBoardPx} />
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold">Você</span>
          {myTime != null && (
            <span className={`tnum rounded-md px-2 py-0.5 text-lg font-bold ${myTime < 30000 ? "bg-bad/15 text-bad" : "bg-sunk"} ${myTurn ? "ring-2 ring-pen/50" : ""}`}
              aria-label={`Seu tempo: ${clockText(myTime)}`}>
              {clockText(myTime)}
            </span>
          )}
          <span className="flex items-center" role="group" aria-label="Ver os lances já jogados">
            <button className="btn-quiet btn-sm px-2" onClick={() => go(0)} disabled={cursor === 0} aria-label="Posição inicial" title="Posição inicial (Home)"><Icon name="first" /></button>
            <button className="btn-quiet btn-sm px-2" onClick={() => go(cursor - 1)} disabled={cursor === 0} aria-label="Lance anterior" title="Lance anterior (←)"><Icon name="back" /></button>
            <button className="btn-quiet btn-sm px-2" onClick={() => go(cursor + 1)} disabled={!viewing} aria-label="Próximo lance" title="Próximo lance (→)"><Icon name="forward" /></button>
            <button className="btn-quiet btn-sm px-2" onClick={() => go(liveCursor)} disabled={!viewing} aria-label="Lance atual" title="Lance atual (End)"><Icon name="last" /></button>
          </span>
          {!g.over && (
            <span className="ml-auto flex flex-wrap gap-1">
              <button className="btn btn-sm" onClick={askHint} disabled={!myTurn || thinking || (!hint && g.hintsLeft <= 0) || !!hint?.full}
                title="A 1ª vez mostra a peça; a 2ª, o lance. A partida deixa de contar para o seu nível.">
                {hint && !hint.full ? "Mostrar o lance" : `Dica (${g.hintsLeft})`}
              </button>
              <button className="btn btn-sm" onClick={offerDraw} disabled={thinking}>Empate?</button>
              <button className={`btn btn-sm ${confirmResign ? "border-bad text-bad" : ""}`} onClick={resign} onBlur={() => setConfirmResign(false)}>
                {confirmResign ? "Confirmar abandono" : "Abandonar"}
              </button>
            </span>
          )}
        </div>
        {viewing && (
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-pen/40 bg-pen/5 px-3 py-2 text-sm" aria-live="polite">
            <span>
              {shown ? <>Você está vendo o lance {moveNo(cursor - 1)} <SanText san={shown.san} /></> : "Você está vendo a posição inicial"}, só para olhar.
              {!g.over && <> A partida continua: {myTurn ? `é a sua vez${g.clock ? " e o seu relógio está correndo" : ""}` : "o AURA está pensando"}.</>}
            </span>
            <button className="btn-primary btn-sm ml-auto" onClick={() => go(liveCursor)} title="Tecla End">
              {g.over ? "Ir para o fim" : "Voltar ao lance atual"}
            </button>
          </div>
        )}
      </div>

      <aside className="min-w-0 space-y-5">
        {g.over ? (
          <EndPanel levels={levels} onAgain={onAgain} onNew={onNew} routine={routine} />
        ) : (
          <div className="panel space-y-3 p-4">
            <p className="text-lg font-bold" aria-live="polite">{myTurn ? (thinking ? "Conferindo o seu lance…" : "Sua vez") : "O AURA está pensando…"}</p>
            {lastJ && (
              <p className="text-sm">
                <b className={VERDICT[lastJ.verdict]?.tone}>{VERDICT[lastJ.verdict]?.label}</b>
                {lastJ.verdict === "best" ? <>: <SanText san={lastJ.user_san} /> era exatamente o lance do Stockfish.</>
                  : lastJ.verdict === "good" ? <>: <SanText san={lastJ.user_san} />.</>
                  : <>: <SanText san={lastJ.user_san} />. O lance certo só no fim da partida.</>}
              </p>
            )}
            {hint && !hint.full && <p className="text-sm">Dica: a peça marcada com a estrela tem o melhor lance.</p>}
            {note && <p className="text-sm text-muted">{note}</p>}
            <div className="grid grid-cols-2 gap-3 border-t border-rule pt-3 text-sm">
              <div><div className="text-muted">Lances seguidos sem erro</div><div className="stat mt-1">{g.streak}</div>
                <div className="text-xs text-faint">recorde da partida: {g.bestStreak}</div></div>
              <div><div className="text-muted">Nesta partida</div>
                <div className="mt-1 space-y-0.5">
                  <div><b className="text-bad">{counts.blunder}</b> {counts.blunder === 1 ? "capivarada" : "capivaradas"}</div>
                  <div><b className="text-bad">{counts.mistake}</b> {counts.mistake === 1 ? "erro" : "erros"}</div>
                  <div><b className="text-warn">{counts.inaccuracy}</b> {counts.inaccuracy === 1 ? "imprecisão" : "imprecisões"}</div>
                </div>
              </div>
            </div>
            {g.practice ? <p className="text-xs text-faint">Partida de treino: não muda o seu nível.</p>
              : g.helped && <p className="text-xs text-faint">Você usou dica: esta partida não muda o seu nível.</p>}
          </div>
        )}
        <div>
          <h3 className="mb-2 text-sm text-muted">Lances</h3>
          <MoveList moves={hist.map((h, i) => ({ san: h.san, mark: marks[i] ?? null }))} cursor={cursor} onJump={go}
            startTurn={startTurn} startNumber={startNumber} maxHeight={360} />
        </div>
      </aside>

      {alarm && prefs.play_alarm !== "desligado" && (
        <BlunderAlarm key={alarm.ply} verdict={alarm.verdict === "blunder" ? "blunder" : "mistake"}
          mode={prefs.play_alarm === "leve" ? "leve" : "forte"} onDone={() => setAlarm(null)} />
      )}
    </div>
  );
}

function EndPanel({ levels, onAgain, onNew, routine }: { levels: Level[]; onAgain: (s: StartChoice, color?: Color, level?: number) => void;
  onNew: () => void; routine: RoutineDay | null }) {
  const g = usePlay((s) => s.game)!;
  const { prefs } = usePrefs();
  const over = g.over!;
  const sc = userScore(over.result, g.userColor);
  const sum = over.summary;
  const bad = g.judgments.filter((j) => j.verdict === "mistake" || j.verdict === "blunder");
  const worst = [...bad].sort((a, b) => b.win_pct_loss - a.win_pct_loss)[0];
  const same: StartChoice = { fen: g.startFen, label: g.startLabel, opening: g.opening, color: null, practice: g.practice };
  // the automatic level follows the result; a level you chose stays
  const again = prefs.play_auto_level ? sum?.next_level ?? g.level : undefined;
  const diff = sum?.rated ? Math.round(sum.rating_after - sum.rating_before) : 0;
  const moveNo = (ply: number) => {
    const idx = ply + (g.startFen.split(" ")[1] === "b" ? 1 : 0);
    return `${Number(g.startFen.split(" ")[5] || 1) + Math.floor(idx / 2)}${idx % 2 ? "…" : "."}`;
  };
  const from = (j: Judgment, label: string): StartChoice => ({ fen: j.fen_before, label, opening: null, color: g.userColor, practice: true });
  const gamesStep = stepFor(routine, "games");
  return (
    <div className="panel space-y-4 p-5">
      <div>
        <p className={`text-2xl font-black ${sc === 1 ? "text-good" : sc === 0 ? "text-bad" : ""}`}>
          {sc === 1 ? "Você venceu!" : sc === 0 ? "Você perdeu" : "Empate"}
        </p>
        <p className="text-sm text-muted">{over.result.replace("1/2-1/2", "½-½")} por {over.reason}, contra o AURA {g.level} ({g.levelName}).</p>
      </div>
      {!sum ? <Spinner label="Salvando a partida…" /> : sum.error ? <ErrorNote>{sum.error}</ErrorNote> : (
        <div className="space-y-1 text-sm">
          {sum.rated ? (
            <p>Seu nível: <b className="tnum">{Math.round(sum.rating_before)}</b> → <b className="tnum">{Math.round(sum.rating_after)}</b>{" "}
              <span className={diff > 0 ? "text-good" : diff < 0 ? "text-bad" : "text-muted"}>({diff > 0 ? "+" : ""}{diff})</span></p>
          ) : (
            <p className="text-muted">{g.practice ? "Partida de treino: não muda o seu nível."
              : g.helped ? "Você usou dica: esta partida não muda o seu nível."
              : "A partida acabou cedo demais para mudar o seu nível."}</p>
          )}
          <p className="text-muted">Próximo nível automático: <b className="text-ink">{sum.next_level}</b> · {sum.next_level_name ?? nameFor(sum.next_level, levels)}</p>
          {gamesStep && !g.practice && (
            routine?.finished ? <p className="font-bold text-good">Rotina de hoje feita. <Link className="link" to="/">Ver a rotina</Link></p>
              : gamesStep.completed ? <p>As partidas da rotina de hoje estão feitas.</p>
              : <p>Rotina de hoje: <b>{Math.min(gamesStep.done, gamesStep.target)} de {gamesStep.target}</b> partidas.</p>
          )}
        </div>
      )}
      {bad.length > 0 ? (
        <div>
          <p className="mb-1 text-sm font-bold">Seus erros nesta partida</p>
          <ul className="space-y-1 text-sm">
            {bad.map((j) => (
              <li key={j.ply} className="flex flex-wrap items-center gap-2">
                <span className={`chip ${j.verdict === "blunder" ? "border-bad/50 text-bad" : "border-warn/50 text-warn"}`}>{VERDICT[j.verdict].label.toLowerCase()}</span>
                <span className="tnum">{moveNo(j.ply)} <SanText san={j.user_san} /></span>
                <span className="text-muted">melhor <SanText san={j.best_san} /></span>
                <button className="link ml-auto text-xs" onClick={() => onAgain(from(j, `Do seu erro no lance ${moveNo(j.ply)}`), g.userColor, g.level)}>jogar daqui</button>
              </li>
            ))}
          </ul>
        </div>
      ) : g.judgments.length > 0 ? <p className="text-sm text-good">Nenhum erro nem capivarada nesta partida.</p> : null}
      <div className="flex flex-wrap gap-2 border-t border-rule pt-4">
        {sum?.game_id && <Link className="btn-primary" to={`/partidas/${sum.game_id}`}>Revisar a partida</Link>}
        {worst && <button className="btn" onClick={() => onAgain(from(worst, "Do seu pior lance"), g.userColor, g.level)}>Tentar de novo do pior lance</button>}
        <button className="btn" onClick={() => onAgain(same, g.userColor, again)}>Jogar de novo</button>
        <button className="btn" onClick={() => onAgain(same, g.userColor === "white" ? "black" : "white", again)}>Trocar as cores</button>
        <button className="btn-quiet" onClick={onNew}>Nova partida</button>
      </div>
      {sum?.game_id && <p className="text-xs text-faint">A partida foi para Partidas e está sendo analisada: os erros entram no seu Error DNA e no treino em ciclo.</p>}
    </div>
  );
}
