import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { num } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { ErrorNote } from "./ui";

/** First-run tour. The steps are a real sequence: puzzles → your games → start the loop. */
export default function Tour({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [setup, setSetup] = useState<any>(null);
  const [user, setUser] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [gamesStarted, setGamesStarted] = useState(false);
  const { set } = usePrefs();
  const nav = useNavigate();

  useEffect(() => {
    const load = () => api.get("/api/setup").then(setSetup).catch(() => {});
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, []);

  // Esc skips the tour, like the "Pular o tour" button
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const imp = setup?.import ?? {};
  const importing = imp.status === "running";
  const hasPuzzles = (setup?.puzzles ?? 0) > 0;

  async function downloadPuzzles() {
    setErr(null);
    try {
      await api.post("/api/setup/import", { download: true });
    } catch (e: any) {
      setErr(e.message);
    }
  }
  async function importGames() {
    setErr(null);
    try {
      await api.post("/api/games/import/chesscom", { username: user.trim(), months: 3, analyze: true });
      await set({ chesscom_username: user.trim() });
      window.dispatchEvent(new Event("aura:job"));
      setGamesStarted(true);
    } catch (e: any) {
      setErr(e.message);
    }
  }
  function startLoop() {
    onClose();
    nav("/treinar?modo=loop");
  }

  const steps = [
    {
      title: "Bem-vindo ao AURA",
      body: (
        <>
          <p>O AURA é um treino de xadrez feito para uma meta: chegar aos 1800 no Chess.com. Tudo roda no seu computador, e o Stockfish confere cada lance.</p>
          <p className="mt-2">São três passos rápidos para começar. Você pode pular e fazer depois em <b>Configurações</b> e <b>Partidas</b>.</p>
        </>
      ),
    },
    {
      title: "1. Baixe os puzzles",
      body: (
        <>
          <p>Os puzzles vêm do banco público do Lichess (alguns milhões de posições de partidas reais). O download tem uns 300 MB e a importação leva uns 15 minutos (depende do computador). Dá para seguir para o próximo passo enquanto isso.</p>
          <div className="mt-3 rounded-lg bg-sunk/70 p-3 text-sm">
            {hasPuzzles && !importing && <p className="font-bold text-good">{num(setup.puzzles)} puzzles prontos.</p>}
            {importing && (
              <p>{imp.phase === "download"
                ? `Baixando… ${num(Math.round((imp.downloaded ?? 0) / 1e6))} de ${imp.total_bytes ? num(Math.round(imp.total_bytes / 1e6)) : "?"} MB`
                : `Importando… ${num(imp.inserted ?? 0)} puzzles até agora`}</p>
            )}
            {imp.status === "failed" && <p className="text-bad">{imp.error}</p>}
            {!hasPuzzles && !importing && <button className="btn-primary" onClick={downloadPuzzles}>Baixar puzzles do Lichess</button>}
          </div>
        </>
      ),
    },
    {
      title: "2. Traga as suas partidas",
      body: (
        <>
          <p>As suas partidas são a medida principal: o AURA analisa cada lance seu com o Stockfish e descobre que tipo de erro mais se repete. Também lê o seu rating real nos cabeçalhos das partidas.</p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="min-w-[12rem] flex-1">
              <span className="label">Seu usuário no Chess.com</span>
              <input className="input" value={user} onChange={(e) => setUser(e.target.value)} placeholder="ex.: vazwinz" autoComplete="off" />
            </label>
            <button className="btn-primary" disabled={user.trim().length < 2 || gamesStarted} onClick={importGames}>
              {gamesStarted ? "Importando em segundo plano" : "Importar os últimos 3 meses"}
            </button>
          </div>
          <p className="mt-2 text-sm text-muted">A análise roda em segundo plano e você pode treinar enquanto isso. Joga no Lichess ou outro site? Cole o PGN na tela Partidas.</p>
        </>
      ),
    },
    {
      title: "3. Comece o ciclo",
      body: (
        <>
          <p>O <b>Treino em ciclo</b> é o modo principal. Ele mede você com 20 puzzles variados, descobre o seu erro mais recorrente, passa 30 exercícios feitos para esse erro, mede de novo e guarda o que funcionou.</p>
          <p className="mt-2">Depois de cada puzzle, use <b>Explicar</b> para ver a ideia do lance, a ameaça e por que o seu lance foi pior. O guia <b>Como treinar</b> no menu explica cada número do app.</p>
        </>
      ),
    },
  ];
  const last = step === steps.length - 1;

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/45 p-0 sm:items-center sm:p-6" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      <div className="w-full max-w-xl rounded-t-2xl border border-rule bg-sheet p-6 shadow-2xl sm:rounded-2xl">
        <div className="mb-4 flex gap-1.5" aria-hidden>
          {steps.map((_, i) => <span key={i} className={`h-1 flex-1 rounded-full ${i <= step ? "bg-pen" : "bg-sunk"}`} />)}
        </div>
        <h2 id="tour-title" className="text-xl">{steps[step].title}</h2>
        <div className="mt-2 leading-relaxed text-ink">{steps[step].body}</div>
        {err && <div className="mt-3"><ErrorNote>{err}</ErrorNote></div>}
        <div className="mt-6 flex flex-wrap items-center gap-2">
          <button className="btn-quiet" onClick={onClose}>Pular o tour</button>
          <span className="ml-auto flex gap-2">
            {step > 0 && <button className="btn" onClick={() => setStep(step - 1)}>Voltar</button>}
            {!last && <button className="btn-primary" onClick={() => setStep(step + 1)}>Próximo</button>}
            {last && <button className="btn-primary" onClick={startLoop} disabled={!hasPuzzles}>{hasPuzzles ? "Começar o ciclo" : "Espere os puzzles"}</button>}
            {last && !hasPuzzles && <button className="btn" onClick={onClose}>Fechar</button>}
          </span>
        </div>
      </div>
    </div>
  );
}
