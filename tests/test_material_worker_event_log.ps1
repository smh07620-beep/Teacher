$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$supervisor = Join-Path $repo "run_material_worker_autostart.ps1"
$source = Get-Content -LiteralPath $supervisor -Raw
$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
  $supervisor,
  [ref]$tokens,
  [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) {
  throw "Worker supervisor PowerShell parse failed: $($parseErrors[0].Message)"
}

foreach ($marker in @(
  'function Write-TeacherWorkerEvent',
  '$script:TeacherWorkerEventSource = "TeacherMaterialWorker"',
  '$script:TeacherWorkerEventLog = "Application"',
  'Write-EventLog',
  '-EntryType "Information" -EventId 1000',
  '-EntryType "Information" -EventId 1001',
  '-EntryType "Information" -EventId 1010',
  '-EntryType "Warning" -EventId 2001',
  '-EntryType "Warning" -EventId 2002',
  '-EntryType "Warning" -EventId 2100',
  '-EntryType "Error" -EventId 3001',
  '-EntryType "Error" -EventId 3002',
  '-EntryType "Error" -EventId 3003',
  '-EntryType "Error" -EventId 3004',
  'Event Log access is best-effort'
)) {
  if (-not $source.Contains($marker)) {
    throw "Worker Event Log supervisor is missing required marker: $marker"
  }
}

$eventCalls = @(
  $source -split "`r?`n" | Where-Object { $_ -match 'Write-TeacherWorkerEvent\s+-EntryType' }
)
if ($eventCalls.Count -lt 9) {
  throw "Expected bounded Event Log call sites were not found."
}
foreach ($line in $eventCalls) {
  foreach ($forbidden in @(
    '$env:',
    'MATERIAL_WORKER_TOKEN',
    'MEGA_PASSWORD',
    'GDRIVE_CLIENT_SECRET',
    'GDRIVE_REFRESH_TOKEN',
    'R2_SECRET',
    '$args',
    'Get-Content',
    'GetNetworkCredential'
  )) {
    if ($line.Contains($forbidden)) {
      throw "Event Log call contains forbidden secret-bearing/raw data marker: $forbidden"
    }
  }
}
if ($source.Contains('New-EventLog')) {
  throw "Supervisor must not require administrative Event source creation."
}
if ($source.Contains('pywin32') -or $source.Contains('win32evtlog')) {
  throw "Worker Event Log integration must not depend on pywin32."
}

Write-Output "Material Worker Event Log regression passed."
