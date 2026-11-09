import { ARROW_KINDS, ArrowKind } from "../lib/arrows";
import { usePrefs } from "../lib/prefs";

/** Switches for the arrows a board draws, with each arrow's colour as the legend. */
export default function ArrowToggles({ kinds }: { kinds: ArrowKind[] }) {
  const { prefs, set } = usePrefs();
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Setas no tabuleiro">
      <span className="text-xs text-muted">Setas</span>
      {kinds.map((k) => {
        const info = ARROW_KINDS[k];
        const on = Boolean(prefs[info.pref]);
        return (
          <button key={k} type="button" aria-pressed={on} title={`${info.hint} Clique para ${on ? "esconder" : "mostrar"}.`}
            onClick={() => void set({ [info.pref]: !on })}
            className={`chip gap-1.5 transition-colors hover:border-ink/40 ${on ? "text-ink" : "text-faint line-through decoration-1"}`}>
            <span aria-hidden className="inline-block h-1.5 w-4 rounded-full"
              style={{ background: on ? info.color : "rgb(var(--rule))" }} />
            {info.label}
          </button>
        );
      })}
      <span className="hidden text-xs text-faint md:inline">· botão direito marca casas e desenha setas</span>
    </div>
  );
}
