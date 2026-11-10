"""In-place update ("Atualizar agora" in the new-version notice).

The packaged app downloads the file of the new release that fits this computer (the Windows
installer or the Linux tarball, see updates.pick_asset), checks it against the SHA256SUMS file
published with the release, and hands over to a small detached helper, then closes itself:

* Windows, update_helpers/apply_update.ps1: waits for AURA to exit, runs the installer silently
  (/S /D=<the same folder>) and starts AURA again;
* Linux, update_helpers/apply_update.sh: AURA unpacks the tarball next to its own folder first,
  the helper waits for AURA to exit, swaps the two folders and starts AURA again.

Everything is kept in <data dir>/update: the download, the copy of the helper that runs, its log
(update.log) and result.json, which the next start reads to report an attempt that failed. The
training data is never touched. Running from source, the app does not update itself: use
desktop/update_windows.ps1 or desktop/update_linux.sh instead."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config import settings
from ..version import __version__
from . import updates

log = logging.getLogger(__name__)

HELPERS = Path(__file__).resolve().parent / "update_helpers"
HELPER = {"windows": "apply_update.ps1", "linux": "apply_update.sh"}
RESULT, LOG = "result.json", "update.log"
QUIT_DELAY_S = 1.5   # time for the window to show "Fechando o AURA..." before it closes
# Held by the Windows helper while it installs; the launcher (desktop/aura.py) refuses to start meanwhile.
UPDATE_MUTEX = "Local\\AURA-ChessLab1800-update"

_lock = threading.Lock()
_state: dict = {"status": "idle"}
_cancel = threading.Event()
_quit_hook: Callable[[], None] | None = None


class UpdateError(Exception):
    """A reason, in Portuguese, why the update cannot go on."""


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class Target:
    platform: str        # "windows" | "linux"
    app_dir: Path        # the folder that holds AURA.exe / AURA
    executable: Path


# ---------------------------------------------------------------- where this copy is installed
def set_quit_hook(fn: Callable[[], None] | None) -> None:
    """The desktop launcher registers how to close the app (window first, then the server)."""
    global _quit_hook
    _quit_hook = fn


def install_target(frozen: bool | None = None, executable: str | None = None,
                   platform: str | None = None) -> tuple[Target | None, str | None]:
    """The installed copy this process runs from, or (None, the reason it cannot update itself)."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    platform = sys.platform if platform is None else platform
    if not frozen:
        return None, ("Este AURA roda a partir do código-fonte: atualize com desktop/update_windows.ps1 "
                      "ou desktop/update_linux.sh.")
    exe = Path(executable or sys.executable).resolve()
    if platform == "win32":
        if not (exe.parent / "Uninstall.exe").exists():
            return None, "Esta cópia do AURA não veio do instalador (é o zip portátil?): use Baixar."
        return Target("windows", exe.parent, exe), None
    if platform.startswith("linux"):
        return Target("linux", exe.parent, exe), None
    return None, "A atualização automática existe só no Windows e no Linux: use Baixar."


def install_offer(available: bool, asset: dict | None, sums: dict | None) -> dict:
    """The `install` part of the update check: can "Atualizar agora" be offered, and why not."""
    out = {"possible": False, "reason": None, "asset": (asset or {}).get("name"), "size": (asset or {}).get("size"),
           "asset_url": (asset or {}).get("url"), "sums_url": (sums or {}).get("url")}
    if not available:
        return out
    target, reason = install_target()
    if target is None:
        return {**out, "reason": reason}
    if asset is None:
        return {**out, "reason": "Esta versão não tem arquivo para o seu sistema: use Baixar."}
    if sums is None:
        return {**out, "reason": "Esta versão não publicou o SHA256SUMS, então não há como conferir o download: use Baixar."}
    if _quit_hook is None:
        return {**out, "reason": "O AURA não foi aberto pelo programa do AURA: use Baixar."}
    return {**out, "possible": True}


def _writable(folder: Path) -> bool:
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".aura-write-test-"):
            pass
        return True
    except OSError:
        return False


