[CmdletBinding()]
param(
  [string]$MaterialTaskName = "Teacher Material Worker",
  [string]$AITaskName = "Teacher AI Worker",
  [string]$TaskUser = "",
  [pscredential]$Credential,
  [switch]$ServiceAccount,
  [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$materialInstaller = Join-Path $root "install_material_worker_task.ps1"
$aiInstaller = Join-Path $root "install_ai_worker_task.ps1"

foreach ($path in @($materialInstaller, $aiInstaller)) {
  if (-not (Test-Path $path -PathType Leaf)) {
    throw "Required Worker installer is missing: $path"
  }
}

if ($ServiceAccount) {
  if ($Credential) {
    throw "Do not pass -Credential with -ServiceAccount."
  }
  if (-not $TaskUser) {
    $TaskUser = "SYSTEM"
  }
  & $materialInstaller `
    -TaskName $MaterialTaskName `
    -TaskUser $TaskUser `
    -ServiceAccount `
    -StartNow:$StartNow
  & $aiInstaller `
    -TaskName $AITaskName `
    -TaskUser $TaskUser `
    -ServiceAccount `
    -StartNow:$StartNow
} else {
  if (-not $Credential) {
    if (-not $TaskUser) {
      if ($env:USERDOMAIN -and $env:USERNAME) {
        $TaskUser = "$($env:USERDOMAIN)\$($env:USERNAME)"
      } else {
        $TaskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
      }
    }
    $Credential = Get-Credential `
      -UserName $TaskUser `
      -Message "Enter the Windows password once; it will be passed to both Teacher Worker scheduled tasks."
  }
  if (-not $Credential -or -not $Credential.UserName) {
    throw "A Windows logon credential is required."
  }
  if ($TaskUser -and -not [string]::Equals($TaskUser, $Credential.UserName, [StringComparison]::OrdinalIgnoreCase)) {
    throw "-TaskUser must match the supplied credential username."
  }
  $TaskUser = $Credential.UserName
  & $materialInstaller `
    -TaskName $MaterialTaskName `
    -TaskUser $TaskUser `
    -Credential $Credential `
    -StartNow:$StartNow
  & $aiInstaller `
    -TaskName $AITaskName `
    -TaskUser $TaskUser `
    -Credential $Credential `
    -StartNow:$StartNow
}

Write-Output "Teacher Worker host configuration complete."
Write-Output "Material task: $MaterialTaskName"
Write-Output "AI task: $AITaskName"
Write-Output "Both tasks use the same repository, .venv, and gitignored .local-worker.env."
