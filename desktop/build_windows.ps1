# Build the AURA desktop app on Windows. From the repo root:
#   powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1
#   (add -StockfishFrom "C:\path\stockfish.exe" to reuse a binary you already have)
param([string]$StockfishFrom = "", [string]$Variant = "sse41-popcnt", [switch]$NoShortcuts)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
if (-not (Test-Path "backend\.venv")) { & $py -m venv backend\.venv }
$vpy = "backend\.venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip
& $vpy -m pip install -r backend\requirements.txt -r desktop\requirements-desktop.txt

Push-Location frontend; npm install; npm run build; Pop-Location

if ($StockfishFrom) { & $vpy desktop\fetch_stockfish.py --from $StockfishFrom }
elseif (-not (Test-Path "desktop\stockfish_bin\stockfish.exe")) { & $vpy desktop\fetch_stockfish.py --variant $Variant }

& $vpy -m PyInstaller desktop\aura.spec --noconfirm --distpath desktop\dist --workpath desktop\build
Compress-Archive -Path desktop\dist\AURA -DestinationPath desktop\dist\AURA-windows-x64.zip -Force

if ($NoShortcuts) { Write-Host "Built: desktop\dist\AURA\AURA.exe"; exit 0 }
# Start-menu + desktop shortcuts pointing at the built app
$target = (Resolve-Path "desktop\dist\AURA\AURA.exe").Path
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath("Desktop"), "$env:APPDATA\Microsoft\Windows\Start Menu\Programs")) {
  $lnk = $shell.CreateShortcut((Join-Path $dir "AURA.lnk"))
  $lnk.TargetPath = $target; $lnk.WorkingDirectory = Split-Path $target; $lnk.IconLocation = $target; $lnk.Save()
}
Write-Host "Built: desktop\dist\AURA\AURA.exe  (shortcut 'AURA' added to Desktop and Start menu)" -ForegroundColor Green
Write-Host "Portable zip: desktop\dist\AURA-windows-x64.zip"
