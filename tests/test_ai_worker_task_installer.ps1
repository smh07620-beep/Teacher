$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repo "run_ai_worker_autostart.ps1"
$installer = Join-Path $repo "install_ai_worker_task.ps1"
$bundle = Join-Path $repo "install_teacher_workers.ps1"
$bootstrap = Join-Path $repo "setup_teacher_worker.ps1"
$envTemplate = Join-Path $repo ".local-worker.env.example"
$aiRequirements = Join-Path $repo "requirements-ai-worker.txt"

foreach ($path in @($launcher, $installer, $bundle, $bootstrap)) {
  $tokens = $null
  $parseErrors = $null
  [void][System.Management.Automation.Language.Parser]::ParseFile(
    $path,
    [ref]$tokens,
    [ref]$parseErrors
  )
  if ($parseErrors.Count -gt 0) {
    throw "$([IO.Path]::GetFileName($path)) PowerShell parse failed: $($parseErrors[0].Message)"
  }
}

$launcherSource = Get-Content -LiteralPath $launcher -Raw
$installerSource = Get-Content -LiteralPath $installer -Raw
$bundleSource = Get-Content -LiteralPath $bundle -Raw
$bootstrapSource = Get-Content -LiteralPath $bootstrap -Raw
$envSource = Get-Content -LiteralPath $envTemplate -Raw
$requirementsSource = Get-Content -LiteralPath $aiRequirements -Raw

foreach ($marker in @(
  'TeacherAIWorker',
  'ai_question_worker.py',
  'requirements-ai-worker.txt',
  'DATABASE_URL',
  'GROQ_API_KEY',
  'AI_TTS_PROVIDER',
  'kokoro',
  'R2_ACCOUNT_ID',
  'R2_ACCESS_KEY_ID',
  'R2_SECRET_ACCESS_KEY',
  'R2_BUCKET_NAME',
  '-EntryType "Information" -EventId 1100',
  '-EntryType "Warning" -EventId 2200',
  '-EntryType "Warning" -EventId 2201',
  '-EntryType "Warning" -EventId 2202',
  '-EntryType "Error" -EventId 3101',
  '-EntryType "Error" -EventId 3103',
  '-EntryType "Error" -EventId 3104',
  '-EntryType "Error" -EventId 3105'
)) {
  if (-not $launcherSource.Contains($marker)) {
    throw "AI Worker supervisor is missing required marker: $marker"
  }
}

if ($launcherSource.Contains('update_material_worker.ps1') -or $launcherSource.Contains('git fetch')) {
  throw "AI Worker must not run a second repository updater; Material Worker remains the single update owner."
}

foreach ($marker in @(
  'Teacher AI Worker',
  'TeacherAIWorker',
  'New-ScheduledTaskTrigger -AtStartup',
  '-StartWhenAvailable',
  '-RestartCount 5',
  'Register-ScheduledTask',
  '-LogonType ServiceAccount',
  '-Principal $taskPrincipal',
  '-User $TaskUser',
  '-Password $plainPassword',
  'run_ai_worker_autostart.ps1'
)) {
  if (-not $installerSource.Contains($marker)) {
    throw "AI Worker installer is missing required marker: $marker"
  }
}

foreach ($marker in @(
  'install_material_worker_task.ps1',
  'install_ai_worker_task.ps1',
  'Teacher Material Worker',
  'Teacher AI Worker',
  'Get-Credential',
  'same repository, .venv, and gitignored .local-worker.env'
)) {
  if (-not $bundleSource.Contains($marker)) {
    throw "Combined Teacher Worker installer is missing required marker: $marker"
  }
}

foreach ($marker in @(
  'update_material_worker.ps1',
  'install_teacher_workers.ps1',
  'requirements-ai-worker.txt',
  'MATERIAL_WORKER_ID',
  'AI_VIDEO_STORAGE_BACKEND',
  'AI_PRESENTATION_STORAGE_BACKEND',
  'Gyan.FFmpeg',
  'Ollama.Ollama',
  'OLLAMA_MODEL',
  'SkipDownloads',
  'InstallOptionalTools',
  'Working tree is dirty',
  'Non-interactive task installation requires -ServiceAccount'
)) {
  if (-not $bootstrapSource.Contains($marker)) {
    throw "One-click Worker bootstrap is missing required marker: $marker"
  }
}
foreach ($forbidden in @('git pull', 'git reset', 'git clean', 'git stash')) {
  if ($bootstrapSource.ToLowerInvariant().Contains($forbidden)) {
    throw "One-click Worker bootstrap must not bypass safe release/update boundaries: $forbidden"
  }
}

foreach ($marker in @(
  'AI_WORKER_TRANSPORT=auto',
  'AI_WORKER_TOKEN=',
  'DATABASE_URL=',
  'FREE_ONLY_MODE=true',
  'AI_EXTERNAL_PROCESSING_ENABLED=true',
  'GROQ_API_KEY=REPLACE_WITH_GROQ_API_KEY',
  'AI_TTS_PROVIDER=kokoro',
  'KOKORO_REPO_ID=hexgrad/Kokoro-82M-v1.1-zh',
  'KOKORO_VOICE=zf_xiaoxiao',
  'MATERIAL_WORKER_ID=lab-worker-01',
  'R2_ACCOUNT_ID=REPLACE_WITH_R2_ACCOUNT_ID',
  'R2_ACCESS_KEY_ID=REPLACE_WITH_R2_ACCESS_KEY_ID',
  'R2_SECRET_ACCESS_KEY=REPLACE_WITH_R2_SECRET_ACCESS_KEY',
  'R2_BUCKET_NAME=REPLACE_WITH_R2_BUCKET_NAME'
)) {
  if (-not $envSource.Contains($marker)) {
    throw ".local-worker.env.example is missing required AI Worker marker: $marker"
  }
}

foreach ($marker in @('kokoro>=', 'misaki[zh]', 'numpy>=', 'python-pptx>=')) {
  if (-not $requirementsSource.Contains($marker)) {
    throw "requirements-ai-worker.txt is missing AI Worker dependency marker: $marker"
  }
}
if ($envSource.Contains('OPENAI_API_KEY') -or $requirementsSource.Contains('openai')) {
  throw "FREE_ONLY_MODE local narration must not require OpenAI configuration."
}

$combined = $launcherSource + "`n" + $installerSource + "`n" + $bundleSource + "`n" + $bootstrapSource
foreach ($forbidden in @(
  'gsk_',
  'postgresql://postgres.',
  'GOCSPX-',
  '1//0',
  'REPLACE_WITH_REAL_SECRET'
)) {
  if ($combined.Contains($forbidden)) {
    throw "Worker scripts contain a forbidden secret-like literal: $forbidden"
  }
}

Write-Output "AI Worker same-host Task Scheduler/bootstrap regression passed."
