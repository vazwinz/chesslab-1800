import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Board from "../components/Board";
import { Empty, ErrorNote, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { tryMove, turnOf } from "../lib/chess";
import { moveSound, play } from "../lib/sound";

export default function Endgames() {
  const [positions, setPositions] = useState<any[]>([]);
  const [cur, setCur] = useState<any>(null);
  const [fen, setFen] = useState("");
  const [last, setLast] = useState<[string, string] | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api.get("/api/endgames").then(setPositions).catch((e) => setErr(e.message)); }, []);
  function pick(p: any) { setCur(p); setFen(p.fen); setMsg(null); setDone(false); setLast(null); setErr(null); }

  function onMove(uci: string) {
    if (!cur || busy || done) return false;
    const r = tryMove(fen, uci);
    if (!r) return false;
    moveSound(r.move);
    const before = fen;
    setFen(r.fen);
    setLast([uci.slice(0, 2), uci.slice(2, 4)]);
    setBusy(true);
    api.post("/api/endgames/move", { position_id: cur.id, fen: before, uci }).then((res) => {
      if (res.move) {
        window.setTimeout(() => {
          moveSound(tryMove(r.fen, res.move)?.move);
          setFen(res.fen);
          setLast([res.move.slice(0, 2), res.move.slice(2, 4)]);
        }, 200);
      }
      if (res.finished) {
        setDone(true);
        play(res.success ? "correct" : "wrong");
        setMsg({ ok: res.success, text: res.success ? `Objetivo cumprido (${res.result}).` : `Não deu desta vez (${res.result}). Tente de novo.` });
      }
    }).catch((e) => { setFen(before); setErr(e.message); }).finally(() => setBusy(false));
    return true;
  }

  const modules = [...new Set(positions.map((p) => p.module))];
  const side = cur ? turnOf(cur.fen) : "white";
  return (
    <div>
      <PageHeader title="Finais" purpose="Posições clássicas de teoria jogadas contra o Stockfish até cumprir o objetivo. Use para fixar técnica (oposição, Lucena, Philidor). Para variedade, há também os puzzles de final em Treinar." />
      {err && <div className="mb-4"><ErrorNote>{err}</ErrorNote></div>}
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div className="min-w-0 space-y-5">
          {modules.map((m) => (
            <div key={m}>
              <h2 className="mb-2 text-base">{m}</h2>
              <div className="flex flex-wrap gap-2">{positions.filter((p) => p.module === m).map((p) => (
                <button key={p.id} className={cur?.id === p.id ? "btn-primary" : "btn"} onClick={() => pick(p)}>
                  {p.title} <span className="font-normal opacity-75">({p.goal === "win" ? "vencer" : "empatar"})</span>
                </button>
              ))}</div>
            </div>
          ))}
          <p className="text-sm text-muted">Quer mais finais? <Link className="link" to="/treinar?modo=endgame">Puzzles de final</Link></p>
        </div>
        <div className="min-w-0 space-y-3">
          {cur ? (
            <>
              <Board fen={fen} orientation={side} onMove={onMove} interactive={!busy && !done} lastMove={last} reserve={200} id="endgame" />
              <div className="max-w-prose">
                <p><b>{cur.title}</b>: {cur.goal === "win" ? "vencer" : "empatar"} jogando de {side === "white" ? "Brancas" : "Pretas"}.</p>
                <p className="text-muted">{cur.hint}</p>
                {msg && <p className={`mt-2 font-bold ${msg.ok ? "text-good" : "text-bad"}`}>{msg.text}</p>}
                <button className="btn mt-3" onClick={() => pick(cur)}>Recomeçar</button>
              </div>
            </>
          ) : <Empty title="Escolha uma posição">Cada posição tem um objetivo (vencer ou empatar) e uma dica. O Stockfish joga do outro lado.</Empty>}
        </div>
      </div>
    </div>
  );
}
