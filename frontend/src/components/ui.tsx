import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { san as fmtSan } from "../lib/chess";
import { usePrefs } from "../lib/prefs";
import Help from "./Help";

/** Page title + one sentence saying what the screen is for and when to use it. */
export function PageHeader({ title, purpose, help, actions }: { title: string; purpose: ReactNode; help?: string;
  actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div className="max-w-prose">
        <h1 className="flex items-center gap-2">{title}{help && <Help id={help} />}</h1>
        <p className="mt-1 text-muted">{purpose}</p>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

/** An empty screen always says what to do next, with the button that does it. */
export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-rule px-5 py-6">
      <p className="font-bold">{title}</p>
      {children && <div className="mt-1 max-w-prose text-muted">{children}</div>}
      {action && <div className="mt-3 flex flex-wrap gap-2">{action}</div>}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div role="alert" className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">{children}</div>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-rule border-t-pen" aria-hidden />
      {label}
    </span>
  );
}

/** A labelled number with an optional explanation. */
export function Metric({ label, value, sub, help, tone }: { label: string; value: ReactNode; sub?: ReactNode;
  help?: string; tone?: "good" | "bad" }) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5 text-sm text-muted">{label}{help && <Help id={help} />}</div>
      <div className={`stat mt-1 ${tone === "good" ? "text-good" : tone === "bad" ? "text-bad" : ""}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-faint">{sub}</div>}
    </div>
  );
}

export function Bar({ value, tone = "pen" }: { value: number | null | undefined; tone?: "pen" | "good" | "bad" | "warn" }) {
  const color = { pen: "bg-pen", good: "bg-good", bad: "bg-bad", warn: "bg-warn" }[tone];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunk">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.max(0, Math.min(1, value ?? 0)) * 100}%` }} />
    </div>
  );
}

/** Renders coach text: [[Nf3]] markers become moves in the chosen notation. */
export function RichText({ text, onMove }: { text: string; onMove?: (san: string) => void }) {
  const { prefs } = usePrefs();
  const parts = text.split(/(\[\[[^\]]+\]\])/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[\[([^\]]+)\]\]$/);
        if (!m) return <span key={i}>{p}</span>;
        const label = <SanText san={m[1]} notation={prefs.notation} />;
        return onMove ? (
          <button key={i} type="button" className="move underline decoration-rule decoration-1 underline-offset-2"
            onClick={() => onMove(m[1])}>{label}</button>
        ) : <b key={i} className="whitespace-nowrap">{label}</b>;
      })}
    </>
  );
}

export function SanText({ san, notation }: { san: string; notation?: "figurine" | "letters" }) {
  const { prefs } = usePrefs();
  const s = fmtSan(san, notation ?? prefs.notation);
  const fig = s.match(/^([♔♕♖♗♘])(.*)$/);
  if (!fig) return <span className="whitespace-nowrap">{s}</span>;
  return <span className="whitespace-nowrap"><span className="fig">{fig[1]}</span>{fig[2]}</span>;
}

export function NavButton({ to, children, primary }: { to: string; children: ReactNode; primary?: boolean }) {
  return <Link to={to} className={primary ? "btn-primary" : "btn"}>{children}</Link>;
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void;
  items: { value: T; label: string }[] }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-rule">
      {items.map((it) => (
        <button key={it.value} role="tab" aria-selected={value === it.value} onClick={() => onChange(it.value)}
          className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-bold ${value === it.value
            ? "border-pen text-ink" : "border-transparent text-muted hover:text-ink"}`}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void;
  label: string; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 py-2">
      <input type="checkbox" className="mt-1 h-4 w-4 accent-[rgb(var(--pen))]" checked={checked}
        onChange={(e) => onChange(e.target.checked)} />
      <span>
        <span className="font-bold">{label}</span>
        {hint && <span className="block text-sm text-muted">{hint}</span>}
      </span>
    </label>
  );
}
