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
  "-LogonType ServiceAccount",
  "Normalize-ServiceAccount",
  "Get-Credential",
  "Register-ScheduledTask",
  "-Principal `$taskPrincipal",
  "-User `$TaskUser",
  "-Password `$plainPassword",
  "-RunLevel Highest"
)) {
  if (-not $source.Contains($marker)) {
    throw "Task installer is missing required marker: $marker"
  }
}

foreach ($forbidden in @(
  "-AtLogOn",
  "-InputObject `$task",
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

$serviceStart = $source.IndexOf('if ($ServiceAccount) {')
$passwordStart = $source.IndexOf('} else {', $serviceStart)
$footerStart = $source.IndexOf('if ($registered) {', $passwordStart)
if ($serviceStart -lt 0 -or $passwordStart -lt 0 -or $footerStart -lt 0) {
  throw "Could not locate the service/password registration branches."
}
$serviceBlock = $source.Substring($serviceStart, $passwordStart - $serviceStart)
$passwordBlock = $source.Substring($passwordStart, $footerStart - $passwordStart)

if (-not $serviceBlock.Contains('-Principal $taskPrincipal')) {
  throw "Service-account registration must use the -Principal parameter set."
}
if ($serviceBlock.Contains('-Password $plainPassword') -or $serviceBlock.Contains('-User $TaskUser')) {
  throw "Service-account registration must not mix -Principal with -User/-Password."
}
if (-not $passwordBlock.Contains('-User $TaskUser') -or -not $passwordBlock.Contains('-Password $plainPassword')) {
  throw "Password registration must use the -User/-Password parameter set."
}
if ($passwordBlock.Contains('-Principal $taskPrincipal') -or $passwordBlock.Contains('-InputObject $task')) {
  throw "Password registration must not mix -User/-Password with -Principal/-InputObject."
}

Write-Output "Material Worker Task Scheduler installer regression passed."
