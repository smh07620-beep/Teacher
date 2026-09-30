[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$ReleaseRef = "",
  [string]$ReleaseCommit = "",
  [switch]$InstallOptionalTools,
  [switch]$InstallTasks,
  [switch]$ServiceAccount,
  [string]$TaskUser = "",
  [switch]$StartNow,
  [switch]$RestartTasks,
  [switch]$SkipDownloads,
  [switch]$SkipPythonSync,
  [switch]$SkipReleaseUpdate,
  [switch]$NonInteractive,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
Set-Location $root
$envFile = Join-Path $root ".local-worker.env"
$envTemplate = Join-Path $root ".local-worker.env.example"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$requirements = Join-Path $root "requirements-ai-worker.txt"
$workerInstaller = Join-Path $root "install_teacher_workers.ps1"
$releaseUpdater = Join-Path $root "update_material_worker.ps1"
$script:Warnings = New-Object System.Collections.Generic.List[string]

function Write-Step([string]$Message) {
  Write-Host "[Teacher Worker] $Message"
}

function Add-Warning([string]$Message) {
  $script:Warnings.Add($Message)
  Write-Warning $Message
}

function Test-Enabled([string]$Value, [bool]$Default = $false) {
  $normalized = ([string]$Value).Trim().ToLowerInvariant()
  if (-not $normalized) { return $Default }
  return @("1", "true", "yes", "on") -contains $normalized
}

function Test-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Import-WorkerEnvironment {
  if (-not (Test-Path $envFile -PathType Leaf)) { return }
  Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') {
      [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
  }
}

function Test-ConfiguredValue([string]$Name) {
  $value = [string][Environment]::GetEnvironmentVariable($Name, "Process")
  if (-not $value.Trim()) { return $false }
  return -not $value.Trim().StartsWith("REPLACE_WITH_", [StringComparison]::OrdinalIgnoreCase)
}

function Assert-RepositorySafe {
  if (-not (Test-Path (Join-Path $root ".git") -PathType Container)) {
    throw "setup_teacher_worker.ps1 must run from the Teacher repository root."
  }
  foreach ($path in @($requirements, $workerInstaller, $releaseUpdater, $envTemplate)) {
    if (-not (Test-Path $path -PathType Leaf)) {
      throw "Required Worker file is missing: $([IO.Path]::GetFileName($path))"
    }
  }
}

function Ensure-LocalEnv {
  if (Test-Path $envFile -PathType Leaf) { return }
  if ($DryRun) {
    Add-Warning ".local-worker.env is missing; dry-run will not create it."
    return
  }
  if (-not $PSCmdlet.ShouldProcess($envFile, "Create local Worker environment template")) { return }
  Copy-Item -LiteralPath $envTemplate -Destination $envFile -ErrorAction Stop
  Add-Warning ".local-worker.env was created from the example. Fill its placeholders locally before starting Workers."
}

function Invoke-ApprovedReleaseUpdate {
  if ($SkipReleaseUpdate) {
    Write-Step "Approved release update skipped by parameter."
    return
  }
  $effectiveRef = $ReleaseRef.Trim()
  if (-not $effectiveRef) {
    $effectiveRef = ([string]$env:MATERIAL_WORKER_RELEASE_REF).Trim()
  }
  if (-not $effectiveRef) {
    Add-Warning "No approved release ref was supplied; repository checkout was left unchanged. Use -ReleaseRef with an annotated approved tag when upgrading code."
    return
  }
  if ($DryRun) {
    Write-Step "Dry-run: would invoke canonical signed-release updater for tag '$effectiveRef'."
    return
  }
  $dirty = & git status --porcelain --untracked-files=all
  if ($LASTEXITCODE -ne 0) { throw "Could not inspect git working tree." }
  if ($dirty) {
    throw "Working tree is dirty. Bootstrap refuses to stash, reset, clean, or overwrite local changes."
  }
  [Environment]::SetEnvironmentVariable("MATERIAL_WORKER_RELEASE_REF", $effectiveRef, "Process")
  if ($ReleaseCommit.Trim()) {
    [Environment]::SetEnvironmentVariable("MATERIAL_WORKER_RELEASE_COMMIT", $ReleaseCommit.Trim(), "Process")
  }
  Write-Step "Invoking canonical approved-release updater."
  & $releaseUpdater
  if ($LASTEXITCODE -ne 0) {
    throw "Approved Worker release update was refused; the checkout was left unchanged."
  }
}

function Resolve-PythonLauncher {
  if (Test-Path $venvPython -PathType Leaf) { return @($venvPython) }
  $py = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue
  if ($py) {
    & $py.Source -3.12 -c "import sys; print(sys.version_info[:2])" *> $null
    if ($LASTEXITCODE -eq 0) { return @($py.Source, "-3.12") }
  }
  $python = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue
  if ($python) { return @($python.Source) }
  throw "Python is missing. Install Python 3.12 x64, then run this bootstrap again."
}

function Ensure-PythonEnvironment {
  if ($SkipPythonSync) {
    Write-Step "Python environment synchronization skipped by parameter."
    return
  }
  $launcher = Resolve-PythonLauncher
  if (-not (Test-Path $venvPython -PathType Leaf)) {
    if ($DryRun) {
      Write-Step "Dry-run: would create .venv from the detected Python runtime."
      return
    }
    Write-Step "Creating shared Worker virtual environment."
    if ($launcher.Count -eq 2) { & $launcher[0] $launcher[1] -m venv .venv }
    else { & $launcher[0] -m venv .venv }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython -PathType Leaf)) {
      throw "Could not create .venv."
    }
  }

  & $venvPython -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,14); print('Python', sys.version.split()[0])"
  if ($LASTEXITCODE -ne 0) {
    throw "Worker Python must be 3.11-3.13; Python 3.12 is the canonical deployment version."
  }
  if ($DryRun) {
    Write-Step "Dry-run: would synchronize requirements-ai-worker.txt."
    return
  }
  Write-Step "Synchronizing AI Worker Python requirements."
  & $venvPython -m pip install --disable-pip-version-check -r $requirements
  if ($LASTEXITCODE -ne 0) { throw "requirements-ai-worker.txt installation failed." }
  & $venvPython -c "import requests, psycopg, pptx, kokoro, faster_whisper, numpy; from google import genai; from misaki import zh; print('AI Worker Python imports OK')"
  if ($LASTEXITCODE -ne 0) { throw "AI Worker dependency import self-test failed." }
}

