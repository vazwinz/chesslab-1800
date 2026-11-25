/** Your chance of winning through the game (Stockfish, your side), with the moments marked and the
 *  seconds you spent on each of your moves underneath. Click anywhere to go to that position. */
type Moment = { ply: number; kind: string };

const KIND_CLASS: Record<string, string> = {
  decisive: "text-bad", missed: "text-warn", common: "text-muted", great: "text-pen", brilliant: "text-brill",
};

export default function WinGraph({ wins, think, cursor, moments, onJump }: {
  wins: number[]; think: (number | null)[]; cursor: number; moments: Moment[]; onJump: (cursor: number) => void;
}) {
  const n = wins.length;
  if (n < 2) return null;
  const W = 600, H = 90, BH = 20, GAP = 4;
  const x = (i: number) => (i / (n - 1)) * W;
  const y = (w: number) => H - (Math.max(0, Math.min(100, w)) / 100) * H;
  const line = wins.map((w, i) => `${x(i).toFixed(1)},${y(w).toFixed(1)}`).join(" ");
  const times = think.map((t) => t ?? 0);
  const maxT = Math.max(1, ...times);
  const click = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    onJump(Math.round(((e.clientX - r.left) / r.width) * (n - 1)));
  };
  const hasThink = times.some((t) => t > 0);
  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W} ${H + (hasThink ? BH + GAP : 0)}`} className="w-full cursor-pointer select-none" onClick={click}
        role="img" aria-label="Sua chance de vitória ao longo da partida. Clique para ir àquele lance.">
        <rect x={0} y={0} width={W} height={H} className="fill-[rgb(var(--sunk))]" />
        <line x1={0} x2={W} y1={H / 2} y2={H / 2} className="stroke-[rgb(var(--rule))]" strokeDasharray="4 4" />
        <polygon points={`0,${H} ${line} ${W},${H}`} className="fill-[rgb(var(--pen)/0.18)]" />
        <polyline points={line} fill="none" className="stroke-[rgb(var(--pen))]" strokeWidth={1.5} />
        <line x1={x(cursor)} x2={x(cursor)} y1={0} y2={H} className="stroke-[rgb(var(--ink)/0.5)]" strokeWidth={1} />
        {moments.map((m) => {
          const i = Math.min(n - 1, m.ply + 1);
          return (
            <g key={`${m.ply}-${m.kind}`} className={KIND_CLASS[m.kind] ?? "text-muted"}>
              <circle cx={x(i)} cy={y(wins[i])} r={4} fill="currentColor" stroke="rgb(var(--paper))" strokeWidth={1} />
            </g>
          );
        })}
        {hasThink && times.map((t, ply) => t > 0 && (
          <rect key={ply} x={x(Math.min(n - 1, ply + 1)) - 1.5} width={3} y={H + GAP + BH - (t / maxT) * BH}
            height={(t / maxT) * BH} className="fill-[rgb(var(--muted)/0.6)]" />
        ))}
      </svg>
      <figcaption className="mt-1 text-xs text-muted">
        Sua chance de vitória a cada lance{hasThink ? "; as barras embaixo são o tempo que você pensou" : ""}. Clique para ir ao lance.
      </figcaption>
    </figure>
  );
}
