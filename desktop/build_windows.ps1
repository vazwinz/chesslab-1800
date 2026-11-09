# Gera o app AURA para Windows. Rode na pasta do projeto (a que tem backend, frontend e desktop):
#   powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1
#   (acrescente -StockfishFrom "C:\caminho\stockfish.exe" para usar um Stockfish que você já tem)
# Resultado: desktop\dist\AURA-Setup-<versão>.exe (instalador) e desktop\dist\AURA-windows-x64.zip (portátil).
param([string]$StockfishFrom = "", [string]$Variant = "sse41-popcnt", [switch]$NoShortcuts, [string]$Version = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not $Version) {
  # a versão vem de um lugar só: backend\app\version.py
  $m = Select-String -Path "backend\app\version.py" -Pattern '__version__\s*=\s*"([^"]+)"'
  $Version = $m.Matches[0].Groups[1].Value
}
Write-Host "AURA $Version" -ForegroundColor Cyan
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "Falhou: $what (código $LASTEXITCODE)" } }

$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
if (-not (Test-Path "backend\.venv")) { & $py -m venv backend\.venv; Check "criar o ambiente Python" }
$vpy = "backend\.venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip; Check "atualizar o pip"
& $vpy -m pip install -r backend\requirements.txt -r desktop\requirements-desktop.txt; Check "instalar as dependências Python"

Push-Location frontend
npm ci; Check "instalar as dependências do front (npm ci)"
npm run build; Check "gerar o front (npm run build)"
Pop-Location

if ($StockfishFrom) { & $vpy desktop\fetch_stockfish.py --from $StockfishFrom; Check "copiar o Stockfish" }
elseif (-not (Test-Path "desktop\stockfish_bin\stockfish.exe")) { & $vpy desktop\fetch_stockfish.py --variant $Variant; Check "baixar o Stockfish" }

& $vpy -m PyInstaller desktop\aura.spec --noconfirm --distpath desktop\dist --workpath desktop\build; Check "PyInstaller"
Compress-Archive -Path desktop\dist\AURA -DestinationPath desktop\dist\AURA-windows-x64.zip -Force

# Instalador (NSIS): instala por usuário, sem administrador; atalhos e entrada em "Aplicativos instalados".
function Find-MakeNsis {
  $c = Get-Command makensis -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  foreach ($p in @("${env:ProgramFiles(x86)}\NSIS\makensis.exe", "$env:ProgramFiles\NSIS\makensis.exe")) { if (Test-Path $p) { return $p } }
  return $null
}
$nsis = Find-MakeNsis
if (-not $nsis -and (Get-Command winget -ErrorAction SilentlyContinue)) {
  Write-Host "Instalando o NSIS (gerador do instalador) com o winget..."
  winget install -e --id NSIS.NSIS --silent --accept-package-agreements --accept-source-agreements | Out-Null
  $nsis = Find-MakeNsis
}
if ($nsis) {
  Push-Location desktop
  & $nsis "/DVERSION=$Version" installer.nsi; Check "NSIS"
  Pop-Location
  Write-Host "Instalador: desktop\dist\AURA-Setup-$Version.exe" -ForegroundColor Green
} else {
  Write-Host "NSIS não encontrado: instale em https://nsis.sourceforge.io para gerar também o AURA-Setup.exe (o zip funciona do mesmo jeito)." -ForegroundColor Yellow
}

if ($NoShortcuts -or $nsis) { exit 0 }
# Sem instalador: atalhos no Menu Iniciar e na área de trabalho apontando para o app gerado
$target = (Resolve-Path "desktop\dist\AURA\AURA.exe").Path
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath("Desktop"), "$env:APPDATA\Microsoft\Windows\Start Menu\Programs")) {
  $lnk = $shell.CreateShortcut((Join-Path $dir "AURA.lnk"))
  $lnk.TargetPath = $target; $lnk.WorkingDirectory = Split-Path $target; $lnk.IconLocation = $target; $lnk.Save()
}
Write-Host "Pronto: desktop\dist\AURA\AURA.exe (atalho 'AURA' na área de trabalho e no Menu Iniciar)" -ForegroundColor Green
Write-Host "Zip portátil: desktop\dist\AURA-windows-x64.zip"
