import { useEffect, useState } from "react";
import { Bar, PageHeader, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { dateOnly, pct } from "../lib/format";

export default function Plan() {
  const [p, setP] = useState<any>(null);
  const [cons, setCons] = useState<any>(null);
  const [cfg, setCfg] = useState<any[] | null>(null);
  const loadCons = () => api.get("/api/plan/consistency").then(setCons);
  useEffect(() => { api.get("/api/plan/today").then(setP); loadCons(); }, []);
  if (!p) return <Spinner label="Carregando…" />;
  const total = p.blocks.reduce((s: number, b: any) => s + b.minutes, 0);
  const done = p.blocks.filter((b: any) => b.completed).reduce((s: number, b: any) => s + b.minutes, 0);
  return (
    <div className="max-w-3xl">
      <PageHeader title="Plano do dia" purpose={`Um roteiro de cerca de ${Math.round(total / 60 * 10) / 10} h para ${dateOnly(p.day)}. Marque cada bloco quando terminar: a sequência de dias treinados aparece embaixo.`} />
      {p.light_day_advice.light_day && !p.light_day && (
        <div className="mb-5 rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm">
          As últimas sessões mostram quedas repetidas de desempenho. Um dia mais leve pode render mais.
          <button className="btn btn-sm ml-2" onClick={() => api.post("/api/plan/today/regenerate", { light: true }).then(setP)}>Usar dia leve</button>
        </div>
      )}
      <div className="flex items-center justify-between text-sm"><span>{p.light_day ? "Dia leve" : "Dia completo"}</span><span className="tnum">{done} de {total} min</span></div>
      <div className="mt-2"><Bar value={total ? done / total : 0} tone="good" /></div>
      <ul className="mt-4 divide-y divide-rule border-y border-rule">
        {p.blocks.map((b: any) => (
          <li key={b.id}>
            <label className="flex cursor-pointer items-center gap-3 py-3">
              <input type="checkbox" className="h-5 w-5 accent-[rgb(var(--pen))]" checked={b.completed}
                onChange={(e) => api.post(`/api/plan/blocks/${b.id}`, { completed: e.target.checked }).then((x) => { setP(x); loadCons(); })} />
              <span className={`flex-1 ${b.completed ? "text-faint line-through" : "font-bold"}`}>{b.title}</span>
              <span className="tnum text-muted">{b.minutes} min</span>
            </label>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="btn" onClick={() => api.post("/api/plan/today/regenerate", { light: !p.light_day }).then(setP)}>{p.light_day ? "Usar dia completo" : "Usar dia leve"}</button>
        <button className="btn-quiet" onClick={() => api.get("/api/plan/config").then(setCfg)}>Ajustar os blocos</button>
      </div>
      {cfg && (
        <div className="mt-4 space-y-2 rounded-lg border border-rule p-4">
          {cfg.map((b, i) => (
            <label key={b.key} className="flex items-center gap-3"><span className="flex-1">{b.title}</span>
              <input className="input w-24" type="number" min={0} value={b.minutes} onChange={(e) => setCfg(cfg.map((x, j) => (j === i ? { ...x, minutes: +e.target.value } : x)))} />
              <span className="text-sm text-muted">min</span></label>
          ))}
          <button className="btn-primary" onClick={() => api.put("/api/plan/config", cfg).then(() => setCfg(null))}>Salvar (vale a partir de amanhã)</button>
        </div>
      )}
      {cons && (
        <section className="mt-10">
          <h2>Constância nos últimos 28 dias</h2>
          <div className="mt-3 grid max-w-md grid-cols-7 gap-1.5" role="img" aria-label="Dias treinados">
            {cons.series.map((s: any) => (
              <div key={s.day} title={`${dateOnly(s.day)}: ${s.completed_min} de ${s.planned_min} min`} className="aspect-square rounded"
                style={{ background: s.completion == null ? "rgb(var(--sunk))" : `rgb(var(--good) / ${0.18 + 0.82 * s.completion})` }} />
            ))}
          </div>
          <p className="mt-3 text-sm text-muted">Sequência: {cons.streak_days} {cons.streak_days === 1 ? "dia" : "dias"}. Nesta semana: {cons.days_trained_last_7} de 7 dias, {pct(cons.completion_last_7)} do plano cumprido.</p>
        </section>
      )}
    </div>
  );
}
