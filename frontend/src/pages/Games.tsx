import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Board from "../components/Board";
import Explain from "../components/Explain";
import Help from "../components/Help";
import Icon from "../components/Icon";
import MoveList from "../components/MoveList";
import { Bar, Empty, ErrorNote, Metric, PageHeader, SanText, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { turnOf, walk } from "../lib/chess";
import { dateOnly, duration, num } from "../lib/format";
import { TIME_CLASS, useMeta } from "../lib/meta";
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
  const meta = useMeta();

  useEffect(() => {
    api.get(`/api/games/${id}`).then((x) => { setG(x); setCursor(0); }).catch((e) => setErr(e.message));
  }, [id]);
  const steps = useMemo(() => (g ? walk(g.start_fen, g.moves_uci) : []), [g]);
  const marks = useMemo(() => {
    const m: Record<number, any> = {};
    for (const x of g?.mistakes ?? []) m[x.ply] = x;
    return m;
  }, [g]);
  const go = useCallback((c: number) => {
    const n = Math.max(0, Math.min(steps.length, c));
    if (n === cursor + 1 && steps[cursor]) moveSound({ san: steps[cursor].san, flags: steps[cursor].flags });
    setPreview(null);
    setCursor(n);
    setFocus(marks[n - 1] ?? null);
  }, [steps, cursor, marks]);
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
  const openMistake = (m: any) => {
    setPreview(null);
    setCursor(m.ply);
    setFocus(m);
  };
  const bestArrow = focus && cursor === focus.ply && !preview
    ? [[focus.best_uci.slice(0, 2), focus.best_uci.slice(2, 4), "rgba(29, 138, 78, 0.8)"] as any] : [];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Link className="btn-quiet btn-sm -ml-2" to="/partidas"><Icon name="back" size={18} />Partidas</Link>
        <h1 className="text-xl">{g.white} × {g.black} <span className="text-muted">{g.result}</span></h1>
        <span className="text-sm text-muted">{dateOnly(g.date)}{g.time_class ? `, ${TIME_CLASS[g.time_class]}` : ""}{g.user_elo ? `, seu rating ${g.user_elo}` : ""}</span>
      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0">
          <Board fen={fen} orientation={orientation} interactive={false} lastMove={lastMove} arrows={bestArrow}
            badges={focus && cursor === focus.ply + 1 && !preview ? [{ square: focus.move_uci.slice(2, 4), kind: "bad" }] : []} reserve={170} id="review" />
          <div className="mt-3 flex items-center gap-1">
            <button className="btn-quiet btn-sm" onClick={() => go(0)} aria-label="Início"><Icon name="first" /></button>
            <button className="btn-quiet btn-sm" onClick={() => go(cursor - 1)} aria-label="Anterior"><Icon name="back" /></button>
            <button className="btn-quiet btn-sm" onClick={() => go(cursor + 1)} aria-label="Próximo"><Icon name="forward" /></button>
            <button className="btn-quiet btn-sm" onClick={() => go(steps.length)} aria-label="Fim"><Icon name="last" /></button>
            {preview && <button className="link ml-3 text-sm" onClick={() => setPreview(null)}>voltar à partida</button>}
          </div>
        </div>
        <aside className="min-w-0 space-y-6">
          <div className="grid grid-cols-3 gap-4">
            <Metric label="Precisão" help="game_accuracy" value={g.metrics?.accuracy != null ? String(g.metrics.accuracy).replace(".", ",") : "—"} />
            <Metric label="ACPL" help="acpl" value={g.metrics?.acpl != null ? String(g.metrics.acpl).replace(".", ",") : "—"} />
            <Metric label="Erros por 100 lances" help="severity" value={g.metrics?.errors_per_100 != null ? String(g.metrics.errors_per_100).replace(".", ",") : "—"} />
          </div>
          <div>
            <div className="mb-2 flex items-center gap-2"><h2>Seus erros</h2><Help id="severity" /></div>
            {g.mistakes.length === 0 ? <p className="text-muted">Nenhuma imprecisão, erro ou capivarada nesta partida.</p> : (
              <ul className="divide-y divide-rule border-y border-rule">
                {g.mistakes.map((m: any) => (
                  <li key={m.id}>
                    <button className={`flex w-full flex-wrap items-center gap-2 px-1 py-2 text-left text-sm hover:bg-sunk ${focus?.id === m.id ? "bg-pen/5" : ""}`} onClick={() => openMistake(m)}>
                      <span className={`chip ${m.severity === "blunder" ? "border-bad/50 text-bad" : m.severity === "mistake" ? "border-warn/50 text-warn" : ""}`}>{meta.severity(m.severity)}</span>
                      <span className="tnum font-bold">{Math.floor(m.ply / 2) + 1}{m.ply % 2 ? "…" : "."} <SanText san={m.move} /></span>
                      <span className="text-muted">melhor <SanText san={m.best} /></span>
                      <span className="ml-auto text-xs text-muted">{meta.dna(m.category)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {focus && (
            <div className="space-y-2">
              <p className="text-sm text-muted">Lance {Math.floor(focus.ply / 2) + 1}: você jogou <b className="text-ink"><SanText san={focus.move} /></b>; o Stockfish preferia <b className="text-good"><SanText san={focus.best} /></b> (seta verde).
                {focus.think_s != null && ` Você pensou ${String(Math.round(focus.think_s * 10) / 10).replace(".", ",")} s.`}</p>
              <Explain key={focus.id} request={{ game_mistake_id: focus.id }} onPreview={(f, lm) => setPreview({ fen: f, lastMove: lm })} />
            </div>
          )}
          <div>
            <h3 className="mb-2 text-sm text-muted">Lances</h3>
            <MoveList moves={steps.map((s, i) => ({ san: s.san, mark: marks[i]?.severity ?? null }))} cursor={cursor} onJump={go}
              startTurn={turnOf(g.start_fen) === "white" ? "w" : "b"} maxHeight={440} />
          </div>
        </aside>
      </div>
    </div>
  );
}
