import { useEffect, useState } from "react";
import { api } from "../lib/api";

/** What GET /api/alert answers. */
type Alert = { category: string; label: string; text: string; count: number; wrong: number };
export type AlertState = {
  today: Alert | null;
  active: (Alert & { day: string; trend: { before: number; after: number; games_before: number; games_after: number } }) | null;
};

function useAlert() {
  const [state, setState] = useState<AlertState | null>(null);
  useEffect(() => { api.get<AlertState>("/api/alert").then(setState).catch(() => {}); }, []);
  return state;
}

const proof = (a: Alert) => (a.wrong === 1 ? "O erro de hoje foi assim."
  : a.count === a.wrong ? `Os ${a.wrong} erros de hoje foram assim.` : `${a.count} dos ${a.wrong} erros de hoje foram assim.`);

/** The warning of the last day with a session, with how that kind of mistake went in your games since.
 *  Nothing when there is none. */
export default function AlertCard({ compact = false }: { compact?: boolean }) {
  const a = useAlert()?.active;
  if (!a) return null;
  const t = a.trend;
  return (
    <div className={`rounded-lg border border-warn/40 bg-warn/5 ${compact ? "px-3 py-2 text-sm" : "px-4 py-3"}`}>
      <p className="font-bold">{a.text}</p>
      {!compact && (
        <p className="mt-1 text-sm text-muted">
          {t.games_after > 0
            ? <>{a.label}: {t.before} {t.before === 1 ? "vez" : "vezes"} em {t.games_before} partidas até o aviso, {t.after} em {t.games_after} desde então.</>
            : <>{a.label}, na sua última sessão. Ainda não há partidas suas analisadas desde então.</>}
        </p>
      )}
    </div>
  );
}

/** End of today's session: the warning the day's mistakes add up to. */
export function AlertToday() {
  const a = useAlert()?.today;
  if (!a) return null;
  return (
    <div className="rounded-lg border border-warn/40 bg-warn/5 px-3 py-2">
      <p className="font-bold">{a.text}</p>
      <p className="text-sm text-muted">{proof(a)} Amanhã esse aviso aparece no Início e antes de cada partida.</p>
    </div>
  );
}