def update_dir(create: bool = True) -> Path:
    d = Path(settings.data_dir) / "update"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def stage_dir(target: Target) -> Path:
    """Linux: the new version is unpacked here, next to the app folder (same disk: a rename swaps them)."""
    return target.app_dir.parent / f".{target.app_dir.name}-update"


def _unlink(p: Path | None) -> None:
    if p is None:
        return
    try:
        p.unlink(missing_ok=True)
    except OSError:  # an antivirus still holds it: harmless, cleanup() removes it on the next start
        pass


# ---------------------------------------------------------------- download and check
def parse_sha256sums(text: str) -> dict[str, str]:
    """`sha256sum` output: "<64 hex>  <name>" (or " *<name>" in binary mode), one file per line."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _client():
    import httpx

    return httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60, connect=15),
                        headers={"User-Agent": f"AURA/{__version__} (in-app update)"})  # headers are ASCII only


def fetch_text(url: str, limit: int = 1 << 16) -> str:
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
        if len(r.content) > limit:
            raise UpdateError("O SHA256SUMS desta versão é grande demais para ser de verdade; nada foi instalado.")
        return r.text


def download(url: str, dest: Path, progress: Callable[[int, int], None] | None = None,
             cancel: threading.Event | None = None) -> Path:
    """Stream `url` into `dest`. A failed or cancelled download leaves nothing behind."""
    done = total = 0
    try:
        with _client() as c, c.stream("GET", url) as r:
            r.raise_for_status()
            plain = r.headers.get("content-encoding", "identity") == "identity"
            total = int(r.headers.get("content-length") or 0) if plain else 0
            with open(dest, "wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    fh.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        if total and done != total:
            raise UpdateError(f"O download veio incompleto ({done} de {total} bytes). Tente de novo.")
        return dest
    except BaseException:
        _unlink(dest)
        raise


def unpack_linux(tarball: Path, target: Target) -> Path:
    """Unpack the release tarball (one folder, AURA/) next to the app folder; returns the new folder."""
    stage = stage_dir(target)
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir()
    try:
        with tarfile.open(tarball) as tf:
            if hasattr(tarfile, "data_filter"):
                tf.extractall(stage, filter="data")  # refuses absolute paths, "..", devices, links outside
            else:  # pragma: no cover - Python without the extraction filters
                root = stage.resolve()
                for m in tf.getmembers():
                    if not (m.isfile() or m.isdir()) or not (stage / m.name).resolve().is_relative_to(root):
                        raise UpdateError(f"O pacote da versão nova tem um item estranho ({m.name}); nada foi instalado.")
                tf.extractall(stage)
        new = stage / "AURA"
        exe = new / "AURA"
        if not exe.is_file() or not os.access(exe, os.X_OK):
            raise UpdateError("O pacote da versão nova não tem o programa AURA dentro; nada foi instalado.")
        return new
    except tarfile.TarError as exc:
        shutil.rmtree(stage, ignore_errors=True)
        raise UpdateError(f"O pacote da versão nova está danificado ({exc}); nada foi instalado.") from exc
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


# ---------------------------------------------------------------- the helper
def helper_command(target: Target, *, helper: Path, file: Path | None, new: Path | None, pid: int,
                   version: str, result: Path, log_file: Path) -> list[str]:
    """The helper's command line. No shell is involved: each value is one argument."""
    if target.platform == "windows":
        ps = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        return [str(ps), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(helper),
                "-Installer", str(file), "-InstallDir", str(target.app_dir), "-WaitPid", str(pid),
                "-Version", version, "-Result", str(result), "-Log", str(log_file)]
    return ["/bin/sh", str(helper), "--app", str(target.app_dir), "--new", str(new), "--pid", str(pid),
            "--version", version, "--result", str(result), "--log", str(log_file)]


