"""In-place update ("Atualizar agora"): which release file fits this computer, the SHA-256 check,
the helpers' command lines, the helpers themselves against a throwaway install folder and a dummy
app (Windows: compiled with the .NET Framework's csc.exe; Linux: a copy of `sleep`), and the whole
job through the API with a local stand-in for GitHub. Nothing here touches an installed AURA."""
from __future__ import annotations

import functools
import hashlib
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path, PurePosixPath

import pytest

from app.config import settings
from app.services import updater, updates
from app.services.updater import Target
from app.version import __version__

HELPERS = updater.HELPERS
NEWER = "9.9.0"
DL = "https://github.com/vazwinz/chesslab-1800/releases/download/v9.9.0"
ASSETS = [
    {"name": "AURA-Setup-9.9.0.exe", "url": f"{DL}/AURA-Setup-9.9.0.exe", "size": 100},
    {"name": "AURA-Setup-9.9.0.exe.sig", "url": f"{DL}/AURA-Setup-9.9.0.exe.sig", "size": 1},
    {"name": "AURA-windows-x64.zip", "url": f"{DL}/AURA-windows-x64.zip", "size": 90},
    {"name": "AURA-linux-x64.tar.gz", "url": f"{DL}/AURA-linux-x64.tar.gz", "size": 80},
    {"name": "SHA256SUMS", "url": f"{DL}/SHA256SUMS", "size": 300},
]


def _release(assets=ASSETS, latest=NEWER):
    return lambda repo: {"ok": True, "latest": latest, "page_url": "https://github.com/vazwinz/chesslab-1800/releases/tag/v9.9.0",
                         "assets": assets, "notes": "novidades"}


