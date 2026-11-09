import { useEffect, useState } from "react";
import Board from "../components/Board";
import { Empty, ErrorNote, PageHeader, SanText } from "../components/ui";
import { api } from "../lib/api";
import { tryMove, walk, whiteScore, evalLabel } from "../lib/chess";
import { moveSound, play } from "../lib/sound";

export default function Openings() {
  const [reps, setReps] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [color, setColor] = useState("white");
  const [form, setForm] = useState<{ rid: number; name: string; moves: string; fen: string } | null>(null);
  const [drill, setDrill] = useState<{ line: any; color: string; ply: number; fen: string; last: [string, string] | null; feedback?: string; ok?: boolean } | null>(null);
  const [study, setStudy] = useState<any>(null);
  const [mistakes, setMistakes] = useState<any[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    api.get("/api/openings").then(setReps).catch((e) => setErr(e.message));
    api.get("/api/openings/mistakes").then(setMistakes).catch(() => {});
  };
  useEffect(load, []);

  async function create() {
    if (!name.trim()) return;
    await api.post("/api/openings", { name: name.trim(), color });
    setName("");
    load();
  }
  async function addLine() {
    if (!form) return;
    try {
      await api.post(`/api/openings/${form.rid}/lines`, { name: form.name || "Linha", moves: form.moves, start_fen: form.fen || undefined });
      setForm(null);
      setErr(null);
      load();
    } catch (e: any) {
      setErr(e.message);
    }
  }
  const stepAt = (line: any, ply: number) => {
    const steps = ply === 0 ? [] : walk(line.start_fen, line.moves_uci.slice(0, ply));
    return steps.length ? steps[steps.length - 1] : null;
  };
  const fenAt = (line: any, ply: number) => stepAt(line, ply)?.fen ?? line.start_fen;
  const lastAt = (line: any, ply: number) => stepAt(line, ply)?.lastMove ?? null;
  function startDrill(line: any, repColor: string) {
    const startTurn = line.start_fen.split(" ")[1] === "w" ? "white" : "black";
    const ply = startTurn === repColor ? 0 : 1;
    setDrill({ line, color: repColor, ply, fen: fenAt(line, ply), last: lastAt(line, ply) });
    setStudy(null);
  }
  function onDrillMove(uci: string) {
    if (!drill) return false;
    const { line, ply } = drill;
    const r = tryMove(drill.fen, uci);
    if (!r) return false;
    moveSound(r.move);
    setDrill({ ...drill, fen: r.fen, last: [uci.slice(0, 2), uci.slice(2, 4)] });
    api.post(`/api/openings/lines/${line.id}/drill`, { ply, uci }).then((res) => {
      if (res.correct) {
        const done = ply + 1 >= line.moves_uci.length;
        const nextPly = Math.min(line.moves_uci.length, ply + 2);
        window.setTimeout(() => {
          if (!done) moveSound(walk(fenAt(line, ply + 1), [line.moves_uci[ply + 1]])[0] ?? null);
          else play("correct");
          setDrill({ ...drill, ply: done ? line.moves_uci.length : nextPly, fen: fenAt(line, done ? line.moves_uci.length : nextPly),
            last: lastAt(line, done ? line.moves_uci.length : nextPly), feedback: done ? "Linha completa." : "Certo.", ok: true });
        }, 250);
      } else {
        play("wrong");
        setDrill({ ...drill, fen: fenAt(line, ply), last: lastAt(line, ply), feedback: `O lance do seu repertório é ${res.expected_san}.`, ok: false });
        load();
      }
    });
    return true;
  }

  return (
    <div>
      <PageHeader title="Aberturas" purpose="Monte o seu repertório, treine os lances de memória e veja a estrutura de peões e os planos do Stockfish no fim de cada linha. Use quando você já sabe as aberturas que joga." />
      {err && <div className="mb-4"><ErrorNote>{err}</ErrorNote></div>}
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          <div className="flex flex-wrap gap-2">
            <input className="input min-w-[12rem] flex-1" placeholder="Nome do repertório (ex.: Italiana)" value={name} onChange={(e) => setName(e.target.value)} />
            <select className="input w-auto" value={color} onChange={(e) => setColor(e.target.value)}><option value="white">de Brancas</option><option value="black">de Pretas</option></select>
            <button className="btn-primary" onClick={create} disabled={!name.trim()}>Criar repertório</button>
          </div>
          {reps.length === 0 && <Empty title="Nenhum repertório ainda">Crie um repertório e adicione linhas colando os lances (ex.: 1. e4 e5 2. Cf3 Cc6 3. Bc4, ou em inglês: Nf3 Nc6).</Empty>}
          {reps.map((r) => (
            <section key={r.id} className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <h2>{r.name}</h2><span className="chip">{r.color === "white" ? "Brancas" : "Pretas"}</span>
                <span className="ml-auto flex gap-1">
                  <button className="btn btn-sm" onClick={() => setForm({ rid: r.id, name: "", moves: "", fen: "" })}>Adicionar linha</button>
                  <button className="btn-quiet btn-sm" onClick={() => { if (confirm(`Apagar o repertório "${r.name}" e todas as linhas?`)) api.del(`/api/openings/${r.id}`).then(load); }}>Apagar</button>
                </span>
              </div>
              {form && form.rid === r.id && (
                <div className="space-y-2 rounded-lg border border-rule p-3">
                  <input className="input" placeholder="Nome da linha" value={form.name} onChange={(e) => setForm((f) => f && { ...f, name: e.target.value })} />
                  <textarea className="input h-16 text-sm" placeholder="PGN ou lances: 1. e4 e5 2. Nf3 Nc6 3. Bc4" value={form.moves} onChange={(e) => setForm((f) => f && { ...f, moves: e.target.value })} />
                  <input className="input text-sm" placeholder="FEN inicial (opcional)" value={form.fen} onChange={(e) => setForm((f) => f && { ...f, fen: e.target.value })} />
                  <div className="flex gap-2"><button className="btn-primary" onClick={addLine}>Salvar linha</button><button className="btn-quiet" onClick={() => setForm(null)}>Cancelar</button></div>
                </div>
              )}
              <ul className="divide-y divide-rule border-y border-rule">
                {r.lines.map((l: any) => (
                  <li key={l.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                    <span className="font-bold">{l.name}</span>
                    <span className="min-w-0 flex-1 truncate text-muted">{l.moves_san.slice(0, 12).map((s: string, i: number) => <span key={i}><SanText san={s} /> </span>)}</span>
                    <button className="btn btn-sm" onClick={() => startDrill(l, r.color)}>Treinar</button>
                    <button className="btn-quiet btn-sm" onClick={() => { setDrill(null); api.get(`/api/openings/lines/${l.id}/study`).then((s) => setStudy({ ...s, line: l })); }}>Estudar</button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          <section>
            <h2 className="mb-2">Erros mais comuns</h2>
            {mistakes.length === 0 ? <p className="text-sm text-muted">Aparecem aqui os lances do repertório que você mais erra nos treinos.</p> : (
              <ul className="space-y-1 text-sm">{mistakes.map((m) => (
                <li key={`${m.line_id}-${m.ply}`}>{m.line}, lance {Math.floor(m.ply / 2) + 1}: o certo é <b><SanText san={m.expected_san} /></b> (errou {m.wrong} de {m.n})</li>
              ))}</ul>
            )}
          </section>
        </div>
        <div className="min-w-0 space-y-3">
          {drill && (
            <>
              <Board fen={drill.fen} orientation={drill.color as any} onMove={onDrillMove} interactive={drill.ply < drill.line.moves_uci.length} lastMove={drill.last} reserve={200} id="opening" />
              <p className={drill.ok === false ? "text-bad" : drill.ok ? "text-good" : "text-muted"}>{drill.feedback ?? "Jogue o lance do seu repertório."}</p>
              {drill.ply >= drill.line.moves_uci.length && <button className="btn" onClick={() => startDrill(drill.line, drill.color)}>Treinar de novo</button>}
            </>
          )}
          {study && (
            <div className="space-y-3">
              <Board fen={study.final_fen} interactive={false} reserve={260} id="study" />
              <div className="space-y-2 text-sm">
                <h3>Estrutura de peões no fim da linha</h3>
                <p>Colunas abertas: {study.structure.open_files.join(", ") || "nenhuma"}</p>
                {(["white", "black"] as const).map((c) => (
                  <p key={c}>{c === "white" ? "Brancas" : "Pretas"}: isolados {study.structure[c].isolated.join(", ") || "nenhum"}; dobrados {study.structure[c].doubled.join(", ") || "nenhum"}; passados {study.structure[c].passed.join(", ") || "nenhum"}</p>
                ))}
                <h3 className="pt-2">Planos do Stockfish a partir daqui</h3>
                {study.engine_plans.map((p: any, i: number) => {
                  const w = whiteScore(p.cp, p.mate, study.final_fen);
                  return <p key={i}><span className="tnum mr-2 font-bold">{evalLabel(w.cp, w.mate)}</span>{p.pv_san.slice(0, 8).map((s: string, k: number) => <span key={k}><SanText san={s} /> </span>)}</p>;
                })}
                {study.engine_error && <p className="text-bad">{study.engine_error}</p>}
                <label className="block pt-2"><span className="label">Suas anotações sobre os planos</span>
                  <textarea className="input h-28" defaultValue={study.plans_notes} placeholder="Planos típicos, rupturas de peões, onde colocar as peças…"
                    onBlur={(e) => api.put(`/api/openings/lines/${study.line.id}/plans`, { plans: e.target.value })} /></label>
              </div>
            </div>
          )}
          {!drill && !study && <Empty title="Escolha uma linha">Clique em Treinar para jogar os lances de memória, ou em Estudar para ver a posição final e os planos.</Empty>}
        </div>
      </div>
    </div>
  );
}
