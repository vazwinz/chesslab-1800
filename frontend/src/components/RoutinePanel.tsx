import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useMeta } from "../lib/meta";
import { RoutineDay } from "../lib/routine";

/** Today's routine: the steps in order, what each one is for, how far you got (counted by the app)
 *  and one button to the next step. The games against the computer come last. */
export default function RoutinePanel({ r, onChange }: { r: RoutineDay; onChange: (r: RoutineDay) => void }) {
  const meta = useMeta();
  const [loop, setLoop] = useState<any>(null);
  const next = r.steps.find((s) => !s.completed) ?? null;
  const done = r.steps.filter((s) => s.completed).length;
  const training = r.steps.filter((s) => s.key !== "games" && !s.completed).length;

  useEffect(() => {
    if (next?.key === "loop") api.get("/api/cognitive/loop").then(setLoop).catch(() => {});
  }, [next?.key]);

  const loopLine = !loop ? null
    : loop.phase === "measure" ? `Agora: medição, ${loop.baseline?.attempts ?? 0} de ${loop.baseline?.needed} puzzles.`
    : loop.phase === "practice" && loop.assignment ? `Agora: ${meta.intervention(loop.assignment.intervention)} para ${meta.dna(loop.assignment.category)}, ${loop.assignment.done} de ${loop.assignment.target}.`
    : loop.phase === "reassess" ? `Agora: reavaliação, ${loop.reassessment?.done ?? 0} de ${loop.reassessment?.needed} puzzles.`
    : null;

  return (
    <section className="panel p-5 sm:p-6" aria-labelledby="routine-title">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="routine-title" className="text-xl">Rotina de hoje{r.light_day ? " · dia leve" : ""}</h2>
        <span className="tnum text-sm text-muted">
          {r.finished ? `feita · ${r.streak_days} ${r.streak_days === 1 ? "dia seguido" : "dias seguidos"}`
            : `${done} de ${r.steps.length} feitos · cerca de ${r.minutes_left} min`}
        </span>
      </div>
      {r.light_day_advice?.light_day && !r.light_day && !r.finished && (
        <p className="mt-2 text-sm text-warn">
          Suas últimas sessões mostram quedas repetidas de desempenho.{" "}
          <button className="link" onClick={() => api.post<RoutineDay>("/api/routine/today/light", { light: true }).then(onChange)}>Usar o dia leve</button>
        </p>
      )}
      <ol className="mt-4 space-y-1.5">
        {r.steps.map((s, i) => {
          const isNext = s.key === next?.key;
          return (
            <li key={s.key} className={`flex items-start gap-3 rounded-lg px-3 py-2.5 ${isNext ? "bg-pen/10 ring-1 ring-pen/40" : ""}`}>
              <span aria-hidden className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
                s.completed ? "bg-good text-white" : isNext ? "bg-pen text-pen-ink" : "bg-sunk text-muted"}`}>{s.completed ? "✓" : i + 1}</span>
              <div className="min-w-0 flex-1">
                <p className={`font-bold ${s.completed ? "text-muted line-through decoration-1" : ""}`}>
                  {s.title}{s.completed && <span className="sr-only"> (feito)</span>}
                </p>
                {isNext && <p className="text-sm text-muted">{s.why}{s.key === "loop" && loopLine ? ` ${loopLine}` : ""}</p>}
              </div>
              <span className="tnum shrink-0 pt-0.5 text-sm text-muted">{Math.min(s.done, s.target)}/{s.target} {s.unit}</span>
              {!s.completed && !isNext && (s.key === "games"
                ? <span className="shrink-0 pt-0.5 text-xs text-faint">no fim</span>
                : <Link className="btn-quiet btn-sm shrink-0" to={s.to}>Ir</Link>)}
            </li>
          );
        })}
      </ol>
      {next ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Link className="btn-primary px-6 py-3 text-base" to={next.to}>{done ? "Continuar" : "Começar"}: {next.title}</Link>
          {next.key === "games" && training === 0 && <span className="text-sm text-muted">Treino feito. Agora as partidas, no seu nível.</span>}
        </div>
      ) : (
        <div className="mt-4 rounded-lg bg-good/10 px-4 py-3">
          <p className="font-bold text-good">Rotina de hoje feita.</p>
          <p className="text-sm text-muted">Amanhã ela começa pelos erros das partidas de hoje. Treinar mais é com você: tudo continua contando.</p>
        </div>
      )}
    </section>
  );
}
