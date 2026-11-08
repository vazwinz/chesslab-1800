#!/usr/bin/env bash
# ChessLab 1800 — one-time setup on Linux/macOS. Run from the repo root: bash scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements-dev.txt
(cd frontend && npm install && npm run build)
command -v stockfish >/dev/null || [ -n "${STOCKFISH_PATH:-}" ] || \
  echo "Install Stockfish (e.g. 'sudo apt install stockfish') or set STOCKFISH_PATH."
echo "Setup done. Import puzzles (README), then: bash scripts/run.sh"
