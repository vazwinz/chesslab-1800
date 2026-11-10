# PyInstaller spec for AURA (ChessLab 1800 desktop). Build from the repo root:
#   pyinstaller desktop/aura.spec --noconfirm
# Prerequisites: frontend built (frontend/dist) and desktop/stockfish_bin/stockfish[.exe] present.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
APP_DIR = ROOT / "backend" / "app"
win = sys.platform == "win32"

datas = [(str(ROOT / "frontend" / "dist"), "frontend_dist")]
sf = ROOT / "desktop" / "stockfish_bin"
if sf.exists():
    datas.append((str(sf), "stockfish"))
# Alembic reads env.py and the revision files from disk at start-up (they are not imported as
# modules), so the migrations folder ships as plain files next to the frozen `app` package.
for f in sorted((APP_DIR / "migrations").rglob("*")):
    if f.is_file() and "__pycache__" not in f.parts and f.suffix in (".py", ".mako"):
        datas.append((str(f), str(Path("app") / f.parent.relative_to(APP_DIR))))
# the in-place updater's helper scripts, also read from disk (app/services/updater.py copies one out)
for f in sorted((APP_DIR / "services" / "update_helpers").glob("apply_update.*")):
    datas.append((str(f), str(Path("app") / "services" / "update_helpers")))
datas += collect_data_files("webview")

hidden = (collect_submodules("app") + collect_submodules("uvicorn") + collect_submodules("webview")
          + collect_submodules("alembic") + ["mako", "mako.template", "chess.pgn", "chess.engine", "zstandard",
                                             "sqlalchemy.dialects.sqlite"])

a = Analysis([str(ROOT / "desktop" / "aura.py")], pathex=[str(ROOT / "backend")], datas=datas,
             hiddenimports=hidden, excludes=["tkinter", "pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AURA", console=False,
          icon=str(ROOT / "desktop" / ("aura.ico" if win else "aura.png")))
coll = COLLECT(exe, a.binaries, a.datas, name="AURA")
