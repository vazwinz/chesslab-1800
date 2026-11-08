# ChessLab 1800 — one-time setup on Windows (PowerShell). Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== Python backend ==" -ForegroundColor Green
if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python 3.11+ not found. Install from https://www.python.org/downloads/ (tick 'Add to PATH')."
}
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
if (-not (Test-Path "backend\.venv")) { & $py -m venv backend\.venv }
& backend\.venv\Scripts\python.exe -m pip install --upgrade pip
& backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt

Write-Host "== Frontend ==" -ForegroundColor Green
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js 18+ not found. Install from https://nodejs.org/" }
Push-Location frontend
npm install
npm run build
Pop-Location

Write-Host "== Stockfish ==" -ForegroundColor Green
if (-not $env:STOCKFISH_PATH -and -not (Get-Command stockfish -ErrorAction SilentlyContinue)) {
  Write-Host "Stockfish not found. Download the Windows build from https://stockfishchess.org/download/ ,"
  Write-Host "unzip it (e.g. C:\Tools\stockfish) and set, for example:"
  Write-Host '  setx STOCKFISH_PATH "C:\Tools\stockfish\stockfish-windows-x86-64-avx2.exe"'
  Write-Host "(open a new PowerShell window afterwards)."
} else { Write-Host "Stockfish: $($env:STOCKFISH_PATH)" }
Write-Host "Setup done. Next: import puzzles (README) and run scripts\run.ps1" -ForegroundColor Green
