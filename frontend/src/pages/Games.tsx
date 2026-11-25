import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ArrowToggles from "../components/ArrowToggles";
import Board from "../components/Board";
import Explain from "../components/Explain";
import Help from "../components/Help";
import Icon from "../components/Icon";
import MoveList from "../components/MoveList";
import WinGraph from "../components/WinGraph";
import { Bar, Empty, ErrorNote, Metric, PageHeader, SanText, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { ARROW_KINDS, ArrowKind, nullMoveFen, pickArrows } from "../lib/arrows";
import { tryMove, turnOf, walk } from "../lib/chess";
import { dateOnly, duration, num } from "../lib/format";
import { TIME_CLASS, useMeta } from "../lib/meta";
import { playFromHref } from "../lib/playStore";
import { usePrefs } from "../lib/prefs";
import { moveSound } from "../lib/sound";

export default function Games() {
  const { id } = useParams();
  return id ? <Review id={Number(id)} /> : <GamesList />;
}

function useJob() {
  const [job, setJob] = useState<any>(null);
  useEffect(() => {
    let stop = false;
    let t: number;
    const tick = async () => {
      try {
        const j = await api.get("/api/games/jobs");
        if (stop) return;
        setJob(j);
        t = window.setTimeout(tick, j.status === "running" ? 1500 : 8000);
      } catch {
        t = window.setTimeout(tick, 8000);
      }
    };
    tick();
    const wake = () => { window.clearTimeout(t); tick(); };
    window.addEventListener("aura:job", wake);
    return () => { stop = true; window.clearTimeout(t); window.removeEventListener("aura:job", wake); };
  }, []);
  return job;
}

function GamesList() {
  const { prefs, set } = usePrefs();
  const [games, setGames] = useState<any[] | null>(null);
  const [user, setUser] = useState("");
  const [months, setMonths] = useState(3);
  const [pgn, setPgn] = useState("");
  const [names, setNames] = useState("");
  const [color, setColor] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const job = useJob();
  const nav = useNavigate();

  useEffect(() => {
    setUser(prefs.chesscom_username || "");
    setNames(prefs.player_names || "");
  }, [prefs.chesscom_username, prefs.player_names]);
  const load = useCallback(() => api.get("/api/games").then(setGames).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (job && job.status !== "running") load();
  }, [job?.status, job?.done, load]); // eslint-disable-line react-hooks/exhaustive-deps

  const kick = () => window.dispatchEvent(new Event("aura:job"));
  async function importChesscom() {
    setErr(null);
    setMsg(null);
    try {
      await api.post("/api/games/import/chesscom", { username: user.trim(), months, analyze: true });
      await set({ chesscom_username: user.trim() });
      kick();
    } catch (e: any) {
      setErr(e.message);
    }
  }
  async function importPgn() {
    setErr(null);
    try {
      const r = await api.post("/api/games/import", { pgn, analyze: true, user_color: color || undefined,
        player_names: names ? names.split(",").map((s) => s.trim()) : undefined });
      setMsg(`${num(r.imported)} partidas importadas${r.duplicates ? `, ${num(r.duplicates)} já existiam` : ""}${r.unknown_user_color ? `. Em ${num(r.unknown_user_color)} não achei o seu nome: escolha a cor na lista para analisar.` : "."}${r.errors.length ? ` Problemas: ${r.errors.join("; ")}` : ""}`);
      setPgn("");
      load();
      kick();
    } catch (e: any) {
      setErr(e.message);
    }
  }
  async function analyzeOne(gid: number, user_color?: string) {
    try {
      await api.post(`/api/games/${gid}/analyze${user_color ? `?user_color=${user_color}` : ""}`);
      kick();
      load();
    } catch (e: any) {
      setErr(e.message);
    }
  }
  const pending = (games ?? []).filter((g) => !g.analyzed && g.user_color).length;
  const stale = (games ?? []).filter((g) => g.stale).length;
  const running = job?.status === "running";

  return (
    <div>
      <PageHeader title="Partidas" help="error_dna"
        purpose="As suas partidas de verdade são a medida principal do treino. O AURA analisa cada lance seu com o Stockfish, aponta os erros e lê o seu rating real." />
      {err && <div className="mb-4"><ErrorNote>{err}</ErrorNote></div>}

      <section className="mb-8 grid gap-8 lg:grid-cols-2">
        <div>
          <h2>Importar do Chess.com</h2>
          <p className="mt-1 max-w-prose text-sm text-muted">Só o seu nome de usuário. As partidas públicas são baixadas pela API aberta do Chess.com, sem login, e analisadas em segundo plano.</p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="min-w-[10rem] flex-1">
              <span className="label">Usuário</span>
              <input className="input" value={user} onChange={(e) => setUser(e.target.value)} placeholder="ex.: vazwinz" autoComplete="off" />
            </label>
            <label>
              <span className="label">Período</span>
              <select className="input w-auto" value={months} onChange={(e) => setMonths(+e.target.value)}>
                {[1, 3, 6, 12].map((m) => <option key={m} value={m}>{m === 1 ? "último mês" : `últimos ${m} meses`}</option>)}
              </select>
            </label>
            <button className="btn-primary" onClick={importChesscom} disabled={user.trim().length < 2 || running}>Importar e analisar</button>
          </div>
        </div>
        <div>
          <h2>Colar ou enviar um PGN</h2>
          <p className="mt-1 text-sm text-muted">Do Lichess, de um torneio ou de qualquer site. Informe seus nomes de usuário para o AURA saber qual lado é você.</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder="Seus usuários, separados por vírgula" value={names} onChange={(e) => setNames(e.target.value)} />
            <select className="input" value={color} onChange={(e) => setColor(e.target.value)}>
              <option value="">Descobrir minha cor pelo nome</option><option value="white">Joguei de Brancas</option><option value="black">Joguei de Pretas</option>
            </select>
          </div>
          <textarea className="input mt-2 h-24 text-sm" placeholder='[Event "..."] 1. e4 e5 ...' value={pgn} onChange={(e) => setPgn(e.target.value)} />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <label className="btn cursor-pointer">Escolher arquivo .pgn<input type="file" accept=".pgn,text/plain" className="hidden"
              onChange={async (e) => { const f = e.target.files?.[0]; if (f) setPgn(await f.text()); }} /></label>
            <button className="btn-primary" disabled={pgn.trim().length < 10} onClick={importPgn}>Importar e analisar</button>
          </div>
          {msg && <p className="mt-2 text-sm text-muted">{msg}</p>}
        </div>
      </section>

      {job && job.status !== "idle" && (running || job.errors?.length || job.status === "failed") && (
        <section className="mb-8 rounded-xl border border-rule p-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-bold">
              {running ? (job.phase === "download" ? "Baixando partidas do Chess.com…" : "Analisando as partidas com o Stockfish") :
                job.status === "failed" ? "A análise parou" : job.status === "cancelled" ? "Análise cancelada" : "Pronto"}
            </span>
            {running && job.total > 0 && <span className="tnum text-sm text-muted">{num(job.done)} de {num(job.total)}{job.eta_s ? `, falta ${duration(job.eta_s)}` : ""}</span>}
            {running && <button className="btn-quiet btn-sm ml-auto" onClick={() => api.post("/api/games/jobs/cancel").then(kick)}>Cancelar</button>}
          </div>
          {running && job.total > 0 && <div className="mt-2"><Bar value={job.done / job.total} /></div>}
          {running && job.current && <p className="mt-2 text-sm text-muted">{job.current}</p>}
          {job.imported > 0 && <p className="mt-1 text-sm text-muted">{num(job.imported)} partidas novas importadas{job.duplicates ? `, ${num(job.duplicates)} já estavam aqui` : ""}.</p>}
          {job.error && <p className="mt-1 text-sm text-bad">{job.error}</p>}
          {job.errors?.map((e: string) => <p key={e} className="mt-1 text-sm text-bad">{e}</p>)}
          {running && <p className="mt-2 text-xs text-faint">Pode treinar enquanto isso: a análise usa um Stockfish separado.</p>}
        </section>
      )}

      <section>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h2>Suas partidas</h2>
          {pending > 0 && !running && <button className="btn btn-sm" onClick={() => api.post("/api/games/analyze-pending").then(kick)}>Analisar {num(pending)} pendentes</button>}
        </div>
        {stale > 0 && !running && (
          <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-warn/40 bg-warn/5 px-3 py-2 text-sm">
            <span>{stale === 1 ? "1 partida foi analisada" : `${num(stale)} partidas foram analisadas`} com os critérios antigos: imprecisões passavam como bons lances e não havia <b className="text-brill">!!</b> nem <b className="text-pen">!</b>.</span>
            <button className="btn btn-sm ml-auto" onClick={() => api.post("/api/games/reanalyze-stale").then(kick)}>Reanalisar {stale === 1 ? "" : `as ${num(stale)}`}</button>
          </div>
        )}
        {games == null ? <Spinner /> : games.length === 0 ? (
          <Empty title="Nenhuma partida ainda">Importe pelo seu usuário do Chess.com ou cole um PGN acima. Com 3 partidas analisadas o treino em ciclo já usa os seus erros reais.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-muted">
                <tr><th className="py-2 font-normal">Data</th><th className="font-normal">Partida</th><th className="font-normal">Ritmo</th>
                  <th className="text-right font-normal">Rating</th><th className="text-right font-normal">Precisão <Help id="game_accuracy" /></th>
                  <th className="text-right font-normal">Capivaradas</th><th /></tr>
              </thead>
              <tbody>
                {games.map((g) => {
                  const me = g.user_color === "white" ? g.white : g.user_color === "black" ? g.black : null;
                  const res = g.metrics?.result_for_user;
                  return (
                    <tr key={g.id} className="border-t border-rule">
                      <td className="tnum py-2 text-muted">{dateOnly(g.date)}</td>
                      <td>
                        <span className={g.user_color === "white" ? "font-bold" : ""}>{g.white}</span> × <span className={g.user_color === "black" ? "font-bold" : ""}>{g.black}</span>
                        <span className={`ml-2 text-xs font-bold ${res === 1 ? "text-good" : res === 0 ? "text-bad" : "text-muted"}`}>{g.result}</span>
                      </td>
                      <td className="text-muted">{TIME_CLASS[g.time_class] ?? "—"}</td>
                      <td className="tnum text-right">{g.user_elo ?? "—"}</td>
                      <td className="tnum text-right">{g.metrics?.accuracy != null ? String(g.metrics.accuracy).replace(".", ",") : "—"}</td>
                      <td className="tnum text-right">{g.metrics?.blunders ?? "—"}</td>
                      <td className="py-1 text-right">
                        {g.analyzed ? <button className="btn btn-sm" onClick={() => nav(`/partidas/${g.id}`)}>Revisar</button>
                          : g.analyzing ? <span className="text-sm text-pen">analisando…</span>
                          : g.user_color ? <span className="text-sm text-faint">na fila</span>
                          : <span className="inline-flex gap-1" title={me ? "" : "Não achei o seu nome nesta partida"}>
                              <button className="btn btn-sm" onClick={() => analyzeOne(g.id, "white")}>Eu de Brancas</button>
                              <button className="btn btn-sm" onClick={() => analyzeOne(g.id, "black")}>Eu de Pretas</button>
                            </span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ game review */
function Review({ id }: { id: number }) {
  const [g, setG] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);
  const [focus, setFocus] = useState<any>(null);
  const [preview, setPreview] = useState<{ fen: string; lastMove: [string, string] | null } | null>(null);
  const [order, setOrder] = useState<number[]>([]);
  const [good, setGood] = useState<any>(null); // the !! or ! move being looked at
  const [redoing, setRedoing] = useState(false);
  const [showInacc, setShowInacc] = useState(false);
  const meta = useMeta();
  const { prefs } = usePrefs();
  const nav = useNavigate();

  useEffect(() => {
    api.get(`/api/games/${id}`).then((x) => {
      setG(x);
      setCursor(0);
      setFocus(null);
      setGood(null);
      setPreview(null);
      window.scrollTo(0, 0);
    }).catch((e) => setErr(e.message));
  }, [id]);
  // "Reanalisar": the game goes to the background queue; reload it when the new analysis is in
  useEffect(() => {
    if (!redoing) return;
    const t = window.setInterval(() => {
      api.get<any>(`/api/games/${id}`).then((x) => {
        if (x.analyzed && !x.stale) {
          setRedoing(false);
          setG(x);
          setFocus(null);
          setGood(null);
        }
      }).catch(() => {});
    }, 2500);
    return () => window.clearInterval(t);
  }, [redoing, id]);
  // the analysed games in the list's order (newest first), for "Anterior" / "Próxima partida"
  useEffect(() => {
    api.get<any[]>("/api/games").then((list) => setOrder(list.filter((x) => x.analyzed).map((x) => x.id))).catch(() => {});
  }, []);
  const steps = useMemo(() => (g ? walk(g.start_fen, g.moves_uci) : []), [g]);
  const marks = useMemo(() => {
    const m: Record<number, any> = {};
    for (const x of g?.mistakes ?? []) m[x.ply] = x;
    return m;
  }, [g]);
  const goods = useMemo(() => {
    const m: Record<number, any> = {};
    for (const h of g?.metrics?.highlights ?? []) m[h.ply] = h;
    return m;
  }, [g]);
  const go = useCallback((c: number) => {
    const n = Math.max(0, Math.min(steps.length, c));
    if (n === cursor + 1 && steps[cursor]) moveSound({ san: steps[cursor].san, flags: steps[cursor].flags });
    setPreview(null);
    setCursor(n);
    setFocus(marks[n] ?? marks[n - 1] ?? null); // a mistake of yours about to be played here, or just played
    setGood(goods[n - 1] ?? null);              // a !! or ! of yours just played
  }, [steps, cursor, marks, goods]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea, select")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return; // Alt+← is "back", not "previous move"
      if (e.key === "ArrowLeft") { e.preventDefault(); go(cursor - 1); }
      if (e.key === "ArrowRight") { e.preventDefault(); go(cursor + 1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, cursor]);

  if (err) return <ErrorNote>{err}</ErrorNote>;
  if (!g) return <Spinner label="Carregando a partida…" />;
  const fen = preview?.fen ?? (cursor === 0 ? g.start_fen : steps[cursor - 1].fen);
  const lastMove = preview ? preview.lastMove : cursor > 0 ? steps[cursor - 1].lastMove : null;
  const orientation = g.user_color === "black" ? "black" : "white";
  // move numbers from the start position (a game from Jogar can start anywhere, with Black to move)
  const startTurn = turnOf(g.start_fen) === "white" ? "w" : "b";
  const startNumber = Number(g.start_fen.split(" ")[5] || 1);
  const moveNo = (ply: number) => {
    const i = ply + (startTurn === "b" ? 1 : 0);
    return `${startNumber + Math.floor(i / 2)}${i % 2 ? "…" : "."}`;
  };
  const moveNum = (ply: number) => startNumber + Math.floor((ply + (startTurn === "b" ? 1 : 0)) / 2);
  const openMistake = (m: any) => {
    setPreview(null);
    setCursor(m.ply);
    setFocus(m);
    setGood(null);
  };
  const openGood = (h: any) => {
    setPreview(null);
    setCursor(h.ply + 1);
    setFocus(null);
    setGood(h);
  };
  const highlights: any[] = g.metrics?.highlights ?? [];
  // "Onde você acha que perdeu?": a lost game asks once, before the engine's marks are shown
  const cal = g.calibration;
  const asking = !!cal?.lost && !cal.asked;
  const pick = (ply: number | null) => api.post<any>(`/api/games/${id}/calibration`, { ply }).then((r) => {
    setG((cur: any) => ({ ...cur, calibration: r }));
    if (r.decisive_ply != null && marks[r.decisive_ply]) openMistake(marks[r.decisive_ply]);
  }).catch((e) => setErr(e.message));
  const isGood = (k: string) => k === "great" || k === "brilliant";
  const nextMoment = (g.moments ?? []).map((m: any) => ({ ...m, at: isGood(m.kind) ? m.ply + 1 : m.ply }))
    .find((m: any) => m.at > cursor);
  const goMoment = () => {
    if (!nextMoment) return;
    if (isGood(nextMoment.kind) && goods[nextMoment.ply]) openGood(goods[nextMoment.ply]);
    else if (marks[nextMoment.ply]) openMistake(marks[nextMoment.ply]);
  };
  const serious = g.mistakes.filter((m: any) => m.severity !== "inaccuracy");
  const nInacc = g.mistakes.length - serious.length;
  const listed = showInacc ? g.mistakes : serious;
  const fmtPct = (v: number | null | undefined) => (v == null ? "—" : String(v).replace(".", ","));
  const fenAt = (ply: number) => (ply === 0 ? g.start_fen : steps[ply - 1].fen);
  // Arrows at your mistakes: just before you play one, the best move, your move and the opponent's
  // threat; right after it, the opponent's reply that punishes it. Each kind can be switched off.
  const upcoming = preview ? null : marks[cursor] ?? null;
  const justPlayed = preview || cursor === 0 ? null : marks[cursor - 1] ?? null;
  const threatOf = (m: any): string | null => ((m?.evidence?.threat_cp ?? 0) >= 100 ? m.evidence.threat_move ?? null : null);
  const arrows = upcoming
    ? pickArrows(prefs, [["opponent", threatOf(upcoming)], ["played", upcoming.move_uci], ["best", upcoming.best_uci]])
    : justPlayed ? pickArrows(prefs, [["opponent", justPlayed.evidence?.refutation]]) : [];
  const sanOf = (from: string | null, uci?: string | null) => (from && uci ? tryMove(from, uci)?.move.san ?? null : null);
  const notes: { kind: ArrowKind; san: string | null; text: string }[] = upcoming
    ? [{ kind: "best", san: upcoming.best, text: "o melhor lance" },
       { kind: "played", san: upcoming.move, text: "o seu lance" },
       { kind: "opponent", san: sanOf(nullMoveFen(fen), threatOf(upcoming)), text: "a ameaça do adversário, se fosse a vez dele" }]
    : justPlayed ? [{ kind: "opponent", san: sanOf(fen, justPlayed.evidence?.refutation), text: "a resposta do adversário que pune o lance" }] : [];
  const shownNotes = notes.filter((n) => n.san && prefs[ARROW_KINDS[n.kind].pref]);
  const idx = order.indexOf(id);
  const prevId = idx > 0 ? order[idx - 1] : null;
  const nextId = idx >= 0 && idx + 1 < order.length ? order[idx + 1] : null;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Link className="btn-quiet btn-sm -ml-2" to="/partidas"><Icon name="back" size={18} />Partidas</Link>
        <h1 className="text-xl">{g.white} × {g.black} <span className="text-muted">{g.result}</span></h1>
        <span className="text-sm text-muted">{dateOnly(g.date)}{g.time_class ? `, ${TIME_CLASS[g.time_class]}` : ""}{g.user_elo ? `, seu rating ${g.user_elo}` : ""}</span>
        {idx >= 0 && order.length > 1 && (
          <span className="ml-auto flex items-center gap-1">
            <span className="tnum mr-1 text-xs text-muted">{idx + 1} de {order.length}</span>
            <button className="btn-quiet btn-sm" disabled={!prevId} onClick={() => prevId && nav(`/partidas/${prevId}`)}><Icon name="back" size={18} />Anterior</button>
            <button className="btn btn-sm" disabled={!nextId} onClick={() => nextId && nav(`/partidas/${nextId}`)}>Próxima partida<Icon name="forward" size={18} /></button>
          </span>
        )}
      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        {/* the board stays in view while the mistakes and the explanation scroll past it */}
        <div className="min-w-0 xl:sticky xl:top-6 xl:self-start">
          <Board fen={fen} orientation={orientation} interactive={false} lastMove={lastMove} arrows={asking ? [] : arrows}
            badges={asking ? [] : justPlayed ? [{ square: justPlayed.move_uci.slice(2, 4), kind: "bad" }]
              : !preview && cursor > 0 && goods[cursor - 1] ? [{ square: goods[cursor - 1].uci.slice(2, 4), kind: goods[cursor - 1].kind }] : []}
            reserve={170} id="review" />
          <div className="mt-3 flex items-center gap-1">
            <button className="btn-quiet btn-sm" onClick={() => go(0)} aria-label="Início"><Icon name="first" /></button>
            <button className="btn-quiet btn-sm" onClick={() => go(cursor - 1)} aria-label="Lance anterior"><Icon name="back" /></button>
            <button className="btn-quiet btn-sm" onClick={() => go(cursor + 1)} aria-label="Próximo lance"><Icon name="forward" /></button>
            <button className="btn-quiet btn-sm" onClick={() => go(steps.length)} aria-label="Fim"><Icon name="last" /></button>
            <button className="btn btn-sm ml-2" onClick={goMoment} disabled={!nextMoment || asking}>Próximo momento</button>
            {preview && <button className="link ml-3 text-sm" onClick={() => setPreview(null)}>voltar à partida</button>}
          </div>
          <div className="mt-2"><ArrowToggles kinds={["best", "played", "opponent"]} /></div>
        </div>
        <aside className="min-w-0 space-y-6">
          {asking && (
            <div className="rounded-lg border border-pen/40 bg-pen/5 p-3 text-sm">
              <p className="font-bold">Onde você acha que perdeu?</p>
              <p className="text-muted">Antes de ver o que o motor diz: clique, na lista de lances, no lance em que a partida escapou.</p>
              <button className="link mt-1" onClick={() => void pick(null)}>pular</button>
            </div>
          )}
          {cal?.asked && cal.picked_ply != null && cal.decisive_ply != null && (
            <p className={`rounded-lg px-3 py-2 text-sm ${cal.hit ? "bg-good/10" : "bg-sunk"}`}>
              {cal.hit ? <>Você acertou onde perdeu: o lance {moveNum(cal.decisive_ply)} decidiu a partida.</>
                : <>Você marcou o lance {moveNum(cal.picked_ply)}; o que decidiu a partida foi o lance {moveNum(cal.decisive_ply)}.</>}
              {cal.stats.total > 1 && <span className="text-muted"> Você acertou onde perdeu em {cal.stats.hits} de {cal.stats.total} partidas.</span>}
            </p>
          )}
          {(g.metrics?.wins?.length ?? 0) > 1 && (
            <WinGraph wins={g.metrics.wins} think={g.metrics.think ?? []} cursor={cursor}
              moments={asking ? [] : g.moments ?? []} onJump={asking ? (c) => void pick(Math.max(0, c - 1)) : go} />
          )}
          {g.stale && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-warn/40 bg-warn/5 px-3 py-2 text-sm">
              <span>{redoing ? "Reanalisando com os critérios novos…" : "Analisada com os critérios antigos: imprecisões passavam como bons lances e não havia !! nem !."}</span>
              {!redoing && <button className="btn btn-sm ml-auto" onClick={() => api.post(`/api/games/${id}/analyze`).then(() => setRedoing(true)).catch((e) => setErr(e.message))}>Reanalisar</button>}
              {redoing && <Spinner />}
            </div>
          )}
          <div className="grid grid-cols-3 gap-4">
            <Metric label="Precisão" help="game_accuracy" value={g.metrics?.accuracy != null ? String(g.metrics.accuracy).replace(".", ",") : "—"} />
            <Metric label="ACPL" help="acpl" value={g.metrics?.acpl != null ? String(g.metrics.acpl).replace(".", ",") : "—"} />
            <Metric label="Erros por 100 lances" help="severity" value={g.metrics?.errors_per_100 != null ? String(g.metrics.errors_per_100).replace(".", ",") : "—"} />
          </div>
          {g.metrics?.phase_accuracy && (
            <p className="-mt-3 text-sm text-muted">
              Precisão por fase: abertura <b className="text-ink">{fmtPct(g.metrics.phase_accuracy.opening)}</b>
              {" · "}meio-jogo <b className="text-ink">{fmtPct(g.metrics.phase_accuracy.middlegame)}</b>
              {" · "}final <b className="text-ink">{fmtPct(g.metrics.phase_accuracy.endgame)}</b>
            </p>
          )}
          {g.metrics?.best_moves != null && (
            <div>
              <div className="mb-2 flex items-center gap-2"><h2>Seus melhores lances</h2><Help id="highlights" /></div>
              <p className="text-sm">
                <b className="text-good">★ {g.metrics.best_moves}</b> de {g.metrics.user_moves} lances foram exatamente o do Stockfish
                {g.metrics.great > 0 && <> · <b className="text-pen">! {g.metrics.great}</b> {g.metrics.great === 1 ? "lance único" : "lances únicos"}</>}
                {g.metrics.brilliant > 0 && <> · <b className="text-brill">!! {g.metrics.brilliant}</b> {g.metrics.brilliant === 1 ? "brilhante" : "brilhantes"}</>}
              </p>
              {highlights.length > 0 && (
                <ul className="mt-2 divide-y divide-rule border-y border-rule">
                  {highlights.map((h) => (
                    <li key={h.ply}>
                      <button className={`flex w-full flex-wrap items-center gap-2 px-1 py-2 text-left text-sm hover:bg-sunk ${good?.ply === h.ply ? "bg-pen/5" : ""}`} onClick={() => openGood(h)}>
                        <span className={`chip ${h.kind === "brilliant" ? "border-brill/50 text-brill" : "border-pen/50 text-pen"}`}>{h.kind === "brilliant" ? "!! brilhante" : "! lance único"}</span>
                        <span className="tnum font-bold">{moveNo(h.ply)} <SanText san={h.san} /></span>
                        {h.kind === "great" && h.second_san && <span className="text-muted">o 2º melhor era <SanText san={h.second_san} /></span>}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {good && !focus && (
            <div className="space-y-2">
              <p className="text-sm text-muted">Lance {moveNum(good.ply)}, <b className="text-ink"><SanText san={good.san} /></b>: {good.kind === "brilliant"
                ? "você entregou material e era o melhor lance do Stockfish."
                : "só esse lance segurava a posição: qualquer outro perdia pelo menos 10 pontos de chance de vitória."}</p>
              <Explain key={`good-${good.ply}`} request={{ fen: fenAt(good.ply), move: good.uci }} onPreview={(f, lm) => setPreview({ fen: f, lastMove: lm })} />
            </div>
          )}
          {!asking && <div>
            <div className="mb-2 flex items-center gap-2"><h2>Seus erros</h2><Help id="severity" /></div>
            {g.mistakes.length === 0 ? <p className="text-muted">Nenhuma imprecisão, erro ou capivarada nesta partida.</p>
              : listed.length === 0 ? <p className="text-muted">Nenhum erro ou capivarada nesta partida.</p> : (
              <ul className="divide-y divide-rule border-y border-rule">
                {listed.map((m: any) => (
                  <li key={m.id}>
                    <button className={`flex w-full flex-wrap items-center gap-2 px-1 py-2 text-left text-sm hover:bg-sunk ${focus?.id === m.id ? "bg-pen/5" : ""}`} onClick={() => openMistake(m)}>
                      <span className={`chip ${m.severity === "blunder" ? "border-bad/50 text-bad" : m.severity === "mistake" ? "border-warn/50 text-warn" : ""}`}>{meta.severity(m.severity)}</span>
                      <span className="tnum font-bold">{moveNo(m.ply)} <SanText san={m.move} /></span>
                      <span className="text-muted">melhor <SanText san={m.best} /></span>
                      <span className="ml-auto text-xs text-muted">{meta.dna(m.category)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {nInacc > 0 && (
              <button className="link mt-2 text-sm" onClick={() => setShowInacc(!showInacc)}>
                {showInacc ? "esconder as imprecisões" : `mostrar ${nInacc === 1 ? "1 imprecisão" : `${nInacc} imprecisões`}`}
              </button>
            )}
          </div>}
          {focus && !asking && (
            <div className="space-y-2">
              <p className="text-sm text-muted">Lance {moveNum(focus.ply)}: você jogou <b className="text-ink"><SanText san={focus.move} /></b>; o Stockfish preferia <b className="text-good"><SanText san={focus.best} /></b>.
                {focus.think_s != null && ` Você pensou ${String(Math.round(focus.think_s * 10) / 10).replace(".", ",")} s.`}
                {cursor === focus.ply + 1 && !preview && <> <button className="link" onClick={() => go(focus.ply)}>Voltar para antes do lance</button></>}</p>
              <Link className="btn btn-sm" to={playFromHref(focus.fen, turnOf(focus.fen),
                `Do seu erro contra ${g.user_color === "white" ? g.black : g.white}, lance ${moveNum(focus.ply)}`)}>
                <Icon name="play" size={16} />Jogar daqui contra o computador
              </Link>
              {shownNotes.length > 0 && (
                <ul className="space-y-1 rounded-lg bg-sunk/50 px-3 py-2 text-sm" aria-label="O que as setas mostram">
                  {shownNotes.map((n) => (
                    <li key={n.kind} className="flex items-center gap-2">
                      <span aria-hidden className="inline-block h-1.5 w-5 shrink-0 rounded-full" style={{ background: ARROW_KINDS[n.kind].color }} />
                      <b><SanText san={n.san!} /></b><span className="text-muted">{n.text}</span>
                    </li>
                  ))}
                </ul>
              )}
              <Explain key={focus.id} request={{ game_mistake_id: focus.id }} onPreview={(f, lm) => setPreview({ fen: f, lastMove: lm })} />
            </div>
          )}
          <div>
            <h3 className="mb-2 text-sm text-muted">Lances</h3>
            <MoveList moves={steps.map((s, i) => ({ san: s.san, mark: asking ? null : marks[i]?.severity ?? goods[i]?.kind ?? null }))}
              cursor={cursor} onJump={asking ? (c) => void pick(Math.max(0, c - 1)) : go}
              startTurn={startTurn} startNumber={startNumber} maxHeight={440} />
          </div>
          {nextId && (
            <div className="border-t border-rule pt-4">
              <button className="btn-primary w-full" onClick={() => nav(`/partidas/${nextId}`)}>Próxima partida<Icon name="forward" size={18} /></button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