function Install-WingetPackage([string]$Id, [string]$Label) {
  if ($SkipDownloads) {
    Add-Warning "$Label is missing and -SkipDownloads was set."
    return $false
  }
  if (-not $InstallOptionalTools) {
    Add-Warning "$Label is missing. Re-run with -InstallOptionalTools to let bootstrap use winget, or install it manually."
    return $false
  }
  $winget = Get-Command winget.exe -CommandType Application -ErrorAction SilentlyContinue
  if (-not $winget) {
    Add-Warning "$Label is missing and winget is unavailable; install it manually."
    return $false
  }
  if ($DryRun) {
    Write-Step "Dry-run: would install $Label with winget package $Id."
    return $true
  }
  Write-Step "Installing optional tool: $Label."
  & $winget.Source install --id $Id -e --accept-package-agreements --accept-source-agreements --silent
  if ($LASTEXITCODE -ne 0) {
    Add-Warning "$Label winget installation did not complete successfully."
    return $false
  }
  return $true
}

function Ensure-FFmpeg {
  $ffmpeg = Get-Command ffmpeg.exe -CommandType Application -ErrorAction SilentlyContinue
  if (-not $ffmpeg) {
    [void](Install-WingetPackage "Gyan.FFmpeg" "FFmpeg")
    $ffmpeg = Get-Command ffmpeg.exe -CommandType Application -ErrorAction SilentlyContinue
  }
  if (-not $ffmpeg) {
    Add-Warning "FFmpeg is not currently available in PATH; AI video jobs cannot render until it is installed and the Worker is restarted."
    return
  }
  & $ffmpeg.Source -version 2>$null | Select-Object -First 1 | ForEach-Object { Write-Step $_ }
}

