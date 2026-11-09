"""Put a Stockfish binary into desktop/stockfish_bin/ for packaging.

    python desktop/fetch_stockfish.py                      # download the official release for this OS
    python desktop/fetch_stockfish.py --variant avx2       # faster build for CPUs with AVX2
    python desktop/fetch_stockfish.py --from C:\\path\\stockfish.exe   # use a binary you already have

Release assets come from https://github.com/official-stockfish/Stockfish/releases (GPL-3.0).
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "stockfish_bin"
VERSION = "sf_17.1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", help="copy this existing Stockfish binary instead of downloading")
    ap.add_argument("--variant", default="sse41-popcnt",
                    help="sse41-popcnt (works on almost any x86-64 CPU), avx2, bmi2, or x86-64")
    ap.add_argument("--version", default=VERSION)
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    exe = OUT / ("stockfish.exe" if os.name == "nt" else "stockfish")
    if a.src:
        shutil.copy2(a.src, exe)
    else:
        osname = "windows" if os.name == "nt" else "ubuntu"
        ext = "zip" if os.name == "nt" else "tar"
        name = f"stockfish-{osname}-x86-64-{a.variant}" if a.variant != "x86-64" else f"stockfish-{osname}-x86-64"
        url = f"https://github.com/official-stockfish/Stockfish/releases/download/{a.version}/{name}.{ext}"
        print("downloading", url)
        try:
            data = urllib.request.urlopen(url, timeout=120).read()
        except Exception as exc:
            print(f"download failed ({exc}).\nDownload Stockfish manually from https://stockfishchess.org/download/ "
                  "and run: python desktop/fetch_stockfish.py --from <path-to-binary>", file=sys.stderr)
            return 1
        if ext == "zip":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                member = next(n for n in z.namelist() if n.endswith(".exe"))
                exe.write_bytes(z.read(member))
        else:
            with tarfile.open(fileobj=io.BytesIO(data)) as t:
                member = next(m for m in t.getmembers() if m.isfile() and Path(m.name).name.startswith("stockfish-"))
                exe.write_bytes(t.extractfile(member).read())
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("Stockfish ready:", exe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