def _serve(directory: Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture()
def fresh(monkeypatch, tmp_path):
    """A clean updater: idle job, no quit hook, its own data folder, no other job running."""
    from app.services import game_jobs, import_jobs

    monkeypatch.setattr(updater, "_state", {"status": "idle"})
    monkeypatch.setattr(updater, "_cancel", threading.Event())
    monkeypatch.setattr(updater, "_quit_hook", None)
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    monkeypatch.setattr(import_jobs, "_state", {"status": "idle"})
    monkeypatch.setattr(game_jobs, "_state", {"status": "idle"})
    return tmp_path


# ------------------------------------------------------------------ which file, and when to offer it
def test_each_platform_gets_its_own_file():
    assert updates.pick_asset(ASSETS, "win32", "AMD64")["name"] == "AURA-Setup-9.9.0.exe"
    assert updates.pick_asset(ASSETS, "win32", "ARM64")["name"] == "AURA-Setup-9.9.0.exe"  # x64 emulation
    assert updates.pick_asset(ASSETS, "linux", "x86_64")["name"] == "AURA-linux-x64.tar.gz"
    assert updates.pick_asset(ASSETS, "linux", "aarch64") is None  # no ARM build
    assert updates.pick_asset(ASSETS, "darwin", "arm64") is None
    assert updates.pick_asset([a for a in ASSETS if not a["name"].endswith(".exe")], "win32", "AMD64") is None


def test_linux_download_link_is_the_tarball_not_the_installer(db, monkeypatch):
    """0.4.0 pointed "Baixar" at the .exe on Linux too."""
    pick = updates.pick_asset
    monkeypatch.setattr(updates, "pick_asset", lambda assets: pick(assets, "linux", "x86_64"))
    r = updates.check(db, force=True, fetch=_release())
    assert r["available"] and r["download_url"].endswith("/AURA-linux-x64.tar.gz")
    monkeypatch.setattr(updates, "pick_asset", lambda assets: pick(assets, "darwin", "arm64"))
    r = updates.check(db, force=True, fetch=_release())
    assert r["download_url"] == r["page_url"], "no build for this system: the release page"


def test_install_is_offered_only_for_a_packaged_app_with_checksums(db, monkeypatch, fresh):
    pick = updates.pick_asset
    monkeypatch.setattr(updates, "pick_asset", lambda assets: pick(assets, "win32", "AMD64"))
    r = updates.check(db, force=True, fetch=_release())
    assert r["install"]["possible"] is False and "código-fonte" in r["install"]["reason"], "tests run from source"

    app_dir = fresh / "AURA"
    monkeypatch.setattr(updater, "install_target", lambda: (Target("windows", app_dir, app_dir / "AURA.exe"), None))
    r = updates.check(db, force=True, fetch=_release())
    assert r["install"]["possible"] is False and "aberto pelo programa" in r["install"]["reason"], "no launcher"
    updater.set_quit_hook(lambda: None)
    r = updates.check(db, force=True, fetch=_release())
    assert r["install"] == {"possible": True, "reason": None, "asset": "AURA-Setup-9.9.0.exe", "size": 100,
                            "asset_url": f"{DL}/AURA-Setup-9.9.0.exe", "sums_url": f"{DL}/SHA256SUMS"}

    no_sums = [a for a in ASSETS if a["name"] != "SHA256SUMS"]
    r = updates.check(db, force=True, fetch=_release(no_sums))
    assert r["install"]["possible"] is False and "SHA256SUMS" in r["install"]["reason"]
    elsewhere = [{**a, "url": a["url"].replace("github.com/vazwinz", "github.com/someone-else")} for a in ASSETS]
    r = updates.check(db, force=True, fetch=_release(elsewhere))
    assert r["install"]["possible"] is False, "files from outside the repository's releases are ignored"
    r = updates.check(db, force=True, fetch=_release(latest=__version__))
    assert r["available"] is False and r["install"]["possible"] is False and r["install"]["reason"] is None


def test_where_the_running_copy_is_installed(tmp_path):
    t, reason = updater.install_target(frozen=False)
    assert t is None and "update_windows.ps1" in reason
    win = tmp_path / "D AURA"
    win.mkdir()
    t, reason = updater.install_target(frozen=True, executable=str(win / "AURA.exe"), platform="win32")
    assert t is None and "zip portátil" in reason, "no Uninstall.exe: not installed by the installer"
    (win / "Uninstall.exe").write_bytes(b"")
    t, _ = updater.install_target(frozen=True, executable=str(win / "AURA.exe"), platform="win32")
    assert t.platform == "windows" and t.app_dir == win.resolve()
    t, _ = updater.install_target(frozen=True, executable=str(tmp_path / "opt" / "aura" / "AURA"), platform="linux")
    assert t.platform == "linux" and t.app_dir.name == "aura"
    assert updater.install_target(frozen=True, executable="/Applications/AURA", platform="darwin")[0] is None


# ------------------------------------------------------------------ SHA-256
def test_sha256sums_lines():
    a, b = "A" * 64, "0123456789abcdef" * 4
    text = f"{a}  AURA-Setup-9.9.0.exe\r\n{b} *AURA-linux-x64.tar.gz\n\n# comment\nnot a checksum line\n{'c' * 63}  short.txt\n"
    assert updater.parse_sha256sums(text) == {"AURA-Setup-9.9.0.exe": "a" * 64, "AURA-linux-x64.tar.gz": b}


def test_download_streams_the_file_and_leaves_nothing_when_it_fails(tmp_path):
    www = tmp_path / "www"
    www.mkdir()
    blob = os.urandom(3 * (1 << 20) + 17)
    (www / "AURA-Setup-9.9.0.exe").write_bytes(blob)
    srv = _serve(www)
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        seen = []
        dest = updater.download(f"{base}/AURA-Setup-9.9.0.exe", tmp_path / "a.exe", progress=lambda d, t: seen.append((d, t)))
        assert dest.read_bytes() == blob and updater.sha256_file(dest) == hashlib.sha256(blob).hexdigest()
        assert seen[-1] == (len(blob), len(blob)) and len(seen) >= 3

        import httpx

        with pytest.raises(httpx.HTTPStatusError):
            updater.download(f"{base}/missing.exe", tmp_path / "b.exe")
        assert not (tmp_path / "b.exe").exists()
        stop = threading.Event()
        stop.set()
        with pytest.raises(updater.Cancelled):
            updater.download(f"{base}/AURA-Setup-9.9.0.exe", tmp_path / "c.exe", cancel=stop)
        assert not (tmp_path / "c.exe").exists()
    finally:
        srv.shutdown()


# ------------------------------------------------------------------ the helpers' command lines
def test_windows_helper_command_line():
    t = Target("windows", Path(r"D:\AURA"), Path(r"D:\AURA\AURA.exe"))
    cmd = updater.helper_command(t, helper=Path(r"C:\Dados\AURA\update\apply_update.ps1"),
                                 file=Path(r"C:\Dados\AURA\update\AURA-Setup-9.9.0.exe"), new=None, pid=4242,
                                 version="9.9.0", result=Path(r"C:\Dados\AURA\update\result.json"),
                                 log_file=Path(r"C:\Dados\AURA\update\update.log"))
    assert cmd[0].lower().endswith(os.path.join("system32", "windowspowershell", "v1.0", "powershell.exe"))
    assert cmd[1:7] == ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(Path(r"C:\Dados\AURA\update\apply_update.ps1"))]
    assert dict(zip(cmd[7::2], cmd[8::2])) == {
        "-Installer": str(Path(r"C:\Dados\AURA\update\AURA-Setup-9.9.0.exe")), "-InstallDir": str(Path(r"D:\AURA")),
        "-WaitPid": "4242", "-Version": "9.9.0", "-Result": str(Path(r"C:\Dados\AURA\update\result.json")),
        "-Log": str(Path(r"C:\Dados\AURA\update\update.log"))}
    # the installer's own arguments are built by the helper: /S first, /D= last and unquoted
    ps1 = (HELPERS / "apply_update.ps1").read_text(encoding="ascii")
    assert '$psi.Arguments = "/S /D=$dir"' in ps1


