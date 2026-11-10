# AURA's in-place updater for Windows. The app starts it detached ("Atualizar agora", see
# backend/app/services/updater.py) right before closing itself. It waits for AURA to exit, runs
# the new installer silently into the same folder, then starts AURA again. The data folder is
# never touched. Kept ASCII on purpose (Windows PowerShell 5.1 reads BOM-less files as ANSI):
# the app turns -Result into the message the person reads.
#
#   powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File apply_update.ps1
#     -Installer <AURA-Setup-X.exe> -InstallDir <folder> -WaitPid <pid> -Version <X>
#     -Result <result.json> [-Log <update.log>] [-WaitSeconds 60] [-NoStart]
#
# -Result receives {"ok", "step", "code", "version"}; "step" says where it stopped:
# wait (AURA did not close), install (installer exit code in "code"), check (no AURA.exe after
# the install), version (the uninstall entry shows another version), error (anything else).
param(
  [Parameter(Mandatory = $true)][string]$Installer,
  [Parameter(Mandatory = $true)][string]$InstallDir,
  [Parameter(Mandatory = $true)][int]$WaitPid,
  [Parameter(Mandatory = $true)][string]$Version,
  [Parameter(Mandatory = $true)][string]$Result,
  [string]$Log = "",
  [int]$WaitSeconds = 60,
  [switch]$NoStart
)
$ErrorActionPreference = "Stop"
$dir = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$prefix = $dir.ToLowerInvariant() + '\'
$step = "error"
$code = $null
$ok = $false

function Write-Log([string]$text) {
  if (-not $Log) { return }
  try { Add-Content -LiteralPath $Log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"), $text) -Encoding UTF8 } catch { }
}

function Save-Result([bool]$success) {
  try {
    $json = @{ ok = $success; step = $step; code = $code; version = $Version } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($Result, $json)  # UTF-8 without BOM
  } catch { Write-Log "could not write ${Result}: $($_.Exception.Message)" }
}

function Test-InFolder($process) {
  try { return [bool]($process.Path -and $process.Path.ToLowerInvariant().StartsWith($prefix)) } catch { return $false }
}

# AURA.exe, its window process and Stockfish all run from the install folder and hold its files.
function Get-FolderProcesses { @(Get-Process -ErrorAction SilentlyContinue | Where-Object { Test-InFolder $_ }) }

$mutex = $null
try {
  # while this exists, opening AURA says "being updated" instead of locking files the installer replaces
  $mutex = New-Object System.Threading.Mutex($false, "Local\AURA-ChessLab1800-update")
  Write-Log "update to ${Version}: installer $Installer, folder $dir, AURA pid $WaitPid"

  $step = "wait"
  $main = Get-Process -Id $WaitPid -ErrorAction SilentlyContinue
  if ($main -and -not (Test-InFolder $main)) { $main = $null }  # the pid was reused: AURA is gone already
  if ($main -and -not $main.WaitForExit($WaitSeconds * 1000)) {
    Write-Log "AURA ($WaitPid) still running after $WaitSeconds s: stopping it"
    Stop-Process -Id $WaitPid -Force -ErrorAction SilentlyContinue
    [void]$main.WaitForExit(10000)
  }
  for ($i = 0; $i -lt 40 -and (Get-FolderProcesses).Count; $i++) { Start-Sleep -Milliseconds 250 }
  foreach ($p in Get-FolderProcesses) {
    Write-Log "stopping $($p.ProcessName) ($($p.Id)), still running from the folder"
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Milliseconds 500
  if ((Get-FolderProcesses).Count) { throw "programs from $dir are still running" }

  $step = "install"
  # /D= must be the last argument and is never quoted: NSIS takes the rest of the line as the folder.
  # Process.Start passes exactly this (Start-Process would add a trailing space; NSIS trims it, but why rely on it).
  Write-Log "running the installer: /S /D=$dir"
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $Installer
  $psi.Arguments = "/S /D=$dir"
  $psi.UseShellExecute = $false
  $setup = [System.Diagnostics.Process]::Start($psi)
  $setup.WaitForExit()
  $code = $setup.ExitCode
  Write-Log "installer exit code $code"
  if ($code -ne 0) { throw "the installer stopped with exit code $code" }

  $step = "check"
  if (-not (Test-Path -LiteralPath (Join-Path $dir "AURA.exe"))) { throw "no AURA.exe in $dir after the install" }
  $step = "version"
  $entry = Get-ChildItem "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
    ForEach-Object { Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue } |
    Where-Object { $_.InstallLocation -and ([string]$_.InstallLocation).TrimEnd('\') -ieq $dir } |
    Select-Object -First 1
  if ($entry -and $entry.DisplayVersion -ne $Version) { throw "the folder now has version $($entry.DisplayVersion)" }
  if (-not $entry) { Write-Log "no uninstall entry points at ${dir}: version not checked" }

  Remove-Item -LiteralPath $Installer -Force -ErrorAction SilentlyContinue
  $step = "done"
  $ok = $true
  Write-Log "update to $Version done"
} catch {
  Write-Log "stopped at '$step': $($_.Exception.Message)"
} finally {
  Save-Result $ok
  if ($mutex) { $mutex.Dispose() }
}

# Start AURA again: the new version, or the old one when nothing was replaced.
$exe = Join-Path $dir "AURA.exe"
if (-not $NoStart -and (Test-Path -LiteralPath $exe) -and -not (Get-FolderProcesses).Count) {
  Write-Log "starting $exe"
  try { Start-Process -FilePath $exe -WorkingDirectory $dir } catch { Write-Log "could not start AURA: $($_.Exception.Message)" }
}
if ($ok) { exit 0 } else { exit 1 }
