[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
Set-Location $root

function Load-LocalWorkerEnvironment {
  $envFile = Join-Path $root ".local-worker.env"
  if (-not (Test-Path $envFile -PathType Leaf)) { return }
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') {
      [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
  }
}

function Add-MegaCmdPath {
  $megaDirectories = @(
    $env:MEGACMD_PATH,
    $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles "MEGAcmd" }),
    $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} "MEGAcmd" })
  ) | Where-Object { $_ -and (Test-Path $_ -PathType Container) }
  $pathParts = @($env:Path -split [regex]::Escape([IO.Path]::PathSeparator) | Where-Object { $_ })
  foreach ($directory in $megaDirectories) {
    if ($pathParts -notcontains $directory) { $pathParts = @($directory) + $pathParts }
  }
  $env:Path = $pathParts -join [IO.Path]::PathSeparator
}

function Test-WorkerCommand([string]$Name, [string]$EnvironmentPath) {
  $candidate = [string](Get-Item -LiteralPath ("Env:" + $EnvironmentPath) -ErrorAction SilentlyContinue).Value
  if ($candidate -and (Test-Path $candidate -PathType Leaf)) { return $true }
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Ensure-WorkerEnvironment {
  $python = Join-Path $root ".venv\Scripts\python.exe"
  if (-not (Test-Path $python -PathType Leaf)) { throw "Missing .venv\\Scripts\\python.exe; create the Worker virtual environment first." }
  $requirements = Join-Path $root "requirements.txt"
  $stamp = Join-Path $root ".worker-requirements.sha256"
  $hash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
  $recorded = if (Test-Path $stamp) { (Get-Content $stamp -Raw).Trim() } else { "" }
  & $python -c "import requests" 2>$null
  $importsOk = $LASTEXITCODE -eq 0
  if ($hash -ne $recorded -or -not $importsOk) {
    Write-Host "Synchronizing Worker Python requirements..."
    & $python -m pip install -r $requirements
    $installExit = $LASTEXITCODE
    & $python -c "import requests" 2>$null
    $importsOk = $LASTEXITCODE -eq 0
    if ($installExit -eq 0 -and $importsOk) { Set-Content -LiteralPath $stamp -Value $hash -NoNewline }
    elseif (-not $importsOk) { throw "Worker requirements are unavailable after a failed synchronization." }
    else { Write-Warning "Requirement synchronization failed; existing importable environment will be used." }
  }
  $ffmpeg = Test-WorkerCommand "ffmpeg" "FFMPEG_PATH"
  $ffprobe = Test-WorkerCommand "ffprobe" "FFPROBE_PATH"
  $office = Test-WorkerCommand "soffice" "SOFFICE_PATH"
  $mega = [bool](Get-Command "mega-login" -ErrorAction SilentlyContinue)
  Write-Host "Capabilities: FFmpeg=$ffmpeg FFprobe=$ffprobe LibreOffice=$office MEGAcmd=$mega"
  return $python
}

Load-LocalWorkerEnvironment
Add-MegaCmdPath
if (-not $env:TEACHER_BASE_URL -or -not $env:MATERIAL_WORKER_TOKEN) {
  throw "Set TEACHER_BASE_URL and MATERIAL_WORKER_TOKEN in .local-worker.env or this session."
}

$updater = Join-Path $root "update_material_worker.ps1"
if (Test-Path $updater -PathType Leaf) {
  & $updater
  if ($LASTEXITCODE -ne 0) { Write-Warning "Safe update did not run; starting the existing local Worker version." }
} else { Write-Warning "Safe updater is missing; starting the existing local Worker version." }

$crashRestarts = 0
$maxCrashRestarts = 5
while ($true) {
  $python = Ensure-WorkerEnvironment
  & $python -u (Join-Path $root "material_worker.py")
  $workerExit = $LASTEXITCODE
  if ($workerExit -eq 0) { exit 0 }
  if ($workerExit -eq 75) {
    Write-Host "Worker requested safe post-update restart."
    $crashRestarts = 0
    Start-Sleep -Seconds 2
    continue
  }
  $crashRestarts++
  if ($crashRestarts -gt $maxCrashRestarts) {
    Write-Error "Worker crashed too many times; stopping to avoid a restart loop."
    exit $workerExit
  }
  Write-Warning "Worker exited with code $workerExit; restarting in 5 seconds ($crashRestarts/$maxCrashRestarts)."
  Start-Sleep -Seconds 5
}
