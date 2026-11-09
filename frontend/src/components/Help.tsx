import { useEffect, useId, useRef, useState } from "react";
import { HELP } from "../lib/help";

/** A small "?" that opens a plain-language explanation of the metric next to it. */
export default function Help({ id, className = "" }: { id: keyof typeof HELP | string; className?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const pid = useId();
  const h = HELP[id];
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  if (!h) return null;
  return (
    <span ref={ref} className={`relative inline-flex align-middle ${className}`}>
      <button
        type="button"
        aria-label={`O que é: ${h.title}`}
        aria-expanded={open}
        aria-controls={pid}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-rule text-[0.7rem] font-bold leading-none text-faint hover:border-pen hover:text-pen"
      >
        ?
      </button>
      {open && (
        <span
          id={pid}
          role="dialog"
          className="absolute left-1/2 top-7 z-40 w-[min(20rem,80vw)] -translate-x-1/2 rounded-lg border border-rule bg-sheet p-3 text-left text-sm font-normal normal-case leading-relaxed text-ink shadow-lg"
        >
          <span className="mb-1 block font-bold">{h.title}</span>
          {h.text}
        </span>
      )}
    </span>
  );
}
