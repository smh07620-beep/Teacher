$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repo "run_ai_worker_autostart.ps1"
$installer = Join-Path $repo "install_ai_worker_task.ps1"
$bundle = Join-Path $repo "install_teacher_workers.ps1"
$envTemplate = Join-Path $repo ".local-worker.env.example"

foreach ($path in @($launcher, $installer, $bundle)) {
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
$envSource = Get-Content -LiteralPath $envTemplate -Raw

foreach ($marker in @(
  'TeacherAIWorker',
  'ai_question_worker.py',
  'DATABASE_URL',
  'GROQ_API_KEY',
  'OPENAI_API_KEY',
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
  'DATABASE_URL=REPLACE_WITH_PRODUCTION_DATABASE_URL',
  'AI_EXTERNAL_PROCESSING_ENABLED=true',
  'GROQ_API_KEY=REPLACE_WITH_GROQ_API_KEY',
  'OPENAI_API_KEY=REPLACE_WITH_OPENAI_API_KEY',
  'R2_ACCOUNT_ID=REPLACE_WITH_R2_ACCOUNT_ID',
  'R2_ACCESS_KEY_ID=REPLACE_WITH_R2_ACCESS_KEY_ID',
  'R2_SECRET_ACCESS_KEY=REPLACE_WITH_R2_SECRET_ACCESS_KEY',
  'R2_BUCKET_NAME=REPLACE_WITH_R2_BUCKET_NAME'
)) {
  if (-not $envSource.Contains($marker)) {
    throw ".local-worker.env.example is missing required AI Worker marker: $marker"
  }
}

$combined = $launcherSource + "`n" + $installerSource + "`n" + $bundleSource
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

Write-Output "AI Worker same-host Task Scheduler regression passed."
