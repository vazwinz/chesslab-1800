const nf = new Intl.NumberFormat("pt-BR");

export const num = (x: number | null | undefined) => (x == null ? "—" : nf.format(x));
export const pct = (x: number | null | undefined, d = 0) =>
  x == null ? "—" : `${(x * 100).toLocaleString("pt-BR", { maximumFractionDigits: d, minimumFractionDigits: d })}%`;
export const secs = (ms: number | null | undefined) =>
  ms == null ? "—" : `${(ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s`;
export const clock = (ms: number) => {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
/** ISO from the API (UTC with Z) → local date/time text. */
export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—";
export const dateOnly = (isoDay: string | null | undefined) => {
  if (!isoDay) return "—";
  const [y, m, d] = isoDay.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};
export const dayShort = (isoDay: string) => {
  const [, m, d] = isoDay.slice(0, 10).split("-");
  return `${d}/${m}`;
};
export const plural = (n: number, one: string, many: string) => `${num(n)} ${n === 1 ? one : many}`;
export const duration = (s: number | null | undefined) => {
  if (s == null) return "—";
  if (s < 60) return `${Math.round(s)} s`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
};
