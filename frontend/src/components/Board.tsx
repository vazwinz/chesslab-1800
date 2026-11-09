import { Chess, Square } from "chess.js";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Chessboard } from "react-chessboard";
import type { Arrow, PromotionPieceOption } from "react-chessboard/dist/chessboard/types";
import { usePrefs } from "../lib/prefs";
import { play } from "../lib/sound";

export type Hesitation = { selection_changes: number; cancelled_drags: number; piece_selections: number };
export type Badge = { square: string; kind: "good" | "bad" | "best" };

export const BOARD_THEMES: Record<string, { name: string; light: string; dark: string }> = {
  grafite: { name: "Grafite", light: "#DDE4EC", dark: "#8197B5" },
  torneio: { name: "Torneio", light: "#E9EDD7", dark: "#779868" },
  madeira: { name: "Madeira", light: "#EBD8B8", dark: "#B1875F" },
  oceano: { name: "Oceano", light: "#D9E8E6", dark: "#5F9590" },
};

type Props = {
  fen: string;
  orientation?: "white" | "black";
  /** called with a legal move (uci, e.g. e2e4 or e7e8q); return false to refuse it */
  onMove?: (uci: string) => boolean | void;
  interactive?: boolean;
  lastMove?: [string, string] | null;
  arrows?: Arrow[];
  badges?: Badge[];
  onHesitation?: (h: Hesitation) => void;
  /** pixels to keep free below the board (controls); the board never gets taller than the window */
  reserve?: number;
  maxSize?: number;
  id?: string;
  /** reports the board's size in pixels (e.g. to match an evaluation bar) */
  onSize?: (px: number) => void;
};

const SEL = "rgba(250, 210, 80, 0.72)";
const LAST = "rgba(250, 210, 80, 0.5)";
const MARK = "rgba(226, 84, 66, 0.72)";
const DOT = "radial-gradient(circle, rgba(16, 24, 40, 0.26) 21%, transparent 23%)";
const RING = "radial-gradient(circle, transparent 66%, rgba(16, 24, 40, 0.26) 67%, rgba(16, 24, 40, 0.26) 80%, transparent 81%)";
const CHECK = "radial-gradient(circle, rgba(255, 50, 40, 0.95) 0%, rgba(230, 20, 10, 0.6) 32%, rgba(200, 0, 0, 0) 74%)";