def helper_env() -> dict[str, str]:
    """The environment the helper (and the AURA it starts again) gets: without PyInstaller's
    variables, so the new AURA starts as a fresh program and not as a child of this one, and on
    Linux without the bundle's LD_LIBRARY_PATH (tar, mv and sh must use the system's libraries)."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("_PYI_", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
        orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if orig:
            env["LD_LIBRARY_PATH"] = orig
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def _reset_dll_directory() -> Callable[[], None]:
    """PyInstaller points the DLL search path at the bundle, and child processes inherit it: a
    helper that loaded a DLL from _internal would keep the installer from replacing it."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return lambda: None
    import ctypes

    k32 = ctypes.windll.kernel32
    k32.SetDllDirectoryW(None)
    return lambda: k32.SetDllDirectoryW(getattr(sys, "_MEIPASS", None))


def launch(cmd: list[str], cwd: Path, env: dict[str, str]) -> int:
    """Start the helper so that it outlives AURA (own process group/session, no console window)."""
    kw = dict(cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        restore = _reset_dll_directory()
        try:
            try:
                p = subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
            except OSError:  # started inside a job that does not allow breaking away
                p = subprocess.Popen(cmd, creationflags=flags, **kw)
        finally:
            restore()
    else:
        p = subprocess.Popen(cmd, start_new_session=True, **kw)
    return p.pid


# ---------------------------------------------------------------- the background job
def state() -> dict:
    with _lock:
        return dict(_state)


def _set(**kw) -> None:
    with _lock:
        _state.update(kw)


def _busy_reason() -> str | None:
    from . import game_jobs, import_jobs

    if import_jobs.state().get("status") == "running":
        return "A importação de puzzles está em andamento: espere terminar e atualize depois."
    if game_jobs.state().get("status") == "running":
        return "A análise das suas partidas está em andamento: espere terminar (ou pare em Partidas) e atualize depois."
    return None


def start(db) -> dict:
    """Start "Atualizar agora": download, check, prepare, launch the helper, close the app."""
    with _lock:
        if _state.get("status") in ("running", "restarting"):
            raise UpdateError("A atualização já está em andamento.")
    info = updates.check(db)
    offer = info.get("install") or {}
    if not info.get("available"):
        raise UpdateError("Não há versão nova para instalar.")
    if not offer.get("possible"):
        raise UpdateError(offer.get("reason") or "Esta cópia do AURA não consegue se atualizar sozinha: use Baixar.")
    target, reason = install_target()
    if target is None:
        raise UpdateError(reason)
    for folder in (target.app_dir, target.app_dir.parent) if target.platform == "linux" else (target.app_dir,):
        if not _writable(folder):
            raise UpdateError(f"O AURA não tem permissão para gravar em {folder}: use Baixar.")
    busy = _busy_reason()
    if busy:
        raise UpdateError(busy)
    _unlink(update_dir() / RESULT)
    with _lock:
        _cancel.clear()
        _state.clear()
        _state.update({"status": "running", "phase": "download", "version": info.get("latest"),
                       "downloaded": 0, "total_bytes": offer.get("size") or 0, "started": time.time()})
    threading.Thread(target=_run, args=(info, target), name="aura-update", daemon=True).start()
    return state()


def cancel() -> dict:
    """Stops a download in progress (once the helper is running, it is too late)."""
    _cancel.set()
    return state()


def _quit() -> None:
    hook = _quit_hook
    if hook is not None:
        log.info("closing AURA for the update")
        hook()


def _run(info: dict, target: Target) -> None:
    offer, version = info["install"], info["latest"]
    folder = update_dir()
    dest = folder / offer["asset"]
    try:
        expected = parse_sha256sums(fetch_text(offer["sums_url"])).get(offer["asset"])
        if not expected:
            raise UpdateError(f"O SHA256SUMS desta versão não tem a soma de {offer['asset']}; nada foi instalado.")
        download(offer["asset_url"], dest, progress=lambda d, t: _set(downloaded=d, total_bytes=t or offer.get("size") or 0),
                 cancel=_cancel)
        _set(phase="verify")
        if sha256_file(dest) != expected:
            _unlink(dest)
            raise UpdateError("O arquivo baixado não confere com a soma SHA-256 publicada e foi apagado. Tente de novo.")
        _set(phase="prepare")
        new = None
        if target.platform == "linux":
            new = unpack_linux(dest, target)
            _unlink(dest)  # unpacked: the tarball is no longer needed
        helper = folder / HELPER[target.platform]
        shutil.copyfile(HELPERS / HELPER[target.platform], helper)  # the bundle's copy may be replaced
        cmd = helper_command(target, helper=helper, file=dest if target.platform == "windows" else None, new=new,
                             pid=os.getpid(), version=version, result=folder / RESULT, log_file=folder / LOG)
        if _cancel.is_set():
            raise Cancelled()
        log.info("update to %s: starting the helper %s", version, cmd)
        launch(cmd, cwd=folder, env=helper_env())
        _set(status="restarting", phase="restart")
        timer = threading.Timer(QUIT_DELAY_S, _quit)
        timer.daemon = True
        timer.start()
    except Cancelled:
        _unlink(dest)
        if target.platform == "linux":
            shutil.rmtree(stage_dir(target), ignore_errors=True)
        _set(status="idle", phase=None, cancelled=True)
    except Exception as exc:  # surfaced to the notice
        log.exception("update to %s failed", version)
        _set(status="failed", error=_friendly(exc))


def _friendly(exc: Exception) -> str:
    if isinstance(exc, UpdateError):
        return str(exc)
    name = type(exc).__name__
    if name in ("ConnectError", "ConnectTimeout", "ReadTimeout", "RemoteProtocolError", "ReadError"):
        return "Sem conexão com o GitHub. Confira a internet e tente de novo."
    if name == "HTTPStatusError":
        code = getattr(getattr(exc, "response", None), "status_code", "?")
        return f"O GitHub respondeu com erro ({code}). Tente de novo mais tarde."
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return "Disco cheio: libere uns 500 MB e tente de novo."
    return f"Falha inesperada ({name}). Os detalhes estão no aura.log da pasta de dados."


# ---------------------------------------------------------------- after the restart
STEP_TEXT = {
    "wait": "o AURA não fechou a tempo",
    "install": "o instalador parou com o código {code}",
    "check": "a instalação não deixou o AURA.exe na pasta",
    "version": "o instalador terminou, mas a versão instalada não é a nova",
    "swap": "não deu para trocar a pasta do programa",
    "error": "o ajudante de atualização teve um erro inesperado",
}


def _read_result() -> dict | None:
    try:
        r = json.loads((update_dir(create=False) / RESULT).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return r if isinstance(r, dict) else None


def _still_newer(version) -> bool:
    v, cur = updates.parse_version(str(version or "")), updates.parse_version(__version__)
    return bool(v and cur and v > cur)


def last_attempt() -> dict | None:
    """The helper's report when an update did not happen (this copy is still older than its target)."""
    r = _read_result()
    if r is None or r.get("ok") or not _still_newer(r.get("version")):
        return None
    step = str(r.get("step") or "error")
    if step == "install" and r.get("code") == 2:
        why = "o instalador encontrou o AURA ainda aberto e parou"
    else:
        why = STEP_TEXT.get(step, STEP_TEXT["error"]).format(code=r.get("code"))
    return {"version": r.get("version"), "message": f"A atualização para a {r.get('version')} não deu certo: {why}.",
            "log": str(update_dir(create=False) / LOG)}


def cleanup() -> None:
    """On start: remove what an earlier update left behind (the log and a failure report stay)."""
    d = update_dir(create=False)
    if d.is_dir():
        r = _read_result()
        if r is not None and (r.get("ok") or not _still_newer(r.get("version"))):
            _unlink(d / RESULT)
        for p in d.iterdir():
            if p.name in (RESULT, LOG):
                continue
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                _unlink(p)
        logf = d / LOG
        try:
            if logf.stat().st_size > 512 * 1024:
                logf.write_bytes(logf.read_bytes()[-128 * 1024:])
        except OSError:
            pass
    target, _ = install_target()
    if target is not None and target.platform == "linux":
        # only old leftovers: a helper may be about to swap a fresh one (Linux has no "updating" lock)
        for p in (stage_dir(target), target.app_dir.parent / f".{target.app_dir.name}-old"):
            try:
                if time.time() - p.stat().st_mtime > 3600:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
