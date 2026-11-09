import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { walk } from "../lib/chess";
import Help from "./Help";
import { ErrorNote, RichText, SanText, Spinner } from "./ui";

export type ExplainRequest = { attempt_id?: number; game_mistake_id?: number; fen?: string; move?: string | null };

type Props = {
  request: ExplainRequest;
  /** show a position of the commented line on the board */
  onPreview?: (fen: string, lastMove: [string, string] | null) => void;
  autoLoad?: boolean;
  label?: string;
};

/** The "Explicar" coach: rules from Stockfish facts first (fast), then the optional AI wording. */
export default function Explain({ request, onPreview, autoLoad = false, label = "Explicar" }: Props) {
  const [rules, setRules] = useState<any>(null);
  const [ai, setAi] = useState<any>(null);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [showRules, setShowRules] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const key = JSON.stringify(request);
  const seq = useRef(0);

  useEffect(() => {
    setRules(null);
    setAi(null);
    setErr(null);
    setShowRules(false);
    if (autoLoad) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  async function load() {
    const my = ++seq.current;
    setLoading(true);
    setErr(null);
    try {
      const r = await api.post("/api/coach/explain", { ...request, ai: false });
      if (my !== seq.current) return;
      setRules(r.rules);
      setAiEnabled(r.ai_enabled);
      setLoading(false);
      if (r.ai_enabled && !r.rules.terminal) {
        setAiLoading(true);
        const a = await api.post("/api/coach/explain", { ...request, ai: true });
        if (my !== seq.current) return;
        setAi(a.ai);
      }
    } catch (e: any) {
      if (my === seq.current) setErr(e.message);
    } finally {
      if (my === seq.current) {
        setLoading(false);
        setAiLoading(false);
      }
    }
  }

  if (!rules) {
    return (
      <div className="space-y-2">
        <button className="btn" onClick={load} disabled={loading}>
          {loading ? <Spinner label="O Stockfish está analisando…" /> : label}
        </button>
        {err && <ErrorNote>{err}</ErrorNote>}
      </div>
    );
  }
  if (rules.terminal) return <p className="text-muted">{rules.summary}</p>;

  const s = rules.sections;
  const useAi = ai?.ok && !showRules;
  const a = useAi ? ai.sections : null;
  const best = rules.engine.lines[0];
  const fen0: string = rules.position.fen;
  const steps = walk(fen0, s.line.map((x: any) => x.uci));
  const preview = (sanMove: string) => {
    if (!onPreview) return;
    const i = s.line.findIndex((x: any) => x.san === sanMove);
    if (i >= 0 && steps[i]) onPreview(steps[i].fen, steps[i].lastMove);
  };
  const aiComment = (i: number) => a?.line_comments?.[i]?.comment;

  return (
    <section className="space-y-4" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="inline-flex items-center gap-1.5">
          <span className={`chip ${useAi ? "border-pen/50 text-pen" : ""}`}>
            {useAi ? `IA: ${ai.provider_label.split(",")[0]}, ${ai.model}` : "Explicação por regras"}
          </span>
          <Help id="coach_source" />
        </span>
        <span className="text-faint">fatos do {rules.source.engine}, profundidade {rules.source.depth}</span>
        {ai?.ok && (
          <button className="link text-sm" onClick={() => setShowRules((v) => !v)}>
            {showRules ? "Ver texto da IA" : "Ver explicação por regras"}
          </button>
        )}
        {aiLoading && <Spinner label="A IA está escrevendo…" />}
      </div>
      {aiEnabled && ai && !ai.ok && <p className="text-sm text-warn">{ai.error}</p>}

      <dl className="grid gap-x-6 gap-y-2 rounded-lg bg-sunk/60 p-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted">Melhor lance (Stockfish)</dt>
          <dd className="font-bold"><SanText san={best.san} /> <span className="tnum font-normal text-muted">{best.eval.text}</span></dd>
        </div>
        {s.user && !s.user.is_best && (
          <div>
            <dt className="text-muted">Seu lance</dt>
            <dd className="font-bold"><SanText san={s.user.san} /> <span className="tnum font-normal text-muted">{s.user.eval_user}</span>
              <span className={`ml-2 chip ${s.user.verdict_key === "blunder" ? "border-bad/50 text-bad" : s.user.verdict_key === "good" ? "" : "border-warn/50 text-warn"}`}>{s.user.verdict}</span></dd>
          </div>
        )}
        {rules.engine.lines.length > 1 && (
          <div className="sm:col-span-2">
            <dt className="text-muted">Outras opções</dt>
            <dd>{rules.engine.lines.slice(1).map((l: any) => (
              <span key={l.uci} className="mr-3 whitespace-nowrap"><SanText san={l.san} /> <span className="tnum text-muted">{l.eval.text}</span></span>
            ))}</dd>
          </div>
        )}
      </dl>

      <div className="max-w-prose space-y-3 leading-relaxed">
        <Block title="A ideia"><RichText text={a?.idea || s.idea} onMove={onPreview ? preview : undefined} /></Block>
        {s.user && !s.user.is_best && (
          <Block title="Por que o seu lance foi pior">
            {a?.why_worse ? <p><RichText text={a.why_worse} /></p> : <p><RichText text={s.user.headline} /></p>}
            {!a?.why_worse && s.user.reasons.length > 0 && (
              <ul className="mt-1 list-disc space-y-1 pl-5">{s.user.reasons.map((r: string) => <li key={r}><RichText text={r} /></li>)}</ul>
            )}
          </Block>
        )}
        <Block title="Ameaça do adversário"><RichText text={a?.threat || s.threat} /></Block>
        {s.puzzle_note && <Block title="Solução do puzzle"><RichText text={s.puzzle_note} /></Block>}
        {s.themes.length > 0 && (
          <Block title="Tema tático">
            <ul className="space-y-1">{s.themes.map((t: any) => (
              <li key={t.key}><b>{t.name}</b>{t.source === "detectado" && <span className="text-faint"> (visto no tabuleiro)</span>}: {t.text}</li>
            ))}</ul>
          </Block>
        )}
      </div>

      {s.line.length > 0 && (
        <Block title="Linha principal comentada">
          <ol className="space-y-1 text-sm">
            {s.line.map((m: any, i: number) => (
              <li key={i} className="flex items-baseline gap-2">
                <span className="tnum w-10 shrink-0 text-faint">{m.white ? `${m.move_no}.` : `${m.move_no}…`}</span>
                <button type="button" className="move shrink-0" onClick={() => steps[i] && onPreview?.(steps[i].fen, steps[i].lastMove)}
                  disabled={!onPreview}><SanText san={m.san} /></button>
                <span className="text-muted">{aiComment(i) || m.comment}</span>
              </li>
            ))}
          </ol>
          <p className="mt-2 text-sm text-muted"><RichText text={s.line_end} /></p>
        </Block>
      )}
      {(a?.tip || s.tip) && <p className="max-w-prose rounded-lg border-l-4 border-pen bg-pen/5 px-3 py-2 font-bold">{a?.tip || s.tip}</p>}
    </section>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-0.5 text-sm text-muted">{title}</h3>
      <div>{children}</div>
    </div>
  );
}
