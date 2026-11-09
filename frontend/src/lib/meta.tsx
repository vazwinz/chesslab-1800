import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api } from "./api";

export type Meta = {
  version: string;
  themes: Record<string, { name: string; text: string }>;
  categories: Record<string, string>;
  error_dna: Record<string, { name: string; short: string; how: string; tip: string }>;
  severity: Record<string, string>;
  phases: Record<string, string>;
  interventions: Record<string, { title: string; description: string; targets: string[] }>;
};

const EMPTY: Meta = { version: "", themes: {}, categories: {}, error_dna: {}, severity: {}, phases: {}, interventions: {} };
const MetaCtx = createContext<Meta>(EMPTY);

export function MetaProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta>(EMPTY);
  useEffect(() => {
    api.get<Meta>("/api/meta").then(setMeta).catch(() => {});
  }, []);
  return <MetaCtx.Provider value={meta}>{children}</MetaCtx.Provider>;
}

export function useMeta() {
  const m = useContext(MetaCtx);
  return {
    ...m,
    theme: (k: string) => m.themes[k]?.name ?? k,
    dna: (k: string | null | undefined) => (k ? m.error_dna[k]?.name ?? k : "—"),
    severity: (k: string) => m.severity[k] ?? k,
    intervention: (k: string) => m.interventions[k]?.title ?? k,
  };
}

export const SESSION_KINDS: Record<string, string> = {
  loop: "Treino em ciclo", mixed: "Puzzles mistos", theme: "Um tema", blind: "Cálculo às cegas",
  candidates: "Lances candidatos", retention: "Revisão espaçada", pressure: "Pressão de relógio",
  endgame: "Puzzles de final", own_mistakes: "Meus erros de partida",
};
export const MODE_LABEL: Record<string, string> = {
  standard: "Puzzle", assessment: "Medição", intervention: "Intervenção", retention: "Revisão", pressure: "Pressão",
  blind: "Às cegas", candidates: "Candidatos",
};
export const LOOP_PHASE: Record<string, string> = {
  measure: "medir", diagnose: "diagnosticar", intervene: "intervir", practice: "praticar", reassess: "reavaliar",
  adapt: "adaptar", done: "concluído",
};
export const TIME_CLASS: Record<string, string> = { bullet: "Bullet", blitz: "Blitz", rapid: "Rápidas", daily: "Diárias" };

/** The training modes besides the loop, with when to use each (Train screen and the Guide). */
export const TRAIN_MODES: { kind: string; when: string; help?: string }[] = [
  { kind: "mixed", when: "Puzzles de todos os temas perto do seu nível. Bom para aquecer ou para um treino rápido." },
  { kind: "theme", when: "Um motivo de cada vez (garfos, cravadas, mate de corredor…). Use quando o Diagnóstico apontar um tema fraco." },
  { kind: "blind", when: "Escreva a linha inteira antes de mexer. Use quando você acerta o primeiro lance e erra depois.", help: "blind" },
  { kind: "candidates", when: "Liste até 3 candidatos antes de jogar. Use se você joga o primeiro lance que vê.", help: "candidates" },
  { kind: "retention", when: "Revisa os temas que estão na hora, com posições novas.", help: "retention" },
  { kind: "pressure", when: "Relógio cada vez mais curto. Use se você erra muito com pouco tempo nas partidas.", help: "pressure" },
  { kind: "endgame", when: "Puzzles de final do banco do Lichess." },
  { kind: "own_mistakes", when: "Posições em que você errou nas suas partidas. Ache o lance melhor." },
];
