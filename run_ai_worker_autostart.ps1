[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
Set-Location $root
$script:TeacherAIWorkerEventSource = "TeacherAIWorker"
$script:TeacherAIWorkerEventLog = "Application"

function Write-TeacherAIWorkerEvent {
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
    if ([System.Diagnostics.EventLog]::SourceExists($script:TeacherAIWorkerEventSource)) {
      Write-EventLog `
        -LogName $script:TeacherAIWorkerEventLog `
        -Source $script:TeacherAIWorkerEventSource `
        -EventId $EventId `
        -EntryType $EntryType `
        -Message $safeMessage `
        -ErrorAction Stop
      return
    }
  } catch {
    # Event Log access is best-effort and must never prevent Worker startup.
  }
  $fallback = "TeacherAIWorker event $EventId ($EntryType): $safeMessage"
  if ($EntryType -eq "Information") { Write-Host $fallback }
  else { Write-Warning $fallback }
}

function Load-LocalWorkerEnvironment {
  $envFile = Join-Path $root ".local-worker.env"
  if (-not (Test-Path $envFile -PathType Leaf)) { return }
  Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') {
      [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
  }
}

function Test-Enabled([string]$Value, [bool]$Default = $true) {
  $normalized = ([string]$Value).Trim().ToLowerInvariant()
  if (-not $normalized) { return $Default }
  return -not (@("0", "false", "no", "off") -contains $normalized)
}

function Test-AIWorkerConfiguration {
  if (-not ([string]$env:DATABASE_URL).Trim()) {
    Write-TeacherAIWorkerEvent -EntryType "Error" -EventId 3101 -Message "Production database configuration is missing; AI Worker cannot consume the shared durable queues."
    Write-Warning "DATABASE_URL is required for the dedicated AI Worker."
    exit 20
  }

  $externalEnabled = Test-Enabled ([string]$env:AI_EXTERNAL_PROCESSING_ENABLED) $true
  $provider = ([string]$env:AI_PROVIDER).Trim().ToLowerInvariant()
  if (-not $provider) { $provider = "groq" }
  if ($externalEnabled) {
    $providerReady = $true
    if ($provider -eq "groq") { $providerReady = [bool]([string]$env:GROQ_API_KEY).Trim() }
    elseif ($provider -eq "gemini") { $providerReady = [bool]([string]$env:GEMINI_API_KEY).Trim() }
    elseif ($provider -eq "openai") { $providerReady = [bool]([string]$env:OPENAI_API_KEY).Trim() }
    elseif ($provider -eq "auto") {
      $providerReady = [bool](
        ([string]$env:GROQ_API_KEY).Trim() -or
        ([string]$env:GEMINI_API_KEY).Trim() -or
        ([string]$env:OPENAI_API_KEY).Trim()
      )
    }
    if (-not $providerReady) {
      Write-TeacherAIWorkerEvent -EntryType "Warning" -EventId 2202 -Message "The configured external AI provider has no local credential; AI question and script jobs will remain unavailable until configuration is completed."
    }
  }

  $narrationReady = (
    [bool]([string]$env:OPENAI_API_KEY).Trim() -and
    [bool]([string]$env:R2_ACCOUNT_ID).Trim() -and
    [bool]([string]$env:R2_ACCESS_KEY_ID).Trim() -and
    [bool]([string]$env:R2_SECRET_ACCESS_KEY).Trim() -and
    [bool]([string]$env:R2_BUCKET_NAME).Trim()
  )
  if (-not $narrationReady) {
    Write-TeacherAIWorkerEvent -EntryType "Warning" -EventId 2201 -Message "AI narration is not fully configured; AI question and script queues can continue independently."
  }
}

function Ensure-AIWorkerEnvironment {
  $python = Join-Path $root ".venv\Scripts\python.exe"
  $entry = Join-Path $root "ai_question_worker.py"
  if (-not (Test-Path $python -PathType Leaf)) {
    throw "Missing .venv\\Scripts\\python.exe; create the shared Worker virtual environment first."
  }
  if (-not (Test-Path $entry -PathType Leaf)) {
    throw "Missing ai_question_worker.py."
  }
  & $python -c "import requests, psycopg" 2>$null
  if ($LASTEXITCODE -ne 0) {
    throw "AI Worker Python requirements are unavailable; run pip install -r requirements.txt in the shared .venv first."
  }
  return @($python, $entry)
}

Load-LocalWorkerEnvironment
Test-AIWorkerConfiguration
Write-TeacherAIWorkerEvent -EntryType "Information" -EventId 1100 -Message "Teacher AI Worker supervisor starting."
Write-Host "Teacher AI Worker: ai_questions, media_scripts, media_audio"

$crashRestarts = 0
$maxCrashRestarts = 5
while ($true) {
  try {
    $runtime = Ensure-AIWorkerEnvironment
    $python = $runtime[0]
    $entry = $runtime[1]
  } catch {
    Write-TeacherAIWorkerEvent -EntryType "Error" -EventId 3103 -Message "AI Worker environment or launch prerequisite is unavailable; supervisor stopped."
    Write-Warning "AI Worker environment or launch prerequisite is unavailable; supervisor stopped."
    exit 31
  }

  try {
    & $python -u $entry
    $workerExit = $LASTEXITCODE
  } catch {
    Write-TeacherAIWorkerEvent -EntryType "Error" -EventId 3104 -Message "AI Worker process launch failed; supervisor stopped."
    Write-Warning "AI Worker process launch failed; supervisor stopped."
    exit 32
  }

  if ($workerExit -eq 0) { exit 0 }
  if ($workerExit -eq 75) {
    Write-TeacherAIWorkerEvent -EntryType "Information" -EventId 1110 -Message "AI Worker requested an approved restart."
    $crashRestarts = 0
    Start-Sleep -Seconds 2
    continue
  }

  $crashRestarts++
  if ($crashRestarts -gt $maxCrashRestarts) {
    Write-TeacherAIWorkerEvent -EntryType "Error" -EventId 3105 -Message "AI Worker restart limit exhausted; supervisor stopped to avoid a restart loop."
    Write-Warning "AI Worker crashed too many times; stopping to avoid a restart loop."
    exit $workerExit
  }
  Write-TeacherAIWorkerEvent -EntryType "Warning" -EventId 2200 -Message "AI Worker exited abnormally and will be restarted by the supervisor."
  Write-Warning "AI Worker exited with code $workerExit; restarting in 5 seconds ($crashRestarts/$maxCrashRestarts)."
  Start-Sleep -Seconds 5
}
