$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$sandbox = Join-Path ([IO.Path]::GetTempPath()) ("teacher-worker-update-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $sandbox | Out-Null
try {
  Copy-Item (Join-Path $repo "update_material_worker.ps1") (Join-Path $sandbox "update_material_worker.ps1")
  New-Item -ItemType Directory -Path (Join-Path $sandbox ".git") | Out-Null
  $fakeBin = Join-Path $sandbox "fake-bin"; New-Item -ItemType Directory -Path $fakeBin | Out-Null
  $fakeGit = Join-Path $fakeBin "git.cmd"
  @'
@echo off
if "%1"=="branch" (
  if exist "%~dp0..\.fake-branch-feature" (echo feature) else (echo main)
  exit /b 0
)
if "%1"=="remote" (
  echo https://github.com/smh07620-beep/Teacher.git
  exit /b 0
)
if "%1"=="status" (
  if exist "%~dp0..\.fake-dirty" echo M material_worker.py
  exit /b 0
)
if "%1"=="fetch" (
  if exist "%~dp0..\.fake-fetch-fail" exit /b 1
  exit /b 0
)
if "%1"=="rev-parse" (
  if "%2"=="HEAD" (
    if exist "%~dp0..\.fake-pulled" (echo newsha) else (echo oldsha)
    exit /b 0
  )
  if "%2"=="origin/main" echo newsha
  exit /b 0
)
if "%1"=="merge-base" (
  if exist "%~dp0..\.fake-diverged" exit /b 1
  exit /b 0
)
if "%1"=="pull" (
  if exist "%~dp0..\.fake-pull-fail" exit /b 1
  type nul > "%~dp0..\.fake-pulled"
  exit /b 0
)
exit /b 1
'@ | Set-Content $fakeGit -Encoding ascii
  $savedPath = $env:Path; $env:Path = "$fakeBin;$savedPath"
  function Assert-Exit([string]$Name, [int]$Expected) {
    Remove-Item (Join-Path $sandbox ".fake-pulled") -ErrorAction SilentlyContinue
    & (Join-Path $sandbox "update_material_worker.ps1") 2>$null
    if ($LASTEXITCODE -ne $Expected) { throw "$Name expected exit $Expected, got $LASTEXITCODE" }
  }
  Assert-Exit "clean behind origin" 0
  if (-not (Test-Path (Join-Path $sandbox ".fake-pulled"))) { throw "clean update did not use fast-forward pull" }
  New-Item (Join-Path $sandbox ".fake-dirty") | Out-Null; Assert-Exit "dirty tree" 24; Remove-Item (Join-Path $sandbox ".fake-dirty")
  $normalFakeGit = Get-Content $fakeGit -Raw
  @'
@echo off
if "%1"=="branch" (echo main & exit /b 0)
if "%1"=="remote" (echo https://github.com/smh07620-beep/Teacher.git & exit /b 0)
if "%1"=="status" exit /b 0
if "%1"=="fetch" exit /b 0
if "%1"=="rev-parse" (
  if "%2"=="HEAD" echo oldsha
  if "%2"=="origin/main" echo newsha
  exit /b 0
)
if "%1"=="merge-base" exit /b 1
exit /b 1
'@ | Set-Content $fakeGit -Encoding ascii
  Assert-Exit "diverged history" 27
  $normalFakeGit | Set-Content $fakeGit -Encoding ascii
  New-Item (Join-Path $sandbox ".fake-branch-feature") | Out-Null; Assert-Exit "wrong branch" 21; Remove-Item (Join-Path $sandbox ".fake-branch-feature")
  @'
@echo off
if "%1"=="branch" (echo main & exit /b 0)
if "%1"=="remote" (echo https://github.com/smh07620-beep/Teacher.git & exit /b 0)
if "%1"=="status" exit /b 0
if "%1"=="fetch" exit /b 1
exit /b 1
'@ | Set-Content $fakeGit -Encoding ascii
  Assert-Exit "fetch failure" 25
  @'
@echo off
if "%1"=="branch" (echo main & exit /b 0)
if "%1"=="remote" (echo https://github.com/smh07620-beep/Teacher.git & exit /b 0)
if "%1"=="status" exit /b 0
if "%1"=="fetch" exit /b 0
if "%1"=="rev-parse" (
  if "%2"=="HEAD" echo oldsha
  if "%2"=="origin/main" echo newsha
  exit /b 0
)
if "%1"=="merge-base" exit /b 0
if "%1"=="pull" exit /b 1
exit /b 1
'@ | Set-Content $fakeGit -Encoding ascii
  Assert-Exit "pull failure" 28
  Write-Output "PowerShell safe-update regression tests passed (6 scenarios)."
} finally {
  if ($savedPath) { $env:Path = $savedPath }
  Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}
