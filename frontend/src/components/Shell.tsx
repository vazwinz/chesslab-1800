import { ReactNode, useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { num } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import Icon from "./Icon";
import Tour from "./Tour";

const NAV: { to: string; label: string; icon: string; group: number }[] = [
  { to: "/", label: "Início", icon: "home", group: 0 },
  { to: "/treinar", label: "Treinar", icon: "train", group: 0 },
  { to: "/jogar", label: "Jogar", icon: "play", group: 0 },
  { to: "/partidas", label: "Partidas", icon: "games", group: 0 },
  { to: "/analise", label: "Análise", icon: "analysis", group: 0 },
  { to: "/aberturas", label: "Aberturas", icon: "book", group: 1 },
  { to: "/finais", label: "Finais", icon: "king", group: 1 },
  { to: "/plano", label: "Plano do dia", icon: "plan", group: 1 },
  { to: "/diagnostico", label: "Diagnóstico", icon: "chart", group: 2 },
  { to: "/guia", label: "Como treinar", icon: "guide", group: 3 },
  { to: "/configuracoes", label: "Configurações", icon: "settings", group: 3 },
];
const MOBILE_TABS = ["/", "/treinar", "/jogar", "/partidas", "/analise"];

export default function Shell({ children }: { children: ReactNode }) {
  const { prefs, ready, set, dark } = usePrefs();
  const [health, setHealth] = useState<any>(null);
  const [puzzles, setPuzzles] = useState<number | null>(null);
  const [job, setJob] = useState<any>(null);
  const [drawer, setDrawer] = useState(false);
  const loc = useLocation();

  useEffect(() => setDrawer(false), [loc.pathname]);
  useEffect(() => {
    api.get("/api/health").then(setHealth).catch(() => setHealth({ ok: false }));
    const loadCount = () => api.get("/api/puzzles/stats").then((s) => setPuzzles(s.count)).catch(() => {});
    loadCount();
    const t = setInterval(loadCount, 30000);
    return () => clearInterval(t);
  }, []);
  // background game analysis: a small progress line in the sidebar while it runs
  useEffect(() => {
    let stop = false;
    let timer: number;
    const tick = async () => {
      try {
        const j = await api.get("/api/games/jobs");
        if (!stop) setJob(j);
        timer = window.setTimeout(tick, j.status === "running" ? 2000 : 15000);
      } catch {
        timer = window.setTimeout(tick, 15000);
      }
    };
    tick();
    const wake = () => { window.clearTimeout(timer); tick(); };
    window.addEventListener("aura:job", wake);
    return () => { stop = true; window.clearTimeout(timer); window.removeEventListener("aura:job", wake); };
  }, []);

  const engineOk = health?.engine?.ok;
  const toggleTheme = () => set({ theme: dark ? "light" : "dark" });
  const navItem = (n: (typeof NAV)[number], compact = false) => (
    <NavLink key={n.to} to={n.to} end={n.to === "/"}
      className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-[0.95rem] font-bold transition-colors ${
        isActive ? "bg-pen/10 text-pen" : "text-muted hover:bg-sunk hover:text-ink"} ${compact ? "" : ""}`}>
      <Icon name={n.icon} size={19} />
      {n.label}
    </NavLink>
  );
  const status = (
    <div className="space-y-1 px-3 text-xs text-faint">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${health == null ? "bg-faint" : engineOk ? "bg-good" : "bg-bad"}`} />
        {health == null ? "Verificando o Stockfish…" : engineOk ? health.engine.name : "Stockfish não encontrado"}
      </div>
      {puzzles != null && <div>{num(puzzles)} puzzles no banco</div>}
      {job?.status === "running" && (
        <Link to="/partidas" className="block text-pen">
          {job.phase === "download" ? "Baixando partidas…" : `Analisando partidas ${num(job.done)}/${num(job.total)}`}
        </Link>
      )}
      {health?.version && <div>AURA {health.version}</div>}
    </div>
  );

  return (
    <div className="min-h-screen lg:flex">
      {/* desktop sidebar */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-rule bg-sheet lg:sticky lg:top-0 lg:flex lg:h-screen">
        <Link to="/" className="flex items-center gap-2 px-5 pb-4 pt-5 text-lg font-bold tracking-tight">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-pen text-pen-ink">A</span>AURA
        </Link>
        <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3" aria-label="Seções">
          {NAV.map((n, i) => (
            <div key={n.to} className={i > 0 && NAV[i - 1].group !== n.group ? "mt-4" : ""}>{navItem(n)}</div>
          ))}
        </nav>
        <div className="space-y-3 border-t border-rule py-4">
          {status}
          <div className="flex gap-1 px-2">
            <button className="btn-quiet btn-sm" onClick={toggleTheme} aria-label={dark ? "Usar tema claro" : "Usar tema escuro"}>
              <Icon name={dark ? "sun" : "moon"} size={17} />{dark ? "Tema claro" : "Tema escuro"}
            </button>
            <button className="btn-quiet btn-sm" onClick={() => set({ sound: !prefs.sound })}
              aria-label={prefs.sound ? "Desligar sons" : "Ligar sons"} title={prefs.sound ? "Desligar sons" : "Ligar sons"}>
              <Icon name={prefs.sound ? "sound" : "mute"} size={17} />
            </button>
          </div>
        </div>
      </aside>

      {/* mobile top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-rule bg-sheet/95 px-4 py-2 backdrop-blur lg:hidden">
        <button className="btn-quiet btn-sm -ml-2" onClick={() => setDrawer(true)} aria-label="Abrir menu"><Icon name="menu" /></button>
        <Link to="/" className="font-bold tracking-tight">AURA</Link>
        <button className="btn-quiet btn-sm -mr-2" onClick={toggleTheme} aria-label={dark ? "Usar tema claro" : "Usar tema escuro"}>
          <Icon name={dark ? "sun" : "moon"} />
        </button>
      </header>
      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-label="Menu">
          <div className="absolute inset-0 bg-black/40" onClick={() => setDrawer(false)} />
          <nav className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col gap-0.5 overflow-y-auto bg-sheet p-3 shadow-xl">
            <div className="mb-2 flex items-center justify-between px-2">
              <span className="font-bold">AURA</span>
              <button className="btn-quiet btn-sm" onClick={() => setDrawer(false)} aria-label="Fechar menu"><Icon name="x" /></button>
            </div>
            {NAV.map((n, i) => <div key={n.to} className={i > 0 && NAV[i - 1].group !== n.group ? "mt-3" : ""}>{navItem(n)}</div>)}
            <div className="mt-auto pt-4">{status}</div>
          </nav>
        </div>
      )}

      <main className="min-w-0 flex-1 px-4 pb-24 pt-5 sm:px-6 lg:px-10 lg:pb-10 lg:pt-8">
        <Notices />
        {health && health.ok === false && (
          <div className="mb-4 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
            O AURA não está respondendo. Feche a janela e abra o app de novo.
          </div>
        )}
        <div className="mx-auto max-w-[1280px]">{children}</div>
      </main>

      {/* mobile bottom tabs */}
      <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-6 border-t border-rule bg-sheet/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden" aria-label="Atalhos">
        {MOBILE_TABS.map((to) => {
          const n = NAV.find((x) => x.to === to)!;
          return (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-[0.7rem] font-bold ${isActive ? "text-pen" : "text-muted"}`}>
              <Icon name={n.icon} size={20} />{n.label}
            </NavLink>
          );
        })}
        <button className="flex flex-col items-center gap-0.5 py-2 text-[0.7rem] font-bold text-muted" onClick={() => setDrawer(true)}>
          <Icon name="menu" size={20} />Mais
        </button>
      </nav>
      {ready && !prefs.tour_done && <Tour onClose={() => set({ tour_done: true })} />}
    </div>
  );
}

/** One-time notices: new version available, data migrated from the previous version. */
function Notices() {
  const { prefs, set, ready } = usePrefs();
  const [upd, setUpd] = useState<any>(null);
  const [mig, setMig] = useState<any>(null);
  useEffect(() => {
    api.get("/api/app").then((a) => setMig(a.migration)).catch(() => {});
  }, []);
  useEffect(() => {
    if (!ready || !prefs.update_check) return;
    const t = setTimeout(() => api.get("/api/update/check").then(setUpd).catch(() => {}), 2500);
    return () => clearTimeout(t);
  }, [ready, prefs.update_check]);
  const showUpdate = upd?.available && upd.latest !== prefs.dismissed_version;
  return (
    <div className="mx-auto max-w-[1280px]">
      {showUpdate && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-pen/40 bg-pen/5 px-4 py-2.5">
          <span className="font-bold">Nova versão disponível: {upd.latest}</span>
          <span className="text-sm text-muted">Você está na {upd.current}. Instale por cima: seu progresso é mantido.</span>
          <span className="ml-auto flex gap-2">
            <a className="btn-primary btn-sm" href={upd.download_url} target="_blank" rel="noreferrer"><Icon name="download" size={16} />Baixar</a>
            <button className="btn-quiet btn-sm" onClick={() => set({ dismissed_version: upd.latest })}>Agora não</button>
          </span>
        </div>
      )}
      {mig && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-good/40 bg-good/5 px-4 py-2.5 text-sm">
          <span>Seus dados foram atualizados para esta versão e continuam todos aqui. Antes, o AURA salvou uma cópia de segurança em <code className="break-all">{mig.backup}</code>.</span>
          <button className="btn-quiet btn-sm ml-auto" onClick={() => api.post("/api/app/migration-seen").then(() => setMig(null))}>Ok</button>
        </div>
      )}
    </div>
  );
}
