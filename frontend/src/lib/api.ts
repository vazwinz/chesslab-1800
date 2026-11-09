export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function req<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${BASE}${path}`, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (e: any) {
    if (e?.name === "AbortError") throw e;
    throw new ApiError(0, "Sem conexão com o AURA. Se o problema continuar, feche e abra o app de novo.");
  }
  if (!r.ok) {
    let msg = r.statusText || `Erro ${r.status}`;
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
  get: <T = any>(p: string, signal?: AbortSignal) => req<T>("GET", p, undefined, signal),
  post: <T = any>(p: string, b?: unknown, signal?: AbortSignal) => req<T>("POST", p, b ?? {}, signal),
  put: <T = any>(p: string, b?: unknown) => req<T>("PUT", p, b ?? {}),
  del: <T = any>(p: string) => req<T>("DELETE", p),
};