function Ensure-Ollama {
  if (-not (Test-Enabled ([string]$env:OLLAMA_ENABLED) $false)) {
    Write-Step "Ollama fallback is disabled; no local LLM model download is needed."
    return
  }
  $ollama = Get-Command ollama.exe -CommandType Application -ErrorAction SilentlyContinue
  if (-not $ollama) {
    [void](Install-WingetPackage "Ollama.Ollama" "Ollama")
    $ollama = Get-Command ollama.exe -CommandType Application -ErrorAction SilentlyContinue
  }
  if (-not $ollama) {
    Add-Warning "OLLAMA_ENABLED=true but Ollama is unavailable. Cloud providers can continue; local LLM fallback is not ready."
    return
  }
  $model = ([string]$env:OLLAMA_MODEL).Trim()
  if (-not $model) {
    Add-Warning "OLLAMA_ENABLED=true but OLLAMA_MODEL is empty."
    return
  }
  $installed = & $ollama.Source list 2>$null
  if ($LASTEXITCODE -ne 0) {
    Add-Warning "Ollama is installed but its local service/model list is not currently reachable."
    return
  }
  $escaped = [Regex]::Escape($model)
  if (($installed -join "`n") -match "(?m)^$escaped\s") {
    Write-Step "Configured Ollama model is already present; download skipped."
    return
  }
  if ($SkipDownloads) {
    Add-Warning "Configured Ollama model is missing and -SkipDownloads was set."
    return
  }
  if ($DryRun) {
    Write-Step "Dry-run: would pull the configured Ollama model because it is not installed."
    return
  }
  Write-Step "Pulling configured Ollama model because it is not installed yet."
  & $ollama.Source pull $model
  if ($LASTEXITCODE -ne 0) { Add-Warning "Ollama model pull failed; local LLM fallback remains unavailable." }
}

function Test-SharedStorageConfiguration {
  $videoBackend = ([string]$env:AI_VIDEO_STORAGE_BACKEND).Trim().ToLowerInvariant()
  $pptBackend = ([string]$env:AI_PRESENTATION_STORAGE_BACKEND).Trim().ToLowerInvariant()
  $localVideo = $videoBackend -eq "local" -and (Test-Enabled ([string]$env:AI_VIDEO_ALLOW_LOCAL_STORAGE) $false)
  $localPpt = $pptBackend -eq "local" -and (Test-Enabled ([string]$env:AI_PRESENTATION_ALLOW_LOCAL_STORAGE) $false)
  if ($localVideo -or $localPpt) {
    Add-Warning "Local presentation/video storage is enabled. Keep this only for single-host development; production Web and Worker require a shared durable provider."
  }

  $r2Ready = (Test-ConfiguredValue "R2_ACCOUNT_ID") -and (Test-ConfiguredValue "R2_ACCESS_KEY_ID") -and (Test-ConfiguredValue "R2_SECRET_ACCESS_KEY") -and (Test-ConfiguredValue "R2_BUCKET_NAME")
  $gdriveReady = (Test-ConfiguredValue "GDRIVE_CLIENT_ID") -and (Test-ConfiguredValue "GDRIVE_CLIENT_SECRET") -and (Test-ConfiguredValue "GDRIVE_REFRESH_TOKEN") -and (Test-ConfiguredValue "GDRIVE_FOLDER_ID")
  $megaReady = (Test-ConfiguredValue "MEGA_EMAIL") -and (Test-ConfiguredValue "MEGA_PASSWORD")
  if (-not ($r2Ready -or $gdriveReady -or $megaReady -or $localVideo -or $localPpt)) {
    Add-Warning "No complete R2/Google Drive/MEGA shared provider configuration was detected. PowerPoint/video durable publication may remain unavailable."
  }
}

