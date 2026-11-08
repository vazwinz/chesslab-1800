export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not json */
    }
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  get: <T = any>(p: string) => req<T>("GET", p),
  post: <T = any>(p: string, b?: unknown) => req<T>("POST", p, b ?? {}),
  put: <T = any>(p: string, b?: unknown) => req<T>("PUT", p, b ?? {}),
  del: <T = any>(p: string) => req<T>("DELETE", p),
};

export const pct = (x: number | null | undefined, d = 0) => (x == null ? "—" : `${(x * 100).toFixed(d)}%`);
export const fmtMs = (ms: number | null | undefined) => (ms == null ? "—" : `${(ms / 1000).toFixed(1)}s`);
export const CATEGORY_LABEL: Record<string, string> = {
  tactical_blindness: "Tactical blindness",
  calculation_error: "Calculation error",
  missed_opponent_threat: "Missed opponent threat",
  impulsive_decision: "Impulsive decision",
  poor_candidate_selection: "Poor candidate selection",
  positional_misunderstanding: "Positional misunderstanding",
  time_management_failure: "Time-management failure",
  endgame_technique_failure: "Endgame technique failure",
};
