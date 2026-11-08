#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
echo "ChessLab 1800 -> http://127.0.0.1:8000"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
