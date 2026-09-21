[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
Set-Location $root
$script:TeacherWorkerEventSource = "TeacherMaterialWorker"
$script:TeacherWorkerEventLog = "Application"

function Write-TeacherWorkerEvent {
  param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Information", "Warning", "Error")]
    [string]$EntryType,
    [Parameter(Mandatory = $true)]
    [ValidateRange(1000, 3999)]
    [int]$EventId,
    [Parameter(Mandatory = $true)]
    [string]$Message
  )
  $safeMessage = ([string]$Message -replace '[\r\n]+', ' ').Trim()
  if ($safeMessage.Length -gt 600) { $safeMessage = $safeMessage.Substring(0, 600) }
  try {
    if ([System.Diagnostics.EventLog]::SourceExists($script:TeacherWorkerEventSource)) {
      Write-EventLog `
        -LogName $script:TeacherWorkerEventLog `
        -Source $script:TeacherWorkerEventSource `
        -EventId $EventId `
        -EntryType $EntryType `
        -Message $safeMessage `
        -ErrorAction Stop
      return
    }
  } catch {
    # Event Log access is best-effort. Never let source/ACL/service failures
    # prevent the Worker from starting or following its restart policy.
  }
  $fallback = "TeacherMaterialWorker event $EventId ($EntryType): $safeMessage"
  if ($EntryType -eq "Information") { Write-Host $fallback }
  else { Write-Warning $fallback }
}

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
  Write-TeacherWorkerEvent -EntryType "Error" -EventId 3001 -Message "Required Worker connection settings are missing; supervisor cannot start."
  Write-Warning "Required Worker connection settings are missing; supervisor cannot start."
  exit 20
}
Write-TeacherWorkerEvent -EntryType "Information" -EventId 1000 -Message "Teacher material Worker supervisor starting."

$autoUpdateEnabled = @("1", "true", "yes", "on") -contains ([string]$env:MATERIAL_WORKER_AUTO_UPDATE).Trim().ToLowerInvariant()
if ($autoUpdateEnabled) {
  $updater = Join-Path $root "update_material_worker.ps1"
  if (Test-Path $updater -PathType Leaf) {
    & $updater
    if ($LASTEXITCODE -ne 0) {
      Write-TeacherWorkerEvent -EntryType "Warning" -EventId 2002 -Message "Safe updater was refused or failed; existing Worker version will start."
      Write-Warning "Safe update did not run; starting the existing local Worker version."
    } else {
      Write-TeacherWorkerEvent -EntryType "Information" -EventId 1001 -Message "Safe updater check completed successfully before Worker launch."
    }
  } else {
    Write-TeacherWorkerEvent -EntryType "Warning" -EventId 2001 -Message "Safe updater script is missing; existing Worker version will start."
    Write-Warning "Safe updater is missing; starting the existing local Worker version."
  }
} else {
  Write-TeacherWorkerEvent -EntryType "Information" -EventId 1002 -Message "Safe updater is disabled by configuration; existing Worker version will start."
}

$crashRestarts = 0
$maxCrashRestarts = 5
while ($true) {
  try {
    $python = Ensure-WorkerEnvironment
  } catch {
    Write-TeacherWorkerEvent -EntryType "Error" -EventId 3002 -Message "Worker environment or launch prerequisite is unavailable; supervisor stopped."
    Write-Warning "Worker environment or launch prerequisite is unavailable; supervisor stopped."
    exit 31
  }
  try {
    & $python -u (Join-Path $root "material_worker.py")
    $workerExit = $LASTEXITCODE
  } catch {
    Write-TeacherWorkerEvent -EntryType "Error" -EventId 3003 -Message "Worker process launch failed; supervisor stopped."
    Write-Warning "Worker process launch failed; supervisor stopped."
    exit 32
  }
  if ($workerExit -eq 0) { exit 0 }
  if ($workerExit -eq 75) {
    Write-TeacherWorkerEvent -EntryType "Information" -EventId 1010 -Message "Worker requested an approved post-update restart."
    Write-Host "Worker requested safe post-update restart."
    $crashRestarts = 0
    Start-Sleep -Seconds 2
    continue
  }
  $crashRestarts++
  if ($crashRestarts -gt $maxCrashRestarts) {
    Write-TeacherWorkerEvent -EntryType "Error" -EventId 3004 -Message "Worker restart limit exhausted; supervisor stopped to avoid a restart loop."
    Write-Warning "Worker crashed too many times; stopping to avoid a restart loop."
    exit $workerExit
  }
  Write-TeacherWorkerEvent -EntryType "Warning" -EventId 2100 -Message "Worker exited abnormally and will be restarted by the supervisor."
  Write-Warning "Worker exited with code $workerExit; restarting in 5 seconds ($crashRestarts/$maxCrashRestarts)."
  Start-Sleep -Seconds 5
}