export default function Board({ fen, orientation = "white", onMove, interactive = true, lastMove, arrows, badges,
  onHesitation, reserve = 150, maxSize = 780, id = "aura", onSize }: Props) {
  const { prefs, dark } = usePrefs();
  const theme = BOARD_THEMES[prefs.board_theme] ?? BOARD_THEMES.grafite;
  const game = useMemo(() => {
    try {
      return new Chess(fen);
    } catch {
      return new Chess();
    }
  }, [fen]);
  const [selected, setSelected] = useState<Square | null>(null);
  const [promo, setPromo] = useState<{ from: Square; to: Square } | null>(null);
  const [marks, setMarks] = useState<Set<string>>(new Set());
  const hes = useRef<Hesitation>({ selection_changes: 0, cancelled_drags: 0, piece_selections: 0 });
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    setSelected(null);
    setPromo(null);
    setMarks(new Set());
  }, [fen]);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const measure = () => {
      const byHeight = Math.max(260, window.innerHeight - reserve);
      setWidth(Math.floor(Math.max(240, Math.min(el.clientWidth, byHeight, maxSize))));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [reserve, maxSize]);

  useEffect(() => {
    if (width) onSize?.(width);
  }, [width, onSize]);

  const report = () => onHesitation?.({ ...hes.current });
  const legalFrom = useCallback((sq: Square) => game.moves({ square: sq, verbose: true }), [game]);
  const isPromotion = (from: Square, to: Square) => {
    const p = game.get(from);
    return !!p && p.type === "p" && (to[1] === "8" || to[1] === "1");
  };
  const mine = (sq: Square) => {
    const p = game.get(sq);
    return !!p && p.color === game.turn();
  };

  const submit = (from: Square, to: Square, promotion?: string): boolean => {
    const legal = legalFrom(from).find((m) => m.to === to && (!promotion || m.promotion === promotion));
    if (!legal) {
      play("illegal");
      return false;
    }
    const ok = onMove?.(`${from}${to}${promotion ?? ""}`);
    return ok !== false;
  };

  const onSquareClick = (sq: Square) => {
    if (marks.size) setMarks(new Set());
    if (!interactive) return;
    if (selected) {
      if (sq === selected) {
        setSelected(null);
        return;
      }
      if (legalFrom(selected).some((m) => m.to === sq)) {
        if (isPromotion(selected, sq)) {
          setPromo({ from: selected, to: sq });
          return;
        }
        submit(selected, sq);
        setSelected(null);
        return;
      }
    }
    if (mine(sq)) {
      if (selected && selected !== sq) hes.current.selection_changes += 1;
      hes.current.piece_selections += 1;
      report();
      setSelected(sq);
    } else setSelected(null);
  };

  const onDrop = (from: Square, to: Square, piece: string) => {
    if (!interactive) return false;
    setSelected(null);
    if (from === to) {
      hes.current.cancelled_drags += 1;
      report();
      return false;
    }
    const promotion = isPromotion(from, to) ? piece[1]?.toLowerCase() || "q" : undefined;
    const ok = submit(from, to, promotion);
    if (!ok) {
      hes.current.cancelled_drags += 1;
      report();
    }
    return ok;
  };

  const onPromotionPick = (piece?: PromotionPieceOption, from?: Square, to?: Square) => {
    const f = from ?? promo?.from;
    const t = to ?? promo?.to;
    setPromo(null);
    setSelected(null);
    if (!piece || !f || !t) return false;
    return submit(f, t, piece[1].toLowerCase());
  };

  const onRightClick = (sq: Square) => {
    setMarks((m) => {
      const n = new Set(m);
      if (n.has(sq)) n.delete(sq);
      else n.add(sq);
      return n;
    });
  };

  const styles: Record<string, React.CSSProperties> = {};
  if (lastMove) {
    styles[lastMove[0]] = { background: LAST };
    styles[lastMove[1]] = { background: LAST };
  }
  if (game.inCheck()) {
    for (const row of game.board())
      for (const c of row) if (c && c.type === "k" && c.color === game.turn()) styles[c.square] = { background: CHECK };
  }
  for (const m of marks) styles[m] = { background: MARK };
  if (selected) {
    styles[selected] = { background: SEL };
    if (prefs.show_legal_moves) {
      for (const m of legalFrom(selected)) {
        const base = styles[m.to]?.background;
        const g = m.captured ? RING : DOT;
        styles[m.to] = { background: base ? `${g}, ${base}` : g };
      }
    }
  }

  const sq = width / 8;
  const pos = (square: string) => {
    const f = square.charCodeAt(0) - 97;
    const r = Number(square[1]) - 1;
    return orientation === "white" ? { x: f * sq, y: (7 - r) * sq } : { x: (7 - f) * sq, y: r * sq };
  };
  const arrowColor = dark ? "rgba(255, 176, 60, 0.85)" : "rgba(240, 150, 30, 0.85)";

  return (
    <div ref={wrap} className="relative w-full min-w-0 select-none" style={{ minHeight: width || 260 }}>
      {width > 0 && (
        <div className="relative" style={{ width, height: width }}>
          <Chessboard
            id={id}
            position={fen}
            boardWidth={width}
            boardOrientation={orientation}
            onPieceDrop={onDrop}
            onSquareClick={onSquareClick}
            onSquareRightClick={onRightClick}
            onPieceDragBegin={(_p, s) => {
              if (interactive && mine(s as Square)) setSelected(s as Square);
            }}
            onPromotionPieceSelect={onPromotionPick}
            showPromotionDialog={!!promo}
            promotionToSquare={promo?.to ?? null}
            isDraggablePiece={({ sourceSquare }) => interactive && mine(sourceSquare as Square)}
            arePiecesDraggable={interactive}
            customArrows={arrows}
            customArrowColor={arrowColor}
            customSquareStyles={styles}
            customDarkSquareStyle={{ backgroundColor: theme.dark }}
            customLightSquareStyle={{ backgroundColor: theme.light }}
            customDropSquareStyle={{ boxShadow: "inset 0 0 0 4px rgba(255,255,255,0.75)" }}
            customBoardStyle={{ borderRadius: "6px", boxShadow: "var(--shadow-board)" }}
            customNotationStyle={{ fontSize: `${Math.max(10, Math.round(width / 46))}px`, fontWeight: "700" }}
            showBoardNotation={prefs.show_coordinates}
            animationDuration={prefs.animation_ms}
            snapToCursor
          />
          {badges?.map((b) => {
            const p = pos(b.square);
            const size = Math.max(18, sq * 0.36);
            const color = b.kind === "bad" ? "rgb(var(--bad))" : b.kind === "best" ? "rgb(var(--pen))" : "rgb(var(--good))";
            return (
              <span key={b.square + b.kind} aria-hidden
                className="badge-pop pointer-events-none absolute z-20 flex items-center justify-center rounded-full text-white shadow-md"
                style={{ left: p.x + sq - size * 0.72, top: p.y - size * 0.28, width: size, height: size, background: color,
                  fontSize: size * 0.62, fontWeight: 800, lineHeight: 1 }}>
                {b.kind === "bad" ? "✕" : b.kind === "best" ? "★" : "✓"}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
