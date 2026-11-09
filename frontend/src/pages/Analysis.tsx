import { Chess } from "chess.js";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import AnalysisBoard from "../components/AnalysisBoard";
import { ErrorNote, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { START_FEN, walk } from "../lib/chess";

export default function Analysis() {
  const [params] = useSearchParams();
  const [start, setStart] = useState(params.get("fen") || START_FEN);
  const [moves, setMoves] = useState<string[]>([]);
  const [current, setCurrent] = useState<{ fen: string; moves: string[]; cursor: number }>({ fen: start, moves: [], cursor: 0 });
  const [fenIn, setFenIn] = useState("");
  const [pgnIn, setPgnIn] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState("");

  const pgn = useMemo(() => {
    try {
      const g = new Chess(start);
      if (start !== START_FEN) {
        g.header("SetUp", "1", "FEN", start);
      }
      for (const s of walk(start, current.moves)) g.move(s.san);
      return g.pgn();
    } catch {
      return "";
    }
  }, [start, current.moves]);

  function loadFen() {
    try {
      new Chess(fenIn.trim());
      setStart(fenIn.trim());
      setMoves([]);
      setErr(null);
    } catch (e: any) {
      setErr(`FEN inválido: ${e.message}`);
    }
  }
  async function loadPgn() {
    try {
      const r = await api.post("/api/board/pgn", { pgn: pgnIn });
      setStart(r.start_fen);
      setMoves(r.moves_uci);
      setErr(null);
    } catch (e: any) {
      setErr(e.message);
    }
  }
  const copy = async (text: string, what: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      setErr("Não consegui copiar. Selecione o texto e use Ctrl+C.");
    }
  };

  return (
    <div>
      <PageHeader title="Análise" help="engine_eval"
        purpose="Um tabuleiro livre com o Stockfish ligado. Use para conferir uma ideia, revisar uma posição de partida ou entender uma linha com o botão Explicar." />
      <AnalysisBoard startFen={start} initialMoves={moves} onPositionChange={(fen, mv, cursor) => setCurrent({ fen, moves: mv, cursor })} />
      <section className="mt-10 grid gap-8 lg:grid-cols-2">
        <div className="space-y-2">
          <h2>Carregar uma posição</h2>
          {err && <ErrorNote>{err}</ErrorNote>}
          <label className="block"><span className="label">FEN</span>
            <div className="flex gap-2"><input className="input text-sm" placeholder="Cole um FEN" value={fenIn} onChange={(e) => setFenIn(e.target.value)} />
              <button className="btn" onClick={loadFen} disabled={!fenIn.trim()}>Carregar</button></div></label>
          <label className="block"><span className="label">PGN</span>
            <textarea className="input h-24 text-sm" placeholder='Cole um PGN (1. e4 e5 2. Nf3 ...)' value={pgnIn} onChange={(e) => setPgnIn(e.target.value)} /></label>
          <div className="flex gap-2">
            <button className="btn" onClick={loadPgn} disabled={pgnIn.trim().length < 2}>Carregar PGN</button>
            <button className="btn-quiet" onClick={() => { setStart(START_FEN); setMoves([]); }}>Posição inicial</button>
          </div>
        </div>
        <div className="space-y-2">
          <h2>Copiar</h2>
          <label className="block"><span className="label">FEN da posição no tabuleiro</span>
            <div className="flex gap-2"><input className="input text-sm" readOnly value={current.fen} />
              <button className="btn" onClick={() => copy(current.fen, "fen")}>{copied === "fen" ? "Copiado" : "Copiar"}</button></div></label>
          <label className="block"><span className="label">PGN da linha</span>
            <textarea className="input h-24 text-sm" readOnly value={pgn} /></label>
          <button className="btn" onClick={() => copy(pgn, "pgn")} disabled={!pgn}>{copied === "pgn" ? "Copiado" : "Copiar PGN"}</button>
        </div>
      </section>
    </div>
  );
}
