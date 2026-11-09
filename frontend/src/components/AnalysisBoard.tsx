import { useCallback, useEffect, useMemo, useState } from "react";
import { ARROW_KINDS, isRealThreat, nullMoveFen, pickArrows } from "../lib/arrows";
import { evalLabel, tryMove, turnOf, walk, whiteScore } from "../lib/chess";
import { usePrefs } from "../lib/prefs";
import { moveSound } from "../lib/sound";
import { useEngine } from "../lib/useEngine";
import ArrowToggles from "./ArrowToggles";
import Board from "./Board";
import EvalBar from "./EvalBar";
import Explain from "./Explain";
import Help from "./Help";
import Icon from "./Icon";
import MoveList from "./MoveList";
import { SanText, Spinner } from "./ui";

type Props = {
  startFen: string;
  initialMoves?: string[];
  initialCursor?: number;
  orientation?: "white" | "black";
  /** extra controls in the header row (e.g. "Voltar ao puzzle") */
  header?: React.ReactNode;
  engineOn?: boolean;
  reserve?: number;
  onPositionChange?: (fen: string, moves: string[], cursor: number) => void;
};

/** Free analysis board: play moves for both sides, navigate them, and see Stockfish live
 *  (evaluation bar, best lines, best-move arrow) plus the coach's explanation. */
