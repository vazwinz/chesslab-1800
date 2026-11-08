import { Chess, Square } from "chess.js";
import { useEffect, useMemo, useRef, useState } from "react";
import { Chessboard } from "react-chessboard";

export type Hesitation = { selection_changes: number; cancelled_drags: number; piece_selections: number };

type Props = {
  fen: string;
  orientation?: "white" | "black";
  /** Return false to reject the move (board snaps back). uci like e2e4 or e7e8q */
  onMove?: (uci: string) => boolean | void;
  disabled?: boolean;
  lastMove?: [string, string] | null;
  highlight?: Record<string, React.CSSProperties>;
  onHesitation?: (h: Hesitation) => void;
  hidePieces?: boolean;
};

const LIGHT = "#c9cfc3";
const DARK = "#6f8a63";

/** Interactive board. Rules come from chess.js (legal move generation, check, castling,
 *  en passant, promotion). The server re-validates every move with python-chess. */
export default function Board({ fen, orientation = "white", onMove, disabled, lastMove, highlight, onHesitation, hidePieces }: Props) {
  const game = useMemo(() => {
    try {
      return new Chess(fen);
    } catch {
      return new Chess();
    }
  }, [fen]);
  const [selected, setSelected] = useState<Square | null>(null);
  const [promo, setPromo] = useState<{ from: Square; to: Square } | null>(null);
  const hes = useRef<Hesitation>({ selection_changes: 0, cancelled_drags: 0, piece_selections: 0 });
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(480);

  useEffect(() => {
    setSelected(null);
    setPromo(null);
  }, [fen]);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(Math.min(el.clientWidth, 640)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const report = () => onHesitation?.({ ...hes.current });

  const legalFrom = (sq: Square) => game.moves({ square: sq, verbose: true });

  const isPromotion = (from: Square, to: Square) => {
    const p = game.get(from);
    return !!p && p.type === "p" && (to[1] === "8" || to[1] === "1");
  };

  const tryMove = (from: Square, to: Square, promotion?: string): boolean => {
    const legal = legalFrom(from).find((m) => m.to === to && (!promotion || m.promotion === promotion));
    if (!legal) return false;
    const uci = `${from}${to}${promotion ?? ""}`;
    const ok = onMove?.(uci);
    return ok !== false;
  };

  const onSquareClick = (sq: Square) => {
    if (disabled) return;
    if (selected) {
      if (sq === selected) {
        setSelected(null);
        return;
      }
      const targets = legalFrom(selected).map((m) => m.to);
      if (targets.includes(sq)) {
        if (isPromotion(selected, sq)) {
          setPromo({ from: selected, to: sq });
          return;
        }
        tryMove(selected, sq);
        setSelected(null);
        return;
      }
    }
    const p = game.get(sq);
    if (p && p.color === game.turn()) {
      if (selected && selected !== sq) hes.current.selection_changes += 1;
      hes.current.piece_selections += 1;
      report();
      setSelected(sq);
    } else setSelected(null);
  };

  const onDrop = (from: Square, to: Square, piece: string) => {
    if (disabled) return false;
    if (from === to) {
      hes.current.cancelled_drags += 1;
      report();
      return false;
    }
    const promotion = isPromotion(from, to) ? piece[1]?.toLowerCase() || "q" : undefined;
    const ok = tryMove(from, to, promotion);
    if (!ok) {
      hes.current.cancelled_drags += 1;
      report();
    }
    setSelected(null);
    return ok;
  };

  const styles: Record<string, React.CSSProperties> = {};
  if (lastMove) {
    styles[lastMove[0]] = { background: "rgba(215, 190, 80, 0.35)" };
    styles[lastMove[1]] = { background: "rgba(215, 190, 80, 0.45)" };
  }
  if (game.inCheck()) {
    const board = game.board();
    for (const row of board)
      for (const c of row)
        if (c && c.type === "k" && c.color === game.turn()) styles[c.square] = { background: "radial-gradient(circle, rgba(224,100,92,.85) 0%, rgba(224,100,92,.2) 70%)" };
  }
  if (selected) {
    styles[selected] = { background: "rgba(143, 191, 106, 0.55)" };
    for (const m of legalFrom(selected)) {
      styles[m.to] = m.captured
        ? { background: "radial-gradient(circle, transparent 58%, rgba(20,20,20,.45) 60%)" }
        : { background: "radial-gradient(circle, rgba(20,20,20,.38) 22%, transparent 24%)" };
    }
  }
  Object.assign(styles, highlight ?? {});

  const emptyPieces = useMemo(() => {
    if (!hidePieces) return undefined;
    const blank = () => <div />;
    const o: Record<string, () => JSX.Element> = {};
    for (const c of ["w", "b"]) for (const p of ["P", "N", "B", "R", "Q", "K"]) o[c + p] = blank;
    return o;
  }, [hidePieces]);

  return (
    <div ref={wrap} className="relative w-full max-w-[640px] select-none">
      <Chessboard
        id="main"
        position={fen}
        boardWidth={width}
        boardOrientation={orientation}
        onPieceDrop={onDrop}
        onSquareClick={onSquareClick}
        arePiecesDraggable={!disabled}
        customSquareStyles={styles}
        customDarkSquareStyle={{ backgroundColor: DARK }}
        customLightSquareStyle={{ backgroundColor: LIGHT }}
        customBoardStyle={{ borderRadius: 6, boxShadow: "0 6px 24px rgba(0,0,0,.45)" }}
        animationDuration={150}
        customPieces={emptyPieces as any}
      />
      {promo && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/50">
          <div className="card flex gap-2">
            {["q", "r", "b", "n"].map((p) => (
              <button
                key={p}
                className="btn h-12 w-12 text-2xl"
                onClick={() => {
                  tryMove(promo.from, promo.to, p);
                  setPromo(null);
                  setSelected(null);
                }}
              >
                {{ q: "♛", r: "♜", b: "♝", n: "♞" }[p]}
              </button>
            ))}
            <button className="btn" onClick={() => setPromo(null)}>
              ✕
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