def test_linux_helper_command_line():
    t = Target("linux", PurePosixPath("/home/vaz/.local/opt/aura"), PurePosixPath("/home/vaz/.local/opt/aura/AURA"))
    cmd = updater.helper_command(t, helper=PurePosixPath("/home/vaz/.local/share/aura/update/apply_update.sh"),
                                 file=None, new=PurePosixPath("/home/vaz/.local/opt/.aura-update/AURA"), pid=77,
                                 version="9.9.0", result=PurePosixPath("/d/result.json"), log_file=PurePosixPath("/d/update.log"))
    assert cmd == ["/bin/sh", "/home/vaz/.local/share/aura/update/apply_update.sh", "--app", "/home/vaz/.local/opt/aura",
                   "--new", "/home/vaz/.local/opt/.aura-update/AURA", "--pid", "77", "--version", "9.9.0",
                   "--result", "/d/result.json", "--log", "/d/update.log"]


def test_helper_environment_drops_pyinstaller_variables(monkeypatch):
    monkeypatch.setenv("_PYI_ARCHIVE_FILE", "x")
    monkeypatch.setenv("_MEIPASS2", "y")
    monkeypatch.setenv("CHESSLAB_DATA_DIR", "/dados")
    env = updater.helper_env()
    assert "_PYI_ARCHIVE_FILE" not in env and "_MEIPASS2" not in env
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1" and env["CHESSLAB_DATA_DIR"] == "/dados"


def test_helpers_are_plain_ascii_with_unix_line_endings_for_sh():
    """PowerShell 5.1 reads a BOM-less .ps1 as ANSI; dash chokes on CR characters."""
    (HELPERS / "apply_update.ps1").read_bytes().decode("ascii")
    sh = (HELPERS / "apply_update.sh").read_bytes()
    sh.decode("ascii")
    assert b"\r" not in sh, "apply_update.sh must keep LF line endings (see .gitattributes)"


# ------------------------------------------------------------------ Linux: unpacking the tarball
def _tarball(path: Path, members: dict[str, bytes], mode: int = 0o755) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            tf.addfile(info, io.BytesIO(data))
    return path