export default function AnalysisBoard({ startFen, initialMoves = [], initialCursor, orientation: o = "white", header,
  engineOn = true, reserve = 170, onPositionChange }: Props) {
  const [moves, setMoves] = useState<string[]>(initialMoves);
  const [cursor, setCursor] = useState(initialCursor ?? initialMoves.length);
  const [orientation, setOrientation] = useState<"white" | "black">(o);
  const [engine, setEngine] = useState(engineOn);
  const [depth, setDepth] = useState(18);
  const [showExplain, setShowExplain] = useState(false);

  useEffect(() => {
    setMoves(initialMoves);
    setCursor(initialCursor ?? initialMoves.length);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startFen, initialMoves.join(" ")]);
  useEffect(() => setOrientation(o), [o]);

  const steps = useMemo(() => walk(startFen, moves), [startFen, moves]);
  const fen = cursor === 0 ? startFen : steps[cursor - 1]?.fen ?? startFen;
  const lastMove = cursor > 0 ? steps[cursor - 1]?.lastMove ?? null : null;
  const { result, busy, error } = useEngine(fen, engine, depth, 3);
  const { prefs } = usePrefs();
  // the opponent's threat: Stockfish on the same position with the opponent to move (a "pass")
  const threatFen = useMemo(() => (engine && prefs.arrows_opponent ? nullMoveFen(fen) : null), [fen, engine, prefs.arrows_opponent]);
  const { result: threatRes } = useEngine(threatFen, !!threatFen, Math.min(depth, 14), 1);
  useEffect(() => onPositionChange?.(fen, moves, cursor), [fen]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setShowExplain(false), [fen]);

  const onMove = useCallback((uci: string) => {
    const r = tryMove(fen, uci);
    if (!r) return false;
    moveSound(r.move);
    const next = moves[cursor] === uci ? moves : [...moves.slice(0, cursor), uci];
    setMoves(next);
    setCursor(cursor + 1);
    return true;
  }, [fen, moves, cursor]);

  const go = useCallback((c: number) => {
    const n = Math.max(0, Math.min(moves.length, c));
    if (n === cursor + 1 && steps[cursor]) moveSound({ san: steps[cursor].san, flags: steps[cursor].flags });
    setCursor(n);
  }, [moves.length, cursor, steps]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea, select")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return; // Ctrl+F is find, not "flip the board"
      if (e.key === "ArrowLeft") { e.preventDefault(); go(cursor - 1); }
      if (e.key === "ArrowRight") { e.preventDefault(); go(cursor + 1); }
      if (e.key === "Home") go(0);
      if (e.key === "End") go(moves.length);
      if (e.key === "f" || e.key === "F") setOrientation((x) => (x === "white" ? "black" : "white"));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cursor, moves.length, go]);

  const best = result?.lines?.[0];
  const ws = best ? whiteScore(best.cp, best.mate, fen) : { cp: null, mate: null };
  const threat = threatFen && best && !result?.terminal && isRealThreat(best.cp, best.mate, threatRes?.lines?.[0])
    ? threatRes!.lines[0] : null;
  const arrows = engine && result
    ? pickArrows(prefs, [["opponent", threat?.move], ["others", result.lines[2]?.move], ["others", result.lines[1]?.move], ["best", best?.move]])
    : [];
  const [boardPx, setBoardPx] = useState(480);
  const startTurn = turnOf(startFen) === "white" ? "w" : "b";
  const startNo = Number(startFen.split(" ")[5] || 1);
  const prevFen = cursor > 1 ? steps[cursor - 2]?.fen : startFen;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      {/* the board stays in view while the engine lines and the explanation scroll past it */}
      <div className="min-w-0 xl:sticky xl:top-6 xl:self-start">
        {header && <div className="mb-3 flex flex-wrap items-center gap-2">{header}</div>}
        <div className="flex items-start gap-2">
          <EvalBar cp={ws.cp} mate={ws.mate} orientation={orientation} height={boardPx} depth={best?.depth} />
          <div className="min-w-0 flex-1"><Board fen={fen} orientation={orientation} onMove={onMove} lastMove={lastMove} arrows={arrows} reserve={reserve} id="analysis" onSize={setBoardPx} /></div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-1">
          <button className="btn-quiet btn-sm" onClick={() => go(0)} aria-label="Início da partida"><Icon name="first" /></button>
          <button className="btn-quiet btn-sm" onClick={() => go(cursor - 1)} aria-label="Lance anterior"><Icon name="back" /></button>
          <button className="btn-quiet btn-sm" onClick={() => go(cursor + 1)} aria-label="Próximo lance"><Icon name="forward" /></button>
          <button className="btn-quiet btn-sm" onClick={() => go(moves.length)} aria-label="Último lance"><Icon name="last" /></button>
          <button className="btn-quiet btn-sm" onClick={() => setOrientation((x) => (x === "white" ? "black" : "white"))} aria-label="Girar o tabuleiro"><Icon name="flip" /></button>
          <span className="ml-auto text-xs text-faint">Setas ← → navegam · F gira</span>
        </div>
        {engine && <div className="mt-2"><ArrowToggles kinds={["best", "others", "opponent"]} /></div>}
      </div>

      <aside className="min-w-0 space-y-5">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 font-bold">
              <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--pen))]" checked={engine} onChange={(e) => setEngine(e.target.checked)} />
              Stockfish
            </label>
            <Help id="engine_eval" />
            {engine && (
              <select className="input ml-auto w-auto py-1 text-sm" value={depth} onChange={(e) => setDepth(+e.target.value)} aria-label="Profundidade">
                {[12, 16, 18, 22, 26].map((d) => <option key={d} value={d}>Profundidade {d}</option>)}
              </select>
            )}
          </div>
          {engine && (
            <div className="mt-2 space-y-1">
              {busy && !result && <Spinner label="Analisando…" />}
              {error && <p className="text-sm text-bad">{error}</p>}
              {result?.terminal && <p className="text-sm text-muted">Fim de partida: {result.result}</p>}
              {result?.lines.map((l, i) => {
                const w = whiteScore(l.cp, l.mate, fen);
                return (
                  <button key={i} type="button" onClick={() => onMove(l.move)}
                    className="flex w-full items-baseline gap-2 rounded-lg px-2 py-1 text-left text-sm hover:bg-sunk">
                    <span className={`tnum w-14 shrink-0 font-bold ${i === 0 ? "text-pen" : "text-muted"}`}>{evalLabel(w.cp, w.mate)}</span>
                    <span className="truncate text-muted">
                      {l.pv_san.slice(0, 8).map((s, k) => <span key={k} className={k === 0 ? "font-bold text-ink" : ""}><SanText san={s} /> </span>)}
                    </span>
                  </button>
                );
              })}
              {threat && prefs.arrows_opponent && (
                <p className="flex items-center gap-2 px-2 text-sm">
                  <span aria-hidden className="inline-block h-1.5 w-5 shrink-0 rounded-full" style={{ background: ARROW_KINDS.opponent.color }} />
                  <span className="text-muted">Ameaça do adversário, se fosse a vez dele:</span> <b><SanText san={threat.san} /></b>
                </p>
              )}
              {result && <p className="px-2 text-xs text-faint">{result.engine}, profundidade {best?.depth ?? "—"}{busy ? " · atualizando" : ""}</p>}
            </div>
          )}
        </div>

        <div>
          <h3 className="mb-2 text-sm text-muted">Lances</h3>
          <MoveList moves={steps.map((s) => ({ san: s.san }))} cursor={cursor} onJump={go} startTurn={startTurn} startNumber={startNo} />
        </div>

        <div>
          {!showExplain ? (
            <button className="btn" onClick={() => setShowExplain(true)}>{cursor > 0 ? "Explicar o último lance" : "Explicar a posição"}</button>
          ) : (
            <Explain autoLoad request={cursor > 0 && prevFen ? { fen: prevFen, move: moves[cursor - 1] } : { fen }} />
          )}
        </div>
      </aside>
    </div>
  );
}
