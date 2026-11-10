# Atualiza o AURA instalado neste PC a partir deste clone: puxa o código novo do GitHub, gera o
# instalador (ou reaproveita um já gerado para este código), fecha o AURA e instala a versão nova por
# cima, na mesma pasta (o instalador troca a pasta _internal inteira, como o "Atualizar agora" do app).
# Rode na pasta do projeto (a que tem backend, frontend e desktop):
#   powershell -ExecutionPolicy Bypass -File desktop\update_windows.ps1
#   -DryRun    só mostra o que faria: não gera, não fecha, não instala
#   -Rebuild   gera o instalador mesmo que já exista um para este código
#   -NoStart   não abre o AURA no fim
# Os dados (%LOCALAPPDATA%\AURA) não são tocados: o instalador só troca os arquivos do programa.
param([switch]$DryRun, [switch]$Rebuild, [switch]$NoStart)
$root = Split-Path -Parent $PSScriptRoot
function Step($text) { Write-Host $text -ForegroundColor Cyan }
# o instalador só precisa ser gerado de novo quando muda o que vai dentro dele
$codeSpec = @("backend", "frontend", "desktop", ":!desktop/update_windows.ps1", ":!desktop/update_linux.sh")

try {
  if ($DryRun) {
    git -C $root fetch -q
    Step "Código: $(git -C $root status -sb | Select-Object -First 1)"
  } else {
    git -C $root checkout -- frontend/tsconfig.tsbuildinfo  # o build mexe nele; volta ao do repositório
    git -C $root pull --ff-only
    if ($LASTEXITCODE) { throw "o git pull falhou (mensagem acima). Nada foi mudado." }
  }

  $code = [datetime](git -C $root log -1 --format=%cI -- @codeSpec)
  $setup = Get-ChildItem "$root\desktop\dist\AURA-Setup-*.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
  if ($setup -and $setup.LastWriteTime -gt $code -and -not $Rebuild) {
    Step "1/3 O instalador deste código já existe: $($setup.Name)"
  } elseif ($DryRun) {
    Step "1/3 Geraria o instalador (desktop\build_windows.ps1, uns minutos)"
  } else {
    Step "1/3 Gerando o instalador (uns minutos)..."
    $t0 = Get-Date
    $env:PIP_NO_CACHE_DIR = "1"
    powershell -NoProfile -ExecutionPolicy Bypass -File "$root\desktop\build_windows.ps1"
    if ($LASTEXITCODE) { throw "o build falhou (código $LASTEXITCODE). Nada foi mudado." }
    git -C $root checkout -- frontend/tsconfig.tsbuildinfo
    $setup = Get-ChildItem "$root\desktop\dist\AURA-Setup-*.exe" | Where-Object { $_.LastWriteTime -gt $t0 } | Sort-Object LastWriteTime | Select-Object -Last 1
    if (-not $setup) { throw "o instalador novo não apareceu em desktop\dist. Nada foi mudado." }
  }

  $dir = (Get-ItemProperty "HKCU:\Software\AURA" -ErrorAction SilentlyContinue).InstallDir
  if (-not $dir) { $dir = "$env:LOCALAPPDATA\Programs\AURA" }
  $open = @(Get-Process AURA -ErrorAction SilentlyContinue)
  if ($DryRun) {
    Step "2/3 Fecharia o AURA ($(if ($open.Count) { 'está aberto' } else { 'está fechado' }))"
    Step "3/3 Instalaria a versão nova por cima da de $dir ($(if (Test-Path "$dir\AURA.exe") { 'instalada' } else { 'não há versão instalada' }))$(if (-not $NoStart) { ' e abriria o AURA' })"
    Write-Host "Simulação: nada foi mudado." -ForegroundColor Yellow
    return
  }

  Step "2/3 Fechando o AURA, se estiver aberto..."
  $open | ForEach-Object { [void]$_.CloseMainWindow() }
  for ($i = 0; $i -lt 30 -and (Get-Process AURA -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 500 }
  Get-Process AURA -ErrorAction SilentlyContinue | Stop-Process -Force
  # um Stockfish que ficou para trás prenderia arquivos da pasta do AURA
  Get-Process stockfish -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$dir\*" } | Stop-Process -Force
  Start-Sleep -Seconds 1

  # Por cima, sem desinstalar antes: o instalador troca a pasta _internal inteira, e no modo silencioso
  # ele refaz o atalho da área de trabalho só se ele existe (desinstalar antes o apagaria de vez).
  Step "3/3 Instalando a versão nova por cima, em $dir (seus dados ficam)..."
  $p = Start-Process $setup.FullName -ArgumentList "/S /D=$dir" -PassThru
  $null = $p.Handle  # guarda o handle, senão o ExitCode pode vir vazio
  $p.WaitForExit()
  if ($p.ExitCode -eq 2) { throw "o instalador achou o AURA ainda aberto e parou (código 2). Feche o AURA e rode de novo." }
  if ($p.ExitCode) { throw "o instalador terminou com o código $($p.ExitCode)" }
  if (-not (Test-Path "$dir\AURA.exe")) { throw "a instalação não deixou o AURA.exe em $dir" }
  Write-Host "Pronto: AURA atualizado (commit $(git -C $root rev-parse --short HEAD))." -ForegroundColor Green
  if (-not $NoStart) { Start-Process "$dir\AURA.exe" }
} catch {
  Write-Host "Parou: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}
