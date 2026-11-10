import { useEffect, useState } from "react";
import Board, { BOARD_THEMES } from "../components/Board";
import Help from "../components/Help";
import { Bar, ErrorNote, PageHeader, Spinner, Toggle } from "../components/ui";
import { api } from "../lib/api";
import { duration, num } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { play } from "../lib/sound";

const PREVIEW_FEN = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 6 5";

export default function Settings() {
  return (
    <div className="space-y-12">
      <PageHeader title="Configurações" purpose="Banco de puzzles, aparência, sons, a IA opcional do coach e informações sobre o app." />
      <PuzzlesSection />
      <AppearanceSection />
      <TrainingSection />
      <AiSection />
      <AboutSection />
    </div>
  );
}

function Section({ title, purpose, children }: { title: string; purpose?: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-rule pt-6 lg:grid-cols-[16rem_minmax(0,1fr)] lg:gap-10">
      <div>
        <h2>{title}</h2>
        {purpose && <p className="mt-1 text-sm text-muted">{purpose}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function PuzzlesSection() {
  const [s, setS] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [path, setPath] = useState("");
  const [adv, setAdv] = useState(false);
  const [limit, setLimit] = useState("");
  const [minR, setMinR] = useState("");
  const [maxR, setMaxR] = useState("");
  useEffect(() => {
    const load = () => api.get("/api/setup").then(setS).catch((e) => setErr(e.message));
    load();
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, []);
  async function start(download: boolean) {
    setErr(null);
    try {
      await api.post("/api/setup/import", { download, path: download ? undefined : path,
        limit: limit ? +limit : undefined, min_rating: minR ? +minR : undefined, max_rating: maxR ? +maxR : undefined });
    } catch (e: any) {
      setErr(e.message);
    }
  }
  if (!s) return <Section title="Puzzles"><Spinner /></Section>;
  const imp = s.import;
  const running = imp.status === "running";
  return (
    <Section title="Puzzles" purpose="O banco público do Lichess (licença CC0), importado para este computador.">
      <p className="tnum text-lg"><b>{num(s.puzzles)}</b> puzzles no banco</p>
      <p className="mt-1 max-w-prose text-sm text-muted">O download tem uns 300 MB e a importação leva uns 15 minutos (depende do computador). Dá para treinar com o que já entrou. Rodar de novo depois atualiza o banco com os puzzles novos, sem apagar o seu progresso. Se o download cair, clicar de novo continua de onde parou.</p>
      {err && <div className="mt-3"><ErrorNote>{err}</ErrorNote></div>}
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="btn-primary" disabled={running} onClick={() => start(true)}>{s.puzzles ? "Atualizar puzzles do Lichess" : "Baixar puzzles do Lichess"}</button>
        <button className="btn-quiet" onClick={() => setAdv((v) => !v)}>{adv ? "Esconder opções" : "Mais opções"}</button>
      </div>
      {adv && (
        <div className="mt-3 space-y-3 rounded-lg bg-sunk/50 p-3">
          <div className="grid gap-2 sm:grid-cols-3">
            <label><span className="label">Limite de puzzles</span><input className="input" inputMode="numeric" placeholder="todos" value={limit} onChange={(e) => setLimit(e.target.value)} /></label>
            <label><span className="label">Rating mínimo</span><input className="input" inputMode="numeric" placeholder="sem mínimo" value={minR} onChange={(e) => setMinR(e.target.value)} /></label>
            <label><span className="label">Rating máximo</span><input className="input" inputMode="numeric" placeholder="sem máximo" value={maxR} onChange={(e) => setMaxR(e.target.value)} /></label>
          </div>
          <label className="block"><span className="label">Já tem o arquivo lichess_db_puzzle.csv.zst? Caminho dele:</span>
            <div className="flex gap-2"><input className="input text-sm" placeholder="C:\\Users\\voce\\Downloads\\lichess_db_puzzle.csv.zst" value={path} onChange={(e) => setPath(e.target.value)} />
              <button className="btn" disabled={running || !path} onClick={() => start(false)}>Importar arquivo</button></div></label>
        </div>
      )}
      {imp.status !== "idle" && (
        <div className="mt-4 rounded-lg border border-rule p-3 text-sm">
          <p className="font-bold">
            {imp.status === "failed" ? <span className="text-bad">A importação parou</span> : imp.status === "done" ? <span className="text-good">Importação concluída</span>
              : imp.phase === "download" ? "Baixando do Lichess…" : imp.phase === "import" ? "Importando…" : "Começando…"}
          </p>
          {imp.phase === "download" && running && (
            <>
              <div className="mt-2"><Bar value={imp.total_bytes ? imp.downloaded / imp.total_bytes : 0.05} /></div>
              <p className="tnum mt-1 text-muted">{num(Math.round((imp.downloaded ?? 0) / 1e6))} de {imp.total_bytes ? num(Math.round(imp.total_bytes / 1e6)) : "?"} MB{imp.rate_mb_s ? `, ${String(imp.rate_mb_s).replace(".", ",")} MB/s` : ""}{imp.resumed_from ? " (continuando de onde parou)" : ""}</p>
            </>
          )}
          {(imp.phase === "import" || imp.status === "done") && (
            <p className="tnum mt-1 text-muted">{num(imp.rows_read)} lidos, {num(imp.inserted)} novos, {num(imp.updated)} atualizados, {num(imp.invalid)} inválidos{imp.rows_per_s ? `, ${num(imp.rows_per_s)} por segundo` : ""}{imp.seconds ? `, em ${duration(imp.seconds)}` : ""}</p>
          )}
          {imp.error && <p className="mt-1 text-bad">{imp.error}</p>}
        </div>
      )}
      <p className="mt-4 text-sm text-muted">Motor: {s.engine.ok ? <b className="text-ink">{s.engine.name}</b> : <span className="text-bad">{s.engine.error}</span>}</p>
    </Section>
  );
}

function AppearanceSection() {
  const { prefs, set } = usePrefs();
  return (
    <Section title="Aparência" purpose="Tema do app, cores do tabuleiro e notação. Tudo fica salvo neste computador.">
      <fieldset>
        <legend className="label">Tema</legend>
        <div className="flex flex-wrap gap-2">
          {([["system", "Seguir o sistema"], ["light", "Claro"], ["dark", "Escuro"]] as const).map(([v, l]) => (
            <button key={v} className={prefs.theme === v ? "btn-primary" : "btn"} onClick={() => set({ theme: v })} aria-pressed={prefs.theme === v}>{l}</button>
          ))}
        </div>
      </fieldset>
      <div className="mt-6 grid gap-6 md:grid-cols-[minmax(0,1fr)_240px]">
        <div>
          <fieldset>
            <legend className="label">Tabuleiro</legend>
            <div className="flex flex-wrap gap-2">
              {Object.entries(BOARD_THEMES).map(([k, t]) => (
                <button key={k} onClick={() => set({ board_theme: k as any })} aria-pressed={prefs.board_theme === k}
                  className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-bold ${prefs.board_theme === k ? "border-pen text-ink" : "border-rule text-muted"}`}>
                  <span className="grid h-6 w-6 grid-cols-2 overflow-hidden rounded" aria-hidden>
                    <span style={{ background: t.light }} /><span style={{ background: t.dark }} /><span style={{ background: t.dark }} /><span style={{ background: t.light }} />
                  </span>{t.name}
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset className="mt-5">
            <legend className="label">Notação dos lances</legend>
            <div className="flex flex-wrap gap-2">
              <button className={prefs.notation === "figurine" ? "btn-primary" : "btn"} onClick={() => set({ notation: "figurine" })}>Figuras (♘f3)</button>
              <button className={prefs.notation === "letters" ? "btn-primary" : "btn"} onClick={() => set({ notation: "letters" })}>Letras em inglês (Nf3)</button>
            </div>
          </fieldset>
          <div className="mt-4">
            <Toggle checked={prefs.show_coordinates} onChange={(v) => set({ show_coordinates: v })} label="Mostrar coordenadas no tabuleiro" />
            <Toggle checked={prefs.show_legal_moves} onChange={(v) => set({ show_legal_moves: v })} label="Mostrar os lances possíveis ao escolher uma peça" />
            <label className="block py-2"><span className="font-bold">Velocidade das peças</span>
              <select className="input mt-1 w-auto" value={prefs.animation_ms} onChange={(e) => set({ animation_ms: +e.target.value })}>
                <option value={0}>Sem animação</option><option value={120}>Rápida</option><option value={180}>Normal</option><option value={280}>Lenta</option>
              </select></label>
            <label className="block py-2"><span className="font-bold">Animações</span>
              <select className="input mt-1 w-auto" value={prefs.motion} onChange={(e) => set({ motion: e.target.value as "system" | "on" | "off" })}>
                <option value="system">Seguir o sistema</option><option value="on">Sempre</option><option value="off">Nunca</option>
              </select>
              {prefs.motion === "system" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches && (
                <span className="mt-1 block max-w-prose text-sm text-muted">
                  O sistema está com as animações desligadas, então o AURA também está. Escolha "Sempre" para ter as animações só no AURA.
                </span>
              )}
            </label>
          </div>
        </div>
        <div className="pointer-events-none" aria-hidden><Board fen={PREVIEW_FEN} interactive={false} lastMove={["e1", "g1"]} maxSize={240} reserve={0} id="preview" /></div>
      </div>
    </Section>
  );
}

function TrainingSection() {
  const { prefs, set } = usePrefs();
  const [goal, setGoal] = useState(String(prefs.goal_rating));
  useEffect(() => setGoal(String(prefs.goal_rating)), [prefs.goal_rating]);
  return (
    <Section title="Treino e sons" purpose="Como o treino se comporta e a sua meta.">
      <Toggle checked={prefs.sound} onChange={(v) => { set({ sound: v }); if (v) setTimeout(() => play("move"), 50); }} label="Sons do tabuleiro" hint="Lance, captura, xeque, roque, acerto e erro." />
      {prefs.sound && (
        <label className="flex items-center gap-3 py-1 pl-7 text-sm">Volume
          <input type="range" min={0} max={1} step={0.05} value={prefs.volume} onChange={(e) => set({ volume: +e.target.value })}
            onMouseUp={() => play("capture")} onTouchEnd={() => play("capture")} className="w-40 accent-[rgb(var(--pen))]" />
        </label>
      )}
      <Toggle checked={prefs.auto_next} onChange={(v) => set({ auto_next: v })} label="Ir para o próximo puzzle sozinho depois de um acerto" hint="Bom para o ritmo do grind. Depois de um erro ele sempre espera você." />
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label><span className="label">Meta de rating no Chess.com</span>
          <input className="input w-32" inputMode="numeric" value={goal} onChange={(e) => setGoal(e.target.value)} onBlur={() => +goal >= 400 && set({ goal_rating: +goal })} /></label>
        <label><span className="label">Ritmo da meta</span>
          <select className="input w-auto" value={prefs.goal_time_class} onChange={(e) => set({ goal_time_class: e.target.value as any })}>
            <option value="auto">O que eu mais jogo</option><option value="rapid">Rápidas</option><option value="blitz">Blitz</option><option value="bullet">Bullet</option><option value="daily">Diárias</option>
          </select></label>
      </div>
      <div className="mt-4"><button className="btn" onClick={() => set({ tour_done: false })}>Ver o tour de boas-vindas de novo</button></div>
    </Section>
  );
}

function AiSection() {
  const [s, setS] = useState<any>(null);
  const [provider, setProvider] = useState("none");
  const [url, setUrl] = useState("");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [test, setTest] = useState<any>(null);
  const [testing, setTesting] = useState(false);
  const apply = (x: any) => {
    setS(x);
    setProvider(x.provider);
    setUrl(x.base_url);
    setModel(x.model);
  };
  useEffect(() => {
    api.get("/api/settings/coach").then(apply).catch((e) => setErr(e.message));
  }, []);
  if (!s) return <Section title="IA do coach (opcional)"><Spinner /></Section>;
  const p = s.providers[provider];
  async function save(extra: Record<string, unknown> = {}) {
    setErr(null);
    setMsg(null);
    setTest(null);
    try {
      const r = await api.put("/api/settings/coach", { provider, base_url: url || undefined, model: model || undefined,
        api_key: key ? key : undefined, ...extra });
      apply(r);
      setKey("");
      setMsg(r.note || (provider === "none" ? "IA desligada. O coach usa só as regras." : "Salvo."));
    } catch (e: any) {
      setErr(e.message);
    }
  }
  async function runTest() {
    setTesting(true);
    setTest(null);
    try {
      const r = await api.post("/api/settings/coach/test");
      setTest(r);
    } catch (e: any) {
      setTest({ ok: false, message: e.message });
    } finally {
      setTesting(false);
    }
  }
  return (
    <Section title="IA do coach (opcional)" purpose="O AURA explica os lances sem IA nenhuma. Se quiser, uma IA reescreve a explicação com palavras mais naturais.">
      <div className="max-w-prose space-y-2 text-sm text-muted">
        <p>A IA recebe só os fatos que o Stockfish e o tabuleiro já deram (nenhum número de avaliação) e o AURA confere a resposta: se ela citar um lance que não está nos fatos, escrever um número ou chamar de melhor um lance que o Stockfish não colocou em primeiro, a resposta é descartada e você vê a explicação por regras. <Help id="coach_source" /></p>
      </div>
      <fieldset className="mt-4">
        <legend className="label">Provedor</legend>
        <div className="space-y-1">
          {Object.entries(s.providers).map(([k, v]: any) => (
            <label key={k} className="flex cursor-pointer items-start gap-3 py-1.5">
              <input type="radio" name="provider" className="mt-1 accent-[rgb(var(--pen))]" checked={provider === k}
                onChange={() => { setProvider(k); setUrl(k === s.provider ? s.base_url : v.base_url); setModel(k === s.provider ? s.model : v.default_model || ""); }} />
              <span><span className="font-bold">{v.label}</span>
                {k === "ollama" && <span className="block text-sm text-muted">Grátis e sem internet. Instale em ollama.com, baixe um modelo (ex.: <code>ollama pull qwen2.5:7b</code>) e deixe o Ollama aberto.</span>}
                {k === "anthropic" && <span className="block text-sm text-muted">Use a sua chave de API da Anthropic (console.anthropic.com). Cada explicação é cobrada na sua conta da Anthropic, pelo modelo escolhido; o padrão é o claude-haiku-5-5, o modelo menor da Anthropic.</span>}
                {k === "openai_compatible" && <span className="block text-sm text-muted">LM Studio, OpenRouter, OpenAI ou outro serviço com a API /chat/completions.</span>}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {provider !== "none" && (
        <div className="mt-4 grid max-w-2xl gap-3">
          <label><span className="label">Endereço</span><input className="input text-sm" value={url} onChange={(e) => setUrl(e.target.value)} placeholder={p?.base_url || "https://…"} /></label>
          <label><span className="label">Modelo</span><input className="input text-sm" value={model} onChange={(e) => setModel(e.target.value)} placeholder={p?.model_hint} />
            {test?.models?.length > 0 && (
              <span className="mt-1 flex flex-wrap gap-1">{test.models.slice(0, 12).map((m: string) => (
                <button key={m} type="button" className={`chip ${m === model ? "border-pen text-pen" : ""}`} onClick={() => setModel(m)}>{m}</button>
              ))}</span>
            )}
          </label>
          {(p?.needs_key || provider === "openai_compatible") && (
            <label><span className="label">Chave de API {s.key?.has_key && provider === s.provider && <span className="font-normal">(salva: ••••{s.key.hint}, {s.key.storage})</span>}</span>
              <input className="input text-sm" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)}
                placeholder={s.key?.has_key && provider === s.provider ? "deixe em branco para manter a chave salva" : "cole a chave aqui"} /></label>
          )}
          <p className="text-xs text-muted">A chave fica só neste computador, no arquivo secrets.json da pasta de dados do AURA{navigator.userAgent.includes("Windows") ? ", criptografada com o seu usuário do Windows" : ""}. Ela nunca vai para o banco, para backups ou para a tela, e só é enviada para o endereço acima. Se você trocar o endereço, ela é apagada.</p>
        </div>
      )}
      {err && <div className="mt-3"><ErrorNote>{err}</ErrorNote></div>}
      {msg && <p className="mt-3 text-sm text-good">{msg}</p>}
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="btn-primary" onClick={() => save()}>Salvar</button>
        {s.enabled && <button className="btn" onClick={runTest} disabled={testing}>{testing ? <Spinner label="Testando…" /> : "Testar conexão"}</button>}
        {s.key?.has_key && <button className="btn-quiet" onClick={() => save({ api_key: "" })}>Apagar a chave salva</button>}
      </div>
      {test && <p className={`mt-2 text-sm ${test.ok ? "text-good" : "text-bad"}`}>{test.message}</p>}
    </Section>
  );
}

function AboutSection() {
  const [info, setInfo] = useState<any>(null);
  const [upd, setUpd] = useState<any>(null);
  const [checking, setChecking] = useState(false);
  const { prefs, set } = usePrefs();
  useEffect(() => {
    api.get("/api/app").then(setInfo).catch(() => {});
  }, []);
  async function check() {
    setChecking(true);
    try {
      setUpd(await api.get("/api/update/check?force=true"));
    } finally {
      setChecking(false);
    }
  }
  return (
    <Section title="Sobre e atualizações">
      <p>AURA {info?.version}{info?.previous_version && info.previous_version !== info.version ? ` (atualizado da ${info.previous_version})` : ""}</p>
      <p className="mt-1 text-sm text-muted">Seus dados ficam em <code className="break-all">{info?.data_dir}</code>. Desinstalar o app não apaga essa pasta.</p>
      <Toggle checked={prefs.update_check} onChange={(v) => set({ update_check: v })} label="Avisar quando houver versão nova" hint="Ao abrir, o AURA pergunta ao GitHub qual é a última versão. Sem internet, ele só não avisa." />
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button className="btn" onClick={check} disabled={checking}>{checking ? <Spinner label="Verificando…" /> : "Verificar agora"}</button>
        {upd && (upd.available
          ? <a className="btn-primary" href={upd.download_url} target="_blank" rel="noreferrer">Baixar a versão {upd.latest}</a>
          : <span className="text-sm text-muted">{upd.ok ? "Você está na versão mais recente." : `Não deu para verificar: ${upd.error ?? "sem conexão"}.`}</span>)}
      </div>
      <p className="mt-6 max-w-prose text-xs text-faint">Puzzles: banco público do Lichess (CC0). Motor: Stockfish (GPL-3.0). AURA é software livre sob a GPL-3.0 e não tem ligação com o Lichess, o Chess.com ou a equipe do Stockfish.</p>
    </Section>
  );
}
