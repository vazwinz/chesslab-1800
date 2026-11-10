#!/usr/bin/env bash
# Build the AURA desktop app on Linux and install a menu entry. From the repo root:
#   bash desktop/build_linux.sh                  (STOCKFISH_FROM=/usr/games/stockfish to reuse a binary)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d backend/.venv ] || python3 -m venv backend/.venv
VPY=backend/.venv/bin/python
$VPY -m pip install --upgrade pip
$VPY -m pip install -r backend/requirements.txt -r desktop/requirements-desktop.txt
(cd frontend && npm ci && npm run build)
if [ -n "${STOCKFISH_FROM:-}" ]; then $VPY desktop/fetch_stockfish.py --from "$STOCKFISH_FROM"
elif [ ! -x desktop/stockfish_bin/stockfish ]; then
  if command -v stockfish >/dev/null; then $VPY desktop/fetch_stockfish.py --from "$(command -v stockfish)"
  elif [ -x /usr/games/stockfish ]; then $VPY desktop/fetch_stockfish.py --from /usr/games/stockfish
  else $VPY desktop/fetch_stockfish.py --variant "${VARIANT:-sse41-popcnt}"; fi
fi
$VPY -m PyInstaller desktop/aura.spec --noconfirm --distpath desktop/dist --workpath desktop/build
cp desktop/aura.png desktop/dist/AURA/aura.png  # the menu entry's icon travels with the app (and with "Atualizar agora")
tar -C desktop/dist -czf desktop/dist/AURA-linux-x64.tar.gz AURA
if [ "${NO_INSTALL:-0}" != "1" ]; then
  APPDIR="$HOME/.local/opt/aura"; mkdir -p "$APPDIR" "$HOME/.local/share/applications" "$HOME/.local/bin"
  rm -rf "$APPDIR"; cp -r desktop/dist/AURA "$APPDIR"
  ln -sf "$APPDIR/AURA" "$HOME/.local/bin/aura"
  cat > "$HOME/.local/share/applications/aura.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=AURA
Comment=ChessLab 1800 chess training
Exec=$APPDIR/AURA
Icon=$APPDIR/aura.png
Categories=Game;Education;
Terminal=false
DESK
  echo "Installed: menu entry 'AURA' and command 'aura' (~/.local/bin)."
fi
echo "Built: desktop/dist/AURA/AURA   portable: desktop/dist/AURA-linux-x64.tar.gz"
