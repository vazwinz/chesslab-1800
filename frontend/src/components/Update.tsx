import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { num } from "../lib/format";
import Icon from "./Icon";
import { Bar, Spinner } from "./ui";

/** What /api/update/check answers. */
export type UpdateInfo = {
  current: string;
  available: boolean;
  ok?: boolean;
  error?: string;
  latest?: string;
  download_url?: string;
  page_url?: string;
  install?: { possible: boolean; reason: string | null; asset: string | null; size: number | null };
  last_attempt?: { version: string; message: string; log: string } | null;
};

type Job = {
  status: "idle" | "running" | "failed" | "restarting";
  phase?: "download" | "verify" | "prepare" | "restart" | null;
  downloaded?: number;
  total_bytes?: number;
  version?: string;
  error?: string;
};

const mb = (bytes: number | undefined) => num(Math.round((bytes ?? 0) / 1e6));
const UPDATE_EVENT = "aura:update"; // the notice and Configurações show the same job

/** "Atualizar agora": a one-line confirmation, then the download with its progress; the app then
 *  closes, installs the new version and opens again. "Baixar" stays as the way out, and is the
 *  only button when this copy cannot update itself (running from source, the portable zip…). */
export function UpdateActions({ upd, onLater, onStart }: { upd: UpdateInfo; onLater?: () => void; onStart?: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [gone, setGone] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const last = useRef<Job | null>(null);
  last.current = job;

  useEffect(() => {
    const load = () => api.get<Job>("/api/update/job").then((j) => j.status !== "idle" && setJob(j)).catch(() => {});
    load(); // a job already under way (another screen started it) shows its progress here too
    window.addEventListener(UPDATE_EVENT, load);
    return () => window.removeEventListener(UPDATE_EVENT, load);
  }, []);

  const active = job?.status === "running" || job?.status === "restarting";
  useEffect(() => {
    if (!active) return;
    let stop = false;
    let misses = 0;
    let timer: number;
    const tick = async () => {
      try {
        const j = await api.get<Job>("/api/update/job");
        misses = 0;
        if (stop) return;
        setJob(j);
        if (j.status !== "running" && j.status !== "restarting") return;
      } catch {
        // the server stops answering when the app closes for the update
        if (last.current?.status === "restarting" || ++misses >= 2) {
          if (!stop) setGone(true);
          return;
        }
      }
      if (!stop) timer = window.setTimeout(tick, 400);
    };
    timer = window.setTimeout(tick, 400);
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, [active]);

  async function start() {
    setConfirming(false);
    setErr(null);
    try {
      setJob(await api.post<Job>("/api/update/start"));
      window.dispatchEvent(new Event(UPDATE_EVENT));
      onStart?.();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function cancel() {
    try {
      setJob(await api.post<Job>("/api/update/cancel"));
    } catch {
      /* the next poll shows where it is */
    }
  }

  if (gone) return <span className="text-sm">O AURA fechou para se atualizar e abre de novo sozinho em alguns segundos.</span>;
  if (job?.status === "restarting") return <Spinner label="Fechando o AURA para atualizar…" />;
  if (job?.status === "running") {
    const total = job.total_bytes || upd.install?.size || 0;
    const downloading = job.phase === "download";
    return (
      <span className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 sm:w-auto">
        <span className="min-w-[14rem] flex-1">
          <span className="flex items-baseline justify-between gap-3 text-sm">
            <span>{downloading ? `Baixando a versão ${job.version}…` : job.phase === "verify" ? "Conferindo o arquivo…" : "Preparando a instalação…"}</span>
            {downloading && <span className="tnum text-muted">{mb(job.downloaded)} de {total ? mb(total) : "?"} MB</span>}
          </span>
          <span className="mt-1.5 block"><Bar value={downloading ? (total ? (job.downloaded ?? 0) / total : 0.03) : 1} /></span>
        </span>
        {downloading && <button className="btn-quiet btn-sm" onClick={cancel}>Cancelar</button>}
      </span>
    );
  }
  if (confirming) {
    return (
      <span className="flex flex-wrap items-center gap-2">
        <span className="text-sm">O AURA vai fechar, atualizar e abrir de novo; seus dados ficam.</span>
        <button className="btn-primary btn-sm" onClick={start}>Atualizar</button>
        <button className="btn-quiet btn-sm" onClick={() => setConfirming(false)}>Cancelar</button>
      </span>
    );
  }
  const canInstall = !!upd.install?.possible;
  const failed = err ?? (job?.status === "failed" ? job.error : null);
  return (
    <span className="flex flex-wrap items-center gap-2">
      {failed && <span role="alert" className="w-full text-sm text-bad">Não deu para atualizar: {failed}</span>}
      {canInstall && (
        <button className="btn-primary btn-sm" onClick={() => setConfirming(true)}>
          <Icon name="download" size={16} />{failed ? "Tentar de novo" : "Atualizar agora"}
        </button>
      )}
      <a className={`${canInstall ? "btn" : "btn-primary"} btn-sm`} href={upd.download_url} target="_blank" rel="noreferrer"
        title={canInstall ? "Baixar o instalador e instalar você mesmo" : upd.install?.reason ?? undefined}>
        {!canInstall && <Icon name="download" size={16} />}Baixar
      </a>
      {onLater && <button className="btn-quiet btn-sm" onClick={onLater}>Agora não</button>}
    </span>
  );
}

/** The line shown after an update that did not happen (the helper's report). */
export function LastAttempt({ upd }: { upd: UpdateInfo }) {
  if (!upd.last_attempt) return null;
  return (
    <p className="text-sm">
      <span className="text-bad">{upd.last_attempt.message} O AURA continua na {upd.current} e seus dados não foram tocados.</span>{" "}
      <span className="text-muted">Detalhes em <code className="break-all">{upd.last_attempt.log}</code>.</span>
    </p>
  );
}
