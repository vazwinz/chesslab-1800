import { useEffect, useState } from "react";
import { api } from "../lib/api";

/** What GET /api/rule answers. */
export type RuleState = {
  suggestion: { category: string; label: string; text: string } | null;
  today: { day: string; category: string; text: string } | null;
  active: {
    day: string; category: string; text: string; label: string;
    trend: { before: number; after: number; games_before: number; games_after: number };
  } | null;
};

export function useRule() {
  const [state, setState] = useState<RuleState | null>(null);
  const reload = () => api.get<RuleState>("/api/rule").then(setState).catch(() => {});
  useEffect(() => { void reload(); }, []);
  return { state, setState, reload };
}

/** The if-then rule in force today (accepted yesterday or before), with how that kind of mistake went
 *  in your games since. Nothing when there is none. */
export default function RuleCard({ compact = false }: { compact?: boolean }) {
  const { state } = useRule();
  const a = state?.active;
  if (!a) return null;
  const t = a.trend;
  return (
    <div className={`rounded-lg border border-pen/40 bg-pen/5 ${compact ? "px-3 py-2 text-sm" : "px-4 py-3"}`}>
      <p className={compact ? "" : "font-bold"}><span className="text-pen">Sua regra de hoje:</span> {a.text}</p>
      {!compact && (
        <p className="mt-1 text-sm text-muted">
          {t.games_after > 0
            ? <>{a.label}: {t.before} {t.before === 1 ? "vez" : "vezes"} em {t.games_before} partidas antes da regra, {t.after} em {t.games_after} desde então.</>
            : <>{a.label}. Ainda não há partidas suas analisadas desde a regra.</>}
        </p>
      )}
    </div>
  );
}

/** End of today's session: the rule the day suggests, to accept as is, edit, or skip. */
export function RuleSuggestion() {
  const { state, setState } = useRule();
  const [text, setText] = useState<string | null>(null);
  const [skipped, setSkipped] = useState(false);
  if (!state || skipped) return null;
  if (state.today) {
    return (
      <div className="rounded-lg border border-rule px-3 py-2 text-sm">
        <span className="text-muted">Sua regra de amanhã:</span> {state.today.text}{" "}
        <button className="link ml-1" onClick={() => api.del<RuleState>("/api/rule").then(setState)}>desfazer</button>
      </div>
    );
  }
  const s = state.suggestion;
  if (!s) return null;
  const value = text ?? s.text;
  return (
    <div className="space-y-2 rounded-lg border border-pen/40 bg-pen/5 p-3">
      <p className="text-sm font-bold">Regra do dia <span className="font-normal text-muted">(o que mais faltou hoje: {s.label})</span></p>
      <input className="input" value={value} onChange={(e) => setText(e.target.value)} aria-label="Regra do dia" />
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary btn-sm" disabled={!value.trim()}
          onClick={() => api.put<RuleState>("/api/rule", { text: value, category: s.category }).then(setState)}>Aceitar</button>
        <button className="btn-quiet btn-sm" onClick={() => setSkipped(true)}>Pular</button>
      </div>
      <p className="text-xs text-muted">Ela aparece amanhã no Início e antes de cada partida no Jogar.</p>
    </div>
  );
}
