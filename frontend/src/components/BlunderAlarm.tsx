import { useEffect } from "react";
import { play } from "../lib/sound";

type Props = {
  verdict: "mistake" | "blunder";
  /** "forte": the whole screen goes red with the word on it; "leve": only a red frame */
  mode: "forte" | "leve";
  onDone: () => void;
};

/** The red after a mistake or a blunder in "Jogar". Crude on purpose: it only says that you got it
 *  wrong. No explanation, no buttons, no way back, and the game never stops for it (clicks go
 *  through and the computer answers at once); what the better move was waits for the end. */
export default function BlunderAlarm({ verdict, mode, onDone }: Props) {
  const blunder = verdict === "blunder";
  useEffect(() => {
    play("wrong");
    const t1 = blunder ? window.setTimeout(() => play("illegal"), 140) : 0;
    try {
      navigator.vibrate?.(blunder ? [180, 60, 180] : 140);
    } catch {
      /* no vibration here */
    }
    const t2 = window.setTimeout(onDone, blunder ? 1300 : 900);
    return () => { window.clearTimeout(t1); window.clearTimeout(t2); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const word = blunder ? "CAPIVARADA" : "ERROU";
  return (
    <>
      <span role="status" className="sr-only">{blunder ? "Capivarada" : "Erro"}</span>
      {mode === "forte" ? (
        <div aria-hidden className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center overflow-hidden"
          style={{ background: "rgba(205, 0, 0, 0.9)" }}>
          <span className="select-none whitespace-nowrap font-black leading-none text-white"
            style={{ fontFamily: "Impact, Haettenschweiler, 'Arial Black', sans-serif", fontSize: blunder ? "15vw" : "22vw",
              transform: "rotate(-4deg)", letterSpacing: "-0.02em" }}>
            {word}
          </span>
        </div>
      ) : (
        <div aria-hidden className="pointer-events-none fixed inset-0 z-50"
          style={{ boxShadow: `inset 0 0 0 ${blunder ? 22 : 14}px rgb(205, 0, 0)` }} />
      )}
    </>
  );
}
