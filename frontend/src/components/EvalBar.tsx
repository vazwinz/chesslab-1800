import { evalLabel, whiteShare } from "../lib/chess";

/** Vertical evaluation bar: White's share in white on White's side of the board (bottom when White
 *  is below, top when Black is), Black's in dark on the other side. Only drawn from a real Stockfish
 *  score; with no score it stays neutral and unlabeled. */
export default function EvalBar({ cp, mate, orientation, height, depth }: { cp: number | null; mate: number | null;
  orientation: "white" | "black"; height: number; depth?: number | null }) {
  const has = cp != null || mate != null;
  const share = whiteShare(cp, mate);
  const label = has ? evalLabel(cp, mate) : "";
  const whiteAhead = share >= 0.5;
  // the number sits in the leader's part of the bar, in the colour that reads on it
  const leaderBelow = whiteAhead === (orientation === "white");
  return (
    <div className="relative w-6 shrink-0 overflow-hidden rounded-md border border-rule bg-[#262a33]" style={{ height }}
      title={has ? `Stockfish: ${label}${depth ? `, profundidade ${depth}` : ""}` : "Ligue o Stockfish para ver a avaliação"}>
      <div className="absolute inset-x-0 bg-[#f1f2f4] transition-[height] duration-300 ease-out"
        style={{ height: `${has ? share * 100 : 50}%`, [orientation === "white" ? "bottom" : "top"]: 0 }} />
      {has && (
        <span className={`tnum absolute inset-x-0 text-center text-[10px] font-bold ${leaderBelow ? "bottom-1" : "top-1"} ${
          whiteAhead ? "text-[#262a33]" : "text-[#f1f2f4]"}`}>
          {label.replace("+", "")}
        </span>
      )}
    </div>
  );
}
