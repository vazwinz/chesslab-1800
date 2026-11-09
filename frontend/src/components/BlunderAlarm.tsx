import { useEffect, useRef } from "react";
import type { Judgment } from "../lib/playStore";
import { play } from "../lib/sound";
import { SanText } from "./ui";

type Props = {
  judgment: Judgment;
  mode: "forte" | "leve";
  canTakeBack: boolean;
  /** the computer will play the punishing reply (it always does after a blunder unless switched off) */
  punishes: boolean;
  onTakeBack: () => void;
  onContinue: () => void;
};

const RED_EDGES = "radial-gradient(ellipse at center, rgba(220, 30, 30, 0.12) 35%, rgba(205, 0, 0, 0.8) 100%)";
const RED_SCREEN = "radial-gradient(ellipse at center, rgba(150, 0, 0, 0.6) 0%, rgba(205, 0, 0, 0.9) 100%)";

/** The red screen after a mistake or a blunder in "Jogar". "forte" covers the screen and waits:
 *  take the move back and find a better one, or go on and face the punishment. "leve" only flashes. */
export default function BlunderAlarm({ judgment: j, mode, canTakeBack, punishes, onTakeBack, onContinue }: Props) {
  const blunder = j.verdict === "blunder";
  const go = useRef<HTMLButtonElement>(null);
  const title = blunder ? "CAPIVARADA!" : "ERRO!";

  useEffect(() => {
    play("wrong");
    const t1 = blunder ? window.setTimeout(() => play("illegal"), 260) : 0;
    try {
      navigator.vibrate?.(blunder ? [140, 70, 140] : 120);
    } catch {
      /* no vibration here */
    }
    if (mode === "leve") {
      const t = window.setTimeout(onContinue, 1200);
      return () => { window.clearTimeout(t); window.clearTimeout(t1); };
    }
    go.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onContinue();
      if (canTakeBack && (e.key === "Backspace" || e.key.toLowerCase() === "z")) { e.preventDefault(); onTakeBack(); }
    };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); window.clearTimeout(t1); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const lost = Math.round(j.win_pct_loss);
  if (mode === "leve") {
    return (
      <>
        <div aria-hidden className="alarm-flash pointer-events-none fixed inset-0 z-50" style={{ background: RED_EDGES }} />
        <div role="status" className="fixed inset-x-0 top-4 z-50 mx-auto w-fit max-w-[92%] rounded-full px-5 py-2 text-center font-bold text-white shadow-xl"
          style={{ background: "rgb(170, 18, 18)" }}>
          {title} <SanText san={j.user_san} />: o melhor era <SanText san={j.best_san} />
        </div>
      </>
    );
  }
  return (
    <div role="alertdialog" aria-modal="true" aria-labelledby="alarm-title" className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div aria-hidden className="alarm-pulse absolute inset-0" style={{ background: RED_SCREEN }} />
      <div className="relative w-full max-w-md rounded-2xl p-6 text-white shadow-2xl"
        style={{ background: "rgb(105, 8, 8)", boxShadow: "0 0 0 4px rgba(255, 90, 90, 0.75), 0 25px 60px rgba(0, 0, 0, 0.5)" }}>
        <p id="alarm-title" className="text-4xl font-black tracking-tight">{title}</p>
        <p className="mt-3 text-lg">Você jogou <b><SanText san={j.user_san} /></b>. O melhor era <b><SanText san={j.best_san} /></b>.</p>
        {j.reply_san && (
          <p className="mt-1">{punishes
            ? <>Se seguir, o AURA joga <b><SanText san={j.reply_san} /></b> e você paga caro.</>
            : <>O lance que pune o seu: <b><SanText san={j.reply_san} /></b>.</>}</p>
        )}
        <p className="mt-2 text-sm" style={{ color: "rgba(255, 255, 255, 0.8)" }}>
          Você jogou fora {lost} {lost === 1 ? "ponto" : "pontos"} da sua chance de vencer.
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          {canTakeBack && (
            <button type="button" onClick={onTakeBack} className="rounded-lg px-4 py-2 font-bold"
              style={{ background: "white", color: "rgb(140, 0, 0)" }}>
              Voltar o lance e achar o melhor
            </button>
          )}
          <button ref={go} type="button" onClick={onContinue}
            className="rounded-lg border-2 px-4 py-2 font-bold text-white hover:bg-white/10" style={{ borderColor: "rgba(255, 255, 255, 0.7)" }}>
            Seguir e aguentar
          </button>
        </div>
        {canTakeBack && (
          <p className="mt-3 text-xs" style={{ color: "rgba(255, 255, 255, 0.7)" }}>
            Voltar o lance tira esta partida do seu nível. Teclas: Z volta o lance, Esc segue.
          </p>
        )}
      </div>
    </div>
  );
}
