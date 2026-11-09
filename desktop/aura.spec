# PyInstaller spec for AURA (ChessLab 1800 desktop). Build from the repo root:
#   pyinstaller desktop/aura.spec --noconfirm
# Prerequisites: frontend built (frontend/dist) and desktop/stockfish_bin/stockfish[.exe] present.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = Path(SPECPATH).parent
win = sys.platform == "win32"

datas = [(str(ROOT / "frontend" / "dist"), "frontend_dist")]
sf = ROOT / "desktop" / "stockfish_bin"
if sf.exists():
    datas.append((str(sf), "stockfish"))
datas += collect_data_files("webview")

hidden = (collect_submodules("app") + collect_submodules("uvicorn") + collect_submodules("webview")
          + ["chess.pgn", "chess.engine", "zstandard", "sqlalchemy.dialects.sqlite"])

a = Analysis([str(ROOT / "desktop" / "aura.py")], pathex=[str(ROOT / "backend")], datas=datas,
             hiddenimports=hidden, excludes=["tkinter", "pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AURA", console=False,
          icon=str(ROOT / "desktop" / ("aura.ico" if win else "aura.png")))
coll = COLLECT(exe, a.binaries, a.datas, name="AURA")
