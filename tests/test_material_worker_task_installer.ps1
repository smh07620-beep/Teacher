$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $repo "install_material_worker_task.ps1"
$source = Get-Content -LiteralPath $installer -Raw
$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
  $installer,
  [ref]$tokens,
  [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) {
  throw "Task installer PowerShell parse failed: $($parseErrors[0].Message)"
}

foreach ($marker in @(
  "TeacherMaterialWorker",
  "[System.Diagnostics.EventLog]::SourceExists",
  "[System.Diagnostics.EventLog]::LogNameFromSourceName",
  "New-EventLog -LogName `$eventLog -Source `$eventSource",
  "New-ScheduledTaskTrigger -AtStartup",
  "run_material_worker_autostart.ps1",
  "-WorkingDirectory `$root",
  "-RestartCount 5",
  "-RestartInterval (New-TimeSpan -Minutes 1)",
  "-StartWhenAvailable",
  "-LogonType Password",
  "-LogonType ServiceAccount",
  "Normalize-ServiceAccount",
  "Get-Credential",
  "Register-ScheduledTask"
)) {
  if (-not $source.Contains($marker)) {
    throw "Task installer is missing required marker: $marker"
  }
}

foreach ($forbidden in @(
  "-AtLogOn",
  "MATERIAL_WORKER_TOKEN",
  "MEGA_PASSWORD",
  "GDRIVE_CLIENT_SECRET",
  "GDRIVE_REFRESH_TOKEN",
  "R2_SECRET",
  "Remove-EventLog",
  "DeleteEventSource"
)) {
  if ($source.Contains($forbidden)) {
    throw "Task installer contains forbidden value/behavior: $forbidden"
  }
}

Write-Output "Material Worker Task Scheduler installer regression passed."
