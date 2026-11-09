import { ReactNode } from "react";

/** Tooltip body for Recharts: the value leads, the label follows. */
export function ChartTip({ active, payload, label, value, title }: {
  active?: boolean; payload?: any[]; label?: any;
  value: (v: any, row: any) => ReactNode; title?: (label: any, row: any) => ReactNode;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-lg border border-rule bg-sheet px-3 py-2 text-sm shadow-lg">
      <div className="tnum font-bold text-ink">{value(payload[0].value, row)}</div>
      {title && <div className="text-muted">{title(label, row)}</div>}
    </div>
  );
}

/** The table twin of a chart: every value readable without hovering. */
export function NumbersTable({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  if (!rows.length) return null;
  return (
    <details className="mt-2 text-sm">
      <summary className="cursor-pointer select-none text-muted hover:text-ink">Ver os números</summary>
      <div className="mt-2 max-h-64 overflow-auto rounded-lg border border-rule">
        <table className="tnum w-full text-sm">
          <thead className="sticky top-0 bg-sheet text-left text-muted">
            <tr>{head.map((h, i) => <th key={i} className={`px-3 py-1.5 font-normal ${i ? "text-right" : ""}`}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-rule">
                {r.map((c, j) => <td key={j} className={`px-3 py-1 ${j ? "text-right" : ""}`}>{c}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