function Test-WorkerConfiguration {
  Import-WorkerEnvironment
  $missing = New-Object System.Collections.Generic.List[string]
  foreach ($name in @("TEACHER_BASE_URL", "MATERIAL_WORKER_TOKEN", "DATABASE_URL")) {
    if (-not (Test-ConfiguredValue $name)) { $missing.Add($name) }
  }
  if ($missing.Count -gt 0) {
    Add-Warning ("Required Worker settings need local configuration: " + ($missing -join ", "))
  }
  if (-not (Test-ConfiguredValue "MATERIAL_WORKER_ID")) {
    Add-Warning "MATERIAL_WORKER_ID is not set. Configure a stable host ID so heartbeat/observability survives process restarts."
  }

  $provider = ([string]$env:AI_PROVIDER).Trim().ToLowerInvariant()
  if (-not $provider) { $provider = "groq" }
  $cloudReady = (Test-ConfiguredValue "GROQ_API_KEY") -or (Test-ConfiguredValue "GEMINI_API_KEY")
  $localReady = (Test-Enabled ([string]$env:OLLAMA_ENABLED) $false) -and (Test-ConfiguredValue "OLLAMA_MODEL")
  if (-not ($cloudReady -or $localReady)) {
    Add-Warning "No Groq/Gemini/Ollama AI provider is configured; AI generation queues cannot complete."
  } else {
    Write-Step "AI provider chain has at least one configured provider (values are intentionally hidden)."
  }
  if (([string]$env:AI_TTS_PROVIDER).Trim().ToLowerInvariant() -notin @("", "kokoro")) {
    Add-Warning "AI_TTS_PROVIDER is not the supported local Kokoro provider for the current AI video pipeline."
  }
  Test-SharedStorageConfiguration
}

function Install-WorkerTasks {
  if (-not $InstallTasks) { return }
  if (-not (Test-Administrator)) {
    throw "-InstallTasks requires an elevated PowerShell session because Task Scheduler/Event Log setup is privileged."
  }
  if ($DryRun) {
    Write-Step "Dry-run: would register canonical Material + AI Worker scheduled tasks."
    return
  }
  if ($ServiceAccount) {
    $serviceUser = if ($TaskUser.Trim()) { $TaskUser.Trim() } else { "SYSTEM" }
    & $workerInstaller -TaskUser $serviceUser -ServiceAccount -StartNow:$StartNow
  } elseif ($NonInteractive) {
    throw "Non-interactive task installation requires -ServiceAccount; password credentials are never read from environment variables."
  } else {
    & $workerInstaller -TaskUser $TaskUser -StartNow:$StartNow
  }
  if ($LASTEXITCODE -ne 0) { throw "Scheduled task installation failed." }
}

function Restart-WorkerTasks {
  if (-not $RestartTasks) { return }
  if (-not (Test-Administrator)) {
    throw "-RestartTasks requires an elevated PowerShell session."
  }
  foreach ($taskName in @("Teacher Material Worker", "Teacher AI Worker")) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $task) {
      Add-Warning "Scheduled task '$taskName' is not installed."
      continue
    }
    if ($DryRun) {
      Write-Step "Dry-run: would restart scheduled task '$taskName'."
      continue
    }
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $taskName
    Write-Step "Restarted scheduled task '$taskName'."
  }
}

function Show-TaskHealth {
  foreach ($taskName in @("Teacher Material Worker", "Teacher AI Worker")) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
      Write-Step "Task '$taskName' state: $($task.State)"
    }
  }
}

try {
  Assert-RepositorySafe
  Write-Step "Safe one-click bootstrap/upgrade started. Secrets will not be printed."
  Ensure-LocalEnv
  Import-WorkerEnvironment
  Invoke-ApprovedReleaseUpdate
  Import-WorkerEnvironment
  Ensure-PythonEnvironment
  Ensure-FFmpeg
  Ensure-Ollama
  Test-WorkerConfiguration
  Install-WorkerTasks
  Restart-WorkerTasks
  Show-TaskHealth

  if ($script:Warnings.Count -gt 0) {
    Write-Output "Teacher Worker bootstrap completed with $($script:Warnings.Count) warning(s). Review warnings before relying on AI video production."
    exit 2
  }
  Write-Output "Teacher Worker bootstrap completed successfully. Material Worker + AI Worker prerequisites are ready."
  exit 0
} catch {
  # Never echo environment values or raw exception objects: they can include
  # local paths, credentials, provider URLs, or command arguments.
  [Console]::Error.WriteLine("Teacher Worker bootstrap failed safely. No reset/clean/stash operation was performed.")
  [Console]::Error.WriteLine(([string]$_.Exception.Message -replace '[\r\n]+', ' ').Substring(0, [Math]::Min(240, ([string]$_.Exception.Message).Length)))
  exit 1
}
