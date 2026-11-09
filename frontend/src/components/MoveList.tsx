import { useEffect, useRef } from "react";
import { SanText } from "./ui";

export type ListMove = { san: string; mark?: "inaccuracy" | "mistake" | "blunder" | null };

const MARK_COLOR = { inaccuracy: "text-warn", mistake: "text-[rgb(var(--warn))]", blunder: "text-bad" } as const;
const MARK_SIGN = { inaccuracy: "?!", mistake: "?", blunder: "??" } as const;

/** Moves laid out like a scoresheet: numbered rows, White and Black columns. `cursor` = number
 *  of moves played on the board (0 = start position). */
export default function MoveList({ moves, cursor, onJump, startTurn = "w", startNumber = 1, maxHeight = 320 }: {
  moves: ListMove[]; cursor: number; onJump: (ply: number) => void; startTurn?: "w" | "b"; startNumber?: number;
  maxHeight?: number }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    box.current?.querySelector("[data-current='true']")?.scrollIntoView({ block: "nearest" });
  }, [cursor]);
  const cells = startTurn === "b" ? [null, ...moves] : moves;
  const rows: (ListMove | null)[][] = [];
  for (let i = 0; i < cells.length; i += 2) rows.push([cells[i], cells[i + 1] ?? null]);
  const offset = startTurn === "b" ? -1 : 0;
  if (!moves.length) return <p className="text-sm text-muted">Nenhum lance ainda. Jogue no tabuleiro.</p>;
  return (
    <div ref={box} className="overflow-y-auto rounded-lg border border-rule" style={{ maxHeight }}>
      <table className="w-full text-sm">
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-rule last:border-0 odd:bg-sunk/40">
              <td className="tnum w-10 py-1 pl-3 text-faint">{startNumber + i}.</td>
              {r.map((m, j) => {
                const ply = i * 2 + j + offset + 1;
                if (!m) return <td key={j} className="w-1/2 py-1" />;
                const current = ply === cursor;
                return (
                  <td key={j} className="w-1/2 py-0.5">
                    <button type="button" data-current={current} onClick={() => onJump(ply)}
                      className={`move w-full justify-start py-1 ${current ? "bg-pen/15 text-ink" : ""}`}>
                      <SanText san={m.san} />
                      {m.mark && <span className={`ml-1 ${MARK_COLOR[m.mark]}`}>{MARK_SIGN[m.mark]}</span>}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
