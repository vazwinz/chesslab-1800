import { useEffect, useState } from "react";
import RoutinePanel from "../components/RoutinePanel";
import { PageHeader, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { dateOnly, pct } from "../lib/format";
import { RoutineDay, useRoutine } from "../lib/routine";

export default function Routine() {
  const { routine: r, setRoutine } = useRoutine();
  const [cons, setCons] = useState<any>(null);
  useEffect(() => {
    api.get("/api/routine/consistency").then(setCons).catch(() => {});
  }, [r?.finished, r?.steps.filter((s) => s.completed).length]);
  if (!r) return <Spinner label="Carregando…" />;
  return (
    <div className="max-w-3xl">
      <PageHeader title="Rotina do dia"
        purpose="O que fazer hoje, na ordem, contado pelo próprio app: o treino primeiro e as partidas contra o AURA no fim. Os erros das partidas de hoje abrem a rotina de amanhã." />
      <RoutinePanel r={r} onChange={setRoutine} />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button className="btn" onClick={() => api.post<RoutineDay>("/api/routine/today/light", { light: !r.light_day }).then(setRoutine)}>
          {r.light_day ? "Usar o dia completo" : "Usar o dia leve"}
        </button>
        <span className="text-sm text-muted">O dia leve tira a parte de finais ou repertório, encurta o resto e deixa 1 partida. O que já foi feito continua feito.</span>
      </div>
      {cons && (
        <section className="mt-10">
          <h2>Constância nos últimos 28 dias</h2>
          <div className="mt-3 grid max-w-md grid-cols-7 gap-1.5" role="img" aria-label="Dias treinados">
            {cons.series.map((s: any) => (
              <div key={s.day} title={`${dateOnly(s.day)}: ${s.completed_min} de ${s.planned_min} min`} className="aspect-square rounded"
                style={{ background: s.completion == null ? "rgb(var(--sunk))" : `rgb(var(--good) / ${0.18 + 0.82 * s.completion})` }} />
            ))}
          </div>
          <p className="mt-3 text-sm text-muted">
            Sequência: {cons.streak_days} {cons.streak_days === 1 ? "dia" : "dias"}. Nesta semana: {cons.days_trained_last_7} de 7 dias, {pct(cons.completion_last_7)} da rotina cumprida.
          </p>
        </section>
      )}
    </div>
  );
}