def test_unpack_linux_puts_the_new_version_next_to_the_app(tmp_path):
    app = tmp_path / "opt" / "aura"
    app.mkdir(parents=True)
    t = Target("linux", app, app / "AURA")
    tb = _tarball(tmp_path / "AURA-linux-x64.tar.gz", {"AURA/AURA": b"#!/bin/sh\n", "AURA/_internal/x.so": b"so"})
    new = updater.unpack_linux(tb, t)
    assert new == tmp_path / "opt" / ".aura-update" / "AURA"
    assert (new / "AURA").read_bytes() == b"#!/bin/sh\n" and (new / "_internal" / "x.so").exists()

    evil = _tarball(tmp_path / "evil.tar.gz", {"AURA/AURA": b"x", "../../evil.txt": b"x"})
    with pytest.raises(updater.UpdateError):
        updater.unpack_linux(evil, t)
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path / "opt" / ".aura-update").exists()
    empty = _tarball(tmp_path / "empty.tar.gz", {"AURA/README": b"x"})
    with pytest.raises(updater.UpdateError, match="não tem o programa"):
        updater.unpack_linux(empty, t)
    (tmp_path / "broken.tar.gz").write_bytes(b"not a tarball")
    with pytest.raises(updater.UpdateError, match="danificado"):
        updater.unpack_linux(tmp_path / "broken.tar.gz", t)


# ------------------------------------------------------------------ the whole job, through the API
def _stand_in_release(tmp_path: Path, blob: bytes, sums: str | None = None):
    www = tmp_path / "www" / "dl"
    www.mkdir(parents=True)
    (www / "AURA-Setup-9.9.0.exe").write_bytes(blob)
    (www / "SHA256SUMS").write_text(sums if sums is not None else
                                    f"{hashlib.sha256(blob).hexdigest()}  AURA-Setup-9.9.0.exe\n", encoding="ascii")
    srv = _serve(tmp_path / "www")
    base = f"http://127.0.0.1:{srv.server_port}"
    assets = [{"name": "AURA-Setup-9.9.0.exe", "url": f"{base}/dl/AURA-Setup-9.9.0.exe", "size": len(blob)},
              {"name": "SHA256SUMS", "url": f"{base}/dl/SHA256SUMS", "size": 90}]
    return srv, base, assets


