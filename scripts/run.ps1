# Start ChessLab 1800 on Windows: backend + built frontend on http://127.0.0.1:8000
#   powershell -ExecutionPolicy Bypass -File scripts\run.ps1        (add -Dev for the Vite dev server on :5173)
param([switch]$Dev)
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"
if ($Dev) {
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"
}
Write-Host "ChessLab 1800 -> http://127.0.0.1:8000" -ForegroundColor Green
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
