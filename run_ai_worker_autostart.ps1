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
  $fallbackEnabled = Test-Enabled ([string]$env:AI_FREE_FALLBACK_ENABLED) $true
  $ollamaEnabled = Test-Enabled ([string]$env:OLLAMA_ENABLED) $false
  $provider = ([string]$env:AI_PROVIDER).Trim().ToLowerInvariant()
  if (-not $provider) { $provider = "groq" }

  $groqReady = [bool]([string]$env:GROQ_API_KEY).Trim()
  $geminiReady = [bool]([string]$env:GEMINI_API_KEY).Trim()
  $localReady = $fallbackEnabled -and $ollamaEnabled -and [bool]([string]$env:OLLAMA_MODEL).Trim()
  $providerReady = $false
  if ($externalEnabled) {
    if ($provider -eq "groq") { $providerReady = $groqReady }
    elseif ($provider -eq "gemini") { $providerReady = $geminiReady }
    elseif ($provider -eq "auto") { $providerReady = $groqReady -or $geminiReady }
  }
  if ($fallbackEnabled) {
    $providerReady = $providerReady -or ($externalEnabled -and ($groqReady -or $geminiReady)) -or $localReady
  }
  if (-not $providerReady) {
    Write-TeacherAIWorkerEvent -EntryType "Warning" -EventId 2202 -Message "No configured free AI provider is ready; question and script jobs will remain unavailable until Groq, Gemini, or local Ollama is configured."
  }

  $narrationReady = (
    ([string]$env:AI_TTS_PROVIDER).Trim().ToLowerInvariant() -in @("", "kokoro") -and
    [bool]([string]$env:R2_ACCOUNT_ID).Trim() -and
    [bool]([string]$env:R2_ACCESS_KEY_ID).Trim() -and
    [bool]([string]$env:R2_SECRET_ACCESS_KEY).Trim() -and
    [bool]([string]$env:R2_BUCKET_NAME).Trim()
  )
  if (-not $narrationReady) {
    Write-TeacherAIWorkerEvent -EntryType "Warning" -EventId 2201 -Message "Free local narration is not fully configured; AI question and script queues can continue independently."
  }
}

function Ensure-AIWorkerEnvironment {
  $python = Join-Path $root ".venv\Scripts\python.exe"
  $entry = Join-Path $root "ai_question_worker.py"
  $requirements = Join-Path $root "requirements-ai-worker.txt"
  $stamp = Join-Path $root ".ai-worker-requirements.sha256"
  if (-not (Test-Path $python -PathType Leaf)) {
    throw "Missing .venv\\Scripts\\python.exe; create the shared Worker virtual environment first."
  }
  if (-not (Test-Path $entry -PathType Leaf)) {
    throw "Missing ai_question_worker.py."
  }
  if (-not (Test-Path $requirements -PathType Leaf)) {
    throw "Missing requirements-ai-worker.txt."
  }

  $hash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
  $recorded = if (Test-Path $stamp) { (Get-Content -LiteralPath $stamp -Raw).Trim() } else { "" }
  & $python -c "import requests, psycopg, kokoro, faster_whisper; from google import genai; from misaki import zh; import numpy" 2>$null
  $importsOk = $LASTEXITCODE -eq 0
  if ($hash -ne $recorded -or -not $importsOk) {
    Write-Host "Synchronizing AI Worker Python requirements (Kokoro, Gemini fallback, local Whisper)..."
    & $python -m pip install -r $requirements
    $installExit = $LASTEXITCODE
    & $python -c "import requests, psycopg, kokoro, faster_whisper; from google import genai; from misaki import zh; import numpy" 2>$null
    $importsOk = $LASTEXITCODE -eq 0
    if ($installExit -eq 0 -and $importsOk) {
      Set-Content -LiteralPath $stamp -Value $hash -NoNewline -Encoding UTF8
    } elseif (-not $importsOk) {
      throw "AI Worker requirements are unavailable after synchronization."
    } else {
      Write-Warning "AI Worker dependency synchronization failed; existing importable environment will be used."
    }
  }
  return @($python, $entry)
}

Load-LocalWorkerEnvironment
if (-not $env:FREE_ONLY_MODE) { $env:FREE_ONLY_MODE = "true" }
if (-not $env:AI_FREE_FALLBACK_ENABLED) { $env:AI_FREE_FALLBACK_ENABLED = "true" }
if (-not $env:AI_TTS_PROVIDER) { $env:AI_TTS_PROVIDER = "kokoro" }
Test-AIWorkerConfiguration
Write-TeacherAIWorkerEvent -EntryType "Information" -EventId 1100 -Message "Teacher AI Worker supervisor starting with free provider fallback and local Kokoro narration."
Write-Host "Teacher AI Worker: ai_questions, media_scripts, media_audio (Groq/Gemini/Ollama fallback; Kokoro local TTS)"

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