def _wait_job(client, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get("/api/update/job").json()
        if j["status"] not in ("running",):
            return j
        time.sleep(0.05)
    raise AssertionError("update job did not finish")


@pytest.fixture()
def windows_install(fresh, monkeypatch):
    """Pretend this process is an installed AURA on Windows; record the helper and the quit."""
    app_dir = fresh / "Programs" / "AURA"
    app_dir.mkdir(parents=True)
    monkeypatch.setattr(updater, "install_target", lambda: (Target("windows", app_dir, app_dir / "AURA.exe"), None))
    pick = updates.pick_asset
    monkeypatch.setattr(updates, "pick_asset", lambda assets: pick(assets, "win32", "AMD64"))
    launched, quits = [], []
    monkeypatch.setattr(updater, "launch", lambda cmd, cwd, env: launched.append((cmd, cwd, env)) or 4321)
    monkeypatch.setattr(updater, "QUIT_DELAY_S", 0.01)
    updater.set_quit_hook(lambda: quits.append(time.time()))
    return app_dir, launched, quits


def test_update_now_downloads_checks_and_hands_over_to_the_helper(client, monkeypatch, windows_install, fresh):
    app_dir, launched, quits = windows_install
    blob = os.urandom(200_000)
    srv, base, assets = _stand_in_release(fresh, blob)
    monkeypatch.setenv("AURA_UPDATE_API", base)
    monkeypatch.setattr(updates, "_fetch", _release(assets))
    try:
        assert client.get("/api/update/check?force=true").json()["install"]["possible"] is True
        r = client.post("/api/update/start")
        assert r.status_code == 200 and r.json()["status"] == "running" and r.json()["version"] == NEWER
        assert client.post("/api/update/start").status_code == 409, "a second click never starts a second job"
        job = _wait_job(client)
    finally:
        srv.shutdown()
    assert job["status"] == "restarting" and job["downloaded"] == len(blob), job
    time.sleep(0.2)
    assert len(quits) == 1, "the app closes itself after handing over"
    assert len(launched) == 1
    cmd, cwd, env = launched[0]
    upd = Path(settings.data_dir) / "update"
    setup = upd / "AURA-Setup-9.9.0.exe"
    assert setup.read_bytes() == blob and Path(cwd) == upd
    args = dict(zip(cmd[7::2], cmd[8::2]))
    assert args["-Installer"] == str(setup) and args["-InstallDir"] == str(app_dir)
    assert args["-WaitPid"] == str(os.getpid()) and args["-Version"] == NEWER
    assert Path(cmd[6]) == upd / "apply_update.ps1" and (upd / "apply_update.ps1").read_bytes() == (HELPERS / "apply_update.ps1").read_bytes()
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


@pytest.mark.parametrize("sums, why", [
    ("0" * 64 + "  AURA-Setup-9.9.0.exe\n", "não confere com a soma SHA-256"),
    ("0" * 64 + "  AURA-linux-x64.tar.gz\n", "não tem a soma de AURA-Setup-9.9.0.exe"),
])
def test_a_file_that_does_not_match_its_checksum_is_never_installed(client, monkeypatch, windows_install, fresh, sums, why):
    _, launched, quits = windows_install
    srv, base, assets = _stand_in_release(fresh, os.urandom(50_000), sums=sums)
    monkeypatch.setenv("AURA_UPDATE_API", base)
    monkeypatch.setattr(updates, "_fetch", _release(assets))
    try:
        client.get("/api/update/check?force=true")
        assert client.post("/api/update/start").status_code == 200
        job = _wait_job(client)
    finally:
        srv.shutdown()
    assert job["status"] == "failed" and why in job["error"], job
    assert not launched and not quits
    assert not (Path(settings.data_dir) / "update" / "AURA-Setup-9.9.0.exe").exists()


def test_update_now_refuses_with_a_reason(client, monkeypatch, windows_install, fresh):
    from app.services import game_jobs, import_jobs

    monkeypatch.setattr(updates, "_fetch", _release(latest=__version__))
    r = client.post("/api/update/start")
    assert r.status_code == 409 and "Não há versão nova" in r.json()["detail"]
    monkeypatch.setattr(updates, "_fetch", _release())
    assert client.get("/api/update/check?force=true").json()["install"]["possible"] is True
    monkeypatch.setattr(import_jobs, "_state", {"status": "running"})
    r = client.post("/api/update/start")
    assert r.status_code == 409 and "importação de puzzles" in r.json()["detail"]
    monkeypatch.setattr(import_jobs, "_state", {"status": "done"})
    monkeypatch.setattr(game_jobs, "_state", {"status": "running"})
    r = client.post("/api/update/start")
    assert r.status_code == 409 and "análise das suas partidas" in r.json()["detail"]
    _, launched, quits = windows_install
    assert not launched and not quits and client.get("/api/update/job").json()["status"] == "idle"


def test_running_from_source_never_updates_itself(client, monkeypatch, fresh):
    monkeypatch.setattr(updates, "_fetch", _release())
    updater.set_quit_hook(lambda: None)
    r = client.post("/api/update/start")
    assert r.status_code == 409 and "código-fonte" in r.json()["detail"]


# ------------------------------------------------------------------ after the restart
def test_a_failed_attempt_is_reported_until_it_is_superseded(client, monkeypatch, fresh):
    upd = Path(settings.data_dir) / "update"
    upd.mkdir(parents=True)
    (upd / "result.json").write_text(json.dumps({"ok": False, "step": "install", "code": 2, "version": NEWER}), encoding="utf-8-sig")
    (upd / "AURA-Setup-9.9.0.exe").write_bytes(b"left over")
    (upd / "update.log").write_text("log", encoding="utf-8")
    last = updater.last_attempt()
    assert last["version"] == NEWER and "ainda aberto" in last["message"]
    monkeypatch.setattr(updates, "_fetch", _release())
    assert client.get("/api/update/check?force=true").json()["last_attempt"]["version"] == NEWER
    updater.cleanup()
    assert (upd / "result.json").exists() and (upd / "update.log").exists(), "the report and the log stay"
    assert not (upd / "AURA-Setup-9.9.0.exe").exists(), "downloads do not"
    (upd / "result.json").write_text(json.dumps({"ok": False, "step": "swap", "code": None, "version": __version__}))
    assert updater.last_attempt() is None, "this copy already is that version"
    updater.cleanup()
    assert not (upd / "result.json").exists()
    (upd / "result.json").write_text(json.dumps({"ok": False, "step": "install", "code": 5, "version": NEWER}))
    assert "código 5" in updater.last_attempt()["message"]


# ------------------------------------------------------------------ the Windows helper, for real
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"

DUMMY_APP = r"""
using System; using System.IO; using System.Threading;
static class DummyAura {
  static int Main(string[] args) {
    string dir = AppDomain.CurrentDomain.BaseDirectory;
    string name = Path.GetFileNameWithoutExtension(System.Reflection.Assembly.GetEntryAssembly().Location);
    if (args.Length == 2 && args[0] == "--sleep") {   // a running AURA (or its Stockfish)
      Thread.Sleep(int.Parse(args[1]) * 1000);
      File.WriteAllText(Path.Combine(dir, name + "-exited.txt"), DateTime.UtcNow.Ticks.ToString());
      return 0;
    }
    File.WriteAllText(Path.Combine(dir, "reopened.txt"),   // opened again by the helper
      (Environment.GetEnvironmentVariable("PYINSTALLER_RESET_ENVIRONMENT") ?? "") + "|" + Environment.CurrentDirectory);
    return 0;
  }
}"""
FAKE_SETUP = r"""
using System; using System.IO;
static class FakeSetup {
  static int Main() {
    string control = Environment.GetEnvironmentVariable("FAKE_SETUP_DIR");
    string line = Environment.CommandLine;
    File.WriteAllText(Path.Combine(control, "setup-cmdline.txt"), line);
    File.WriteAllText(Path.Combine(control, "setup-ran.txt"), DateTime.UtcNow.Ticks.ToString());
    int code = int.Parse(File.ReadAllText(Path.Combine(control, "exit-code.txt")).Trim());
    if (code != 0) return code;
    string target = line.Substring(line.IndexOf(" /D=") + 4);   // like NSIS: the rest of the line
    File.Copy(Path.Combine(control, "new", "AURA.exe"), Path.Combine(target, "AURA.exe"), true);
    File.WriteAllText(Path.Combine(target, "version.txt"), "9.9.0");
    return 0;
  }
}"""


@pytest.fixture(scope="module")
def dummy_exes(tmp_path_factory):
    if sys.platform != "win32":
        pytest.skip("Windows helper")
    if not CSC.exists():
        pytest.skip("no .NET Framework C# compiler to build the dummy app")
    out = tmp_path_factory.mktemp("dummies")
    exes = {}
    for name, src in (("app", DUMMY_APP), ("setup", FAKE_SETUP)):
        (out / f"{name}.cs").write_text(src, encoding="utf-8")
        subprocess.run([str(CSC), "/nologo", "/target:winexe", f"/out:{out / (name + '.exe')}", str(out / f"{name}.cs")],
                       check=True, capture_output=True, timeout=120)
        exes[name] = out / f"{name}.exe"
    return exes


def _windows_scene(tmp_path: Path, dummy_exes: dict, exit_code: int):
    install = tmp_path / "Programas do AURA ção"  # spaces and an accent, like a real profile folder
    (install / "_internal" / "stockfish").mkdir(parents=True)
    install = install.resolve()  # long names: CI temp folders come as RUNNER~1
    shutil.copy(dummy_exes["app"], install / "AURA.exe")
    shutil.copy(dummy_exes["app"], install / "_internal" / "stockfish" / "stockfish.exe")
    control = tmp_path / "control"
    (control / "new").mkdir(parents=True)
    shutil.copy(dummy_exes["app"], control / "new" / "AURA.exe")
    (control / "exit-code.txt").write_text(str(exit_code))
    upd = (tmp_path / "data" / "update")
    upd.mkdir(parents=True)
    setup = upd / "AURA-Setup-9.9.0.exe"
    shutil.copy(dummy_exes["setup"], setup)
    env = {**os.environ, "FAKE_SETUP_DIR": str(control), "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    return install, control, upd, setup, env


def _wait_file(path: Path, timeout: float = 15) -> str:
    end = time.time() + timeout
    while time.time() < end:
        try:
            text = path.read_text(encoding="utf-8")
            if text:
                return text
        except OSError:
            pass
        time.sleep(0.1)
    raise AssertionError(f"{path} never appeared")


def test_windows_helper_waits_for_aura_installs_silently_and_reopens(tmp_path, dummy_exes):
    install, control, upd, setup, env = _windows_scene(tmp_path, dummy_exes, exit_code=0)
    main = subprocess.Popen([str(install / "AURA.exe"), "--sleep", "2"])
    engine = subprocess.Popen([str(install / "_internal" / "stockfish" / "stockfish.exe"), "--sleep", "4"])
    cmd = updater.helper_command(Target("windows", install, install / "AURA.exe"), helper=HELPERS / "apply_update.ps1",
                                 file=setup, new=None, pid=main.pid, version="9.9.0", result=upd / "result.json",
                                 log_file=upd / "update.log")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    log = (upd / "update.log").read_text(encoding="utf-8-sig")
    assert r.returncode == 0, (r.stdout, r.stderr, log)
    main.wait(5), engine.wait(5)
    ran = int((control / "setup-ran.txt").read_text())
    assert ran > int((install / "AURA-exited.txt").read_text()), "the installer ran only after AURA closed"
    assert ran > int((install / "_internal" / "stockfish" / "stockfish-exited.txt").read_text()), "and its engine"
    assert (control / "setup-cmdline.txt").read_text(encoding="utf-8").endswith(f" /S /D={install}"), "/D= last, unquoted"
    assert (install / "version.txt").read_text() == "9.9.0" and not setup.exists()
    assert json.loads((upd / "result.json").read_text(encoding="utf-8")) == {"ok": True, "step": "done", "code": 0, "version": "9.9.0"}
    assert _wait_file(install / "reopened.txt") == f"1|{install}", "AURA opened again, as a fresh program, in its folder"
    assert updater.UPDATE_MUTEX.split("\\")[-1] in (HELPERS / "apply_update.ps1").read_text(encoding="ascii")


def test_windows_helper_stops_a_stuck_aura_and_reports_a_failed_install(tmp_path, dummy_exes):
    install, control, upd, setup, env = _windows_scene(tmp_path, dummy_exes, exit_code=2)
    stuck = subprocess.Popen([str(install / "AURA.exe"), "--sleep", "60"])
    cmd = updater.helper_command(Target("windows", install, install / "AURA.exe"), helper=HELPERS / "apply_update.ps1",
                                 file=setup, new=None, pid=stuck.pid, version="9.9.0", result=upd / "result.json",
                                 log_file=upd / "update.log") + ["-WaitSeconds", "2"]
    t0 = time.time()
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    log = (upd / "update.log").read_text(encoding="utf-8-sig")
    assert r.returncode == 1, (r.stdout, r.stderr, log)
    assert stuck.wait(5) is not None and time.time() - t0 < 40, "stopped after -WaitSeconds, not after 60 s"
    assert not (install / "AURA-exited.txt").exists(), "it was stopped, it did not finish its sleep"
    assert json.loads((upd / "result.json").read_text(encoding="utf-8")) == {"ok": False, "step": "install", "code": 2, "version": "9.9.0"}
    assert setup.exists(), "a failed install keeps the download"
    assert _wait_file(install / "reopened.txt").startswith("1|"), "the old AURA opened again"


# ------------------------------------------------------------------ the Linux helper, for real
needs_linux = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux helper (/proc, POSIX sh)")


def _linux_scene(tmp_path: Path):
    opt = (tmp_path / "opt").resolve()
    app = opt / "aura"
    (app / "_internal").mkdir(parents=True)
    (app / "_internal" / "old.txt").write_text("old")
    (app / "aura.png").write_bytes(b"png")
    sleeper = app / "_internal" / "aura-sleeper"  # a running AURA: its /proc/<pid>/exe is inside the folder
    shutil.copy(shutil.which("sleep"), sleeper)
    (app / "AURA").write_text('#!/bin/sh\necho old > "$(dirname "$0")/reopened.txt"\n')
    (app / "AURA").chmod(0o755)
    new = opt / ".aura-update" / "AURA"
    (new / "_internal").mkdir(parents=True)
    (new / "_internal" / "new.txt").write_text("new")
    (new / "AURA").write_text('#!/bin/sh\necho "new|$PYINSTALLER_RESET_ENVIRONMENT|$(pwd)" > "$(dirname "$0")/reopened.txt"\n')
    (new / "AURA").chmod(0o755)
    upd = tmp_path / "data" / "update"
    upd.mkdir(parents=True)
    return opt, app, new, sleeper, upd


@needs_linux
def test_linux_helper_waits_swaps_the_folder_and_reopens(tmp_path):
    opt, app, new, sleeper, upd = _linux_scene(tmp_path)
    running = subprocess.Popen([str(sleeper), "2"])
    cmd = updater.helper_command(Target("linux", app, app / "AURA"), helper=HELPERS / "apply_update.sh", file=None,
                                 new=new, pid=running.pid, version="9.9.0", result=upd / "result.json", log_file=upd / "update.log")
    t0 = time.time()
    r = subprocess.run(cmd, env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}, capture_output=True, text=True, timeout=60)
    log = (upd / "update.log").read_text()
    assert r.returncode == 0, (r.stdout, r.stderr, log)
    assert time.time() - t0 >= 1.5, "it waited for AURA to exit"
    assert (app / "_internal" / "new.txt").exists() and not (app / "_internal" / "old.txt").exists()
    assert (app / "aura.png").read_bytes() == b"png", "the menu icon came along"
    assert not (opt / ".aura-old").exists() and not (opt / ".aura-update").exists()
    assert json.loads((upd / "result.json").read_text()) == {"ok": True, "step": "done", "code": None, "version": "9.9.0"}
    assert _wait_file(app / "reopened.txt").strip() == f"new|1|{app}"


@needs_linux
def test_linux_helper_keeps_the_old_folder_when_the_swap_cannot_happen(tmp_path):
    opt, app, new, sleeper, upd = _linux_scene(tmp_path)
    shutil.rmtree(new)  # nothing to swap in
    cmd = updater.helper_command(Target("linux", app, app / "AURA"), helper=HELPERS / "apply_update.sh", file=None,
                                 new=new, pid=999999, version="9.9.0", result=upd / "result.json", log_file=upd / "update.log")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert r.returncode == 1
    assert (app / "_internal" / "old.txt").exists() and (app / "AURA").exists()
    assert json.loads((upd / "result.json").read_text())["step"] == "swap"
    assert _wait_file(app / "reopened.txt").strip() == "old", "the old AURA opened again"


# ------------------------------------------------------------------ detached from the app
def test_the_helper_outlives_the_app_that_started_it(tmp_path):
    """launch() starts the helper in its own process group (Windows, no console window) or session
    (Linux): the app exits right after starting it, and the helper must carry on."""
    marker = tmp_path / "helper-finished.txt"
    helper = [sys.executable, "-c", "import sys, time; time.sleep(3); open(sys.argv[1], 'w').write('ok')", str(marker)]
    backend = str(Path(__file__).resolve().parents[1])
    app = (f"import os, sys; sys.path.insert(0, {backend!r}); from pathlib import Path; from app.services import updater; "
           f"print(updater.launch({helper!r}, Path({str(tmp_path)!r}), dict(os.environ)), flush=True)")
    t0 = time.time()
    p = subprocess.run([sys.executable, "-c", app], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    assert int(p.stdout.strip()) > 0
    assert not marker.exists() and time.time() - t0 < 3, "the app was already gone while the helper still worked"
    assert _wait_file(marker, timeout=20) == "ok"


# ------------------------------------------------------------------ the launcher's side
def _load_launcher():
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "desktop" / "aura.py"
    spec = importlib.util.spec_from_file_location("aura_launcher_upd", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_quitting_for_an_update_closes_the_window_then_the_server():
    import types

    aura = _load_launcher()
    server = types.SimpleNamespace(should_exit=False)
    q = aura.AppQuitter(server)
    q.window = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    q()
    assert q.window.wait(10) is not None and server.should_exit is True and q.requested.is_set()
    q()  # twice is harmless


@pytest.mark.skipif(sys.platform != "win32", reason="the update lock is a Windows mutex")
def test_launcher_sees_the_update_lock():
    import ctypes

    aura = _load_launcher()
    name = aura.UPDATE_MUTEX_NAME + "-test"
    assert aura.update_in_progress(name) is False
    k32 = ctypes.windll.kernel32
    h = k32.CreateMutexW(None, False, name)
    try:
        assert aura.update_in_progress(name) is True
    finally:
        k32.CloseHandle(h)
    assert aura.update_in_progress(name) is False
    assert aura.UPDATE_MUTEX_NAME == updater.UPDATE_MUTEX
