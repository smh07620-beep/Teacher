[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$TaskName = "Teacher Material Worker",
  [string]$TaskUser = "",
  [pscredential]$Credential,
  [switch]$ServiceAccount,
  [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$launcher = Join-Path $root "run_material_worker_autostart.ps1"
$envFile = Join-Path $root ".local-worker.env"
$python = Join-Path $root ".venv\Scripts\python.exe"

function Assert-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this installer from an elevated Windows PowerShell session."
  }
}

function Current-TaskUser {
  if ($env:USERDOMAIN -and $env:USERNAME) {
    return "$($env:USERDOMAIN)\$($env:USERNAME)"
  }
  return [Security.Principal.WindowsIdentity]::GetCurrent().Name
}

function Normalize-ServiceAccount([string]$Value) {
  $normalized = ($Value -replace '\s+', '').ToUpperInvariant()
  switch ($normalized) {
    "SYSTEM" { return "NT AUTHORITY\SYSTEM" }
    "NTAUTHORITY\SYSTEM" { return "NT AUTHORITY\SYSTEM" }
    "LOCALSERVICE" { return "NT AUTHORITY\LOCAL SERVICE" }
    "NTAUTHORITY\LOCALSERVICE" { return "NT AUTHORITY\LOCAL SERVICE" }
    "NETWORKSERVICE" { return "NT AUTHORITY\NETWORK SERVICE" }
    "NTAUTHORITY\NETWORKSERVICE" { return "NT AUTHORITY\NETWORK SERVICE" }
    default { throw "-ServiceAccount supports only SYSTEM, LOCAL SERVICE, or NETWORK SERVICE. Use password logon for ordinary/domain accounts." }
  }
}

function Ensure-TeacherWorkerEventSource {
  $eventSource = "TeacherMaterialWorker"
  $eventLog = "Application"
  $exists = [System.Diagnostics.EventLog]::SourceExists($eventSource)
  if ($exists) {
    $registeredLog = [System.Diagnostics.EventLog]::LogNameFromSourceName($eventSource, ".")
    if ($registeredLog -and -not [string]::Equals($registeredLog, $eventLog, [StringComparison]::OrdinalIgnoreCase)) {
      throw "Windows Event source TeacherMaterialWorker already belongs to another log; refusing destructive reconfiguration."
    }
    return
  }
  if ($PSCmdlet.ShouldProcess($eventSource, "Create Windows Application Event source")) {
    New-EventLog -LogName $eventLog -Source $eventSource
  }
}

Assert-Administrator
Ensure-TeacherWorkerEventSource
if (-not (Test-Path $launcher -PathType Leaf)) {
  throw "Canonical Worker launcher is missing: $launcher"
}
if (-not (Test-Path $envFile -PathType Leaf)) {
  throw "Create the gitignored .local-worker.env before installing the scheduled task."
}
if (-not (Test-Path $python -PathType Leaf)) {
  throw "Create .venv\Scripts\python.exe before installing the scheduled task."
}

$powershell = (Get-Command powershell.exe -CommandType Application -ErrorAction Stop).Source
$arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $launcher + '"'
$action = New-ScheduledTaskAction `
  -Execute $powershell `
  -Argument $arguments `
  -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -RestartCount 5 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -MultipleInstances IgnoreNew `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries

$registered = $null
if ($ServiceAccount) {
  if ($Credential) {
    throw "Do not pass -Credential with -ServiceAccount."
  }
  if (-not $TaskUser) {
    throw "-ServiceAccount requires -TaskUser: SYSTEM, LOCAL SERVICE, or NETWORK SERVICE."
  }
  $TaskUser = Normalize-ServiceAccount $TaskUser
  $taskPrincipal = New-ScheduledTaskPrincipal `
    -UserId $TaskUser `
    -LogonType ServiceAccount `
    -RunLevel Highest
  if ($PSCmdlet.ShouldProcess($TaskName, "Register At-startup material Worker task for service account $TaskUser")) {
    $registered = Register-ScheduledTask `
      -TaskName $TaskName `
      -Action $action `
      -Trigger $trigger `
      -Settings $settings `
      -Principal $taskPrincipal `
      -Description "Teacher local material Worker; canonical startup supervisor." `
      -Force
  }
} else {
  if (-not $TaskUser) {
    $TaskUser = if ($Credential) { $Credential.UserName } else { Current-TaskUser }
  }
  if (-not $Credential) {
    $Credential = Get-Credential `
      -UserName $TaskUser `
      -Message "Enter the Windows password used by Task Scheduler to run the Teacher material Worker when nobody is logged on."
  }
  if (-not $Credential -or -not $Credential.UserName) {
    throw "A Windows logon credential is required."
  }
  if ($TaskUser -and -not [string]::Equals($TaskUser, $Credential.UserName, [StringComparison]::OrdinalIgnoreCase)) {
    throw "-TaskUser must match the supplied credential username."
  }
  $TaskUser = $Credential.UserName
  $plainPassword = $Credential.GetNetworkCredential().Password
  try {
    if ($PSCmdlet.ShouldProcess($TaskName, "Register At-startup material Worker task for password logon $TaskUser")) {
      $registered = Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Teacher local material Worker; canonical startup supervisor." `
        -User $TaskUser `
        -Password $plainPassword `
        -RunLevel Highest `
        -Force
    }
  } finally {
    $plainPassword = $null
  }
}

if ($registered) {
  Write-Output "Registered scheduled task: $TaskName"
  Write-Output "Event source: TeacherMaterialWorker (Application)"
  Write-Output "Trigger: At startup"
  Write-Output "Launcher: $launcher"
  Write-Output "Task user: $TaskUser"
  Write-Output "Restart policy: 5 attempts, 1 minute interval"
  if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Output "Task started."
  }
}
