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
if "%1"=="cat-file" (
  if exist "%~dp0..\.fake-lightweight" (echo commit) else (echo tag)
  exit /b 0
)
if "%1"=="verify-tag" (
  if exist "%~dp0..\.fake-unsigned" exit /b 1
  exit /b 0
)
if "%1"=="rev-parse" (
  if "%2"=="HEAD" (
    if exist "%~dp0..\.fake-merged" (echo bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb) else (echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)
    exit /b 0
  )
  echo bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
  exit /b 0
)
if "%1"=="merge-base" (
  if exist "%~dp0..\.fake-diverged" exit /b 1
  exit /b 0
)
if "%1"=="merge" (
  if exist "%~dp0..\.fake-merge-fail" exit /b 1
  type nul > "%~dp0..\.fake-merged"
  exit /b 0
)
exit /b 1
'@ | Set-Content $fakeGit -Encoding ascii

  $savedPath = $env:Path
  $savedRef = $env:MATERIAL_WORKER_RELEASE_REF
  $savedCommit = $env:MATERIAL_WORKER_RELEASE_COMMIT
  $savedSigned = $env:MATERIAL_WORKER_REQUIRE_SIGNED_TAG
  $env:Path = "$fakeBin;$savedPath"
  $env:MATERIAL_WORKER_REQUIRE_SIGNED_TAG = "true"

  function Clear-Markers {
    foreach ($name in @(".fake-merged", ".fake-dirty", ".fake-fetch-fail", ".fake-lightweight", ".fake-unsigned", ".fake-diverged", ".fake-merge-fail")) {
      Remove-Item (Join-Path $sandbox $name) -ErrorAction SilentlyContinue
    }
  }
  function Assert-Exit([string]$Name, [int]$Expected) {
    & (Join-Path $sandbox "update_material_worker.ps1") 2>$null
    if ($LASTEXITCODE -ne $Expected) { throw "$Name expected exit $Expected, got $LASTEXITCODE" }
  }

  Clear-Markers
  Remove-Item Env:MATERIAL_WORKER_RELEASE_REF -ErrorAction SilentlyContinue
  Assert-Exit "missing approved release" 21

  $env:MATERIAL_WORKER_RELEASE_REF = "v6.8.1"
  Clear-Markers; Assert-Exit "clean approved release" 0
  if (-not (Test-Path (Join-Path $sandbox ".fake-merged"))) { throw "approved release did not use fast-forward merge" }

  Clear-Markers; New-Item (Join-Path $sandbox ".fake-dirty") | Out-Null; Assert-Exit "dirty tree" 24
  Clear-Markers; New-Item (Join-Path $sandbox ".fake-unsigned") | Out-Null; Assert-Exit "unsigned tag" 27
  Clear-Markers; New-Item (Join-Path $sandbox ".fake-diverged") | Out-Null; Assert-Exit "diverged history" 30
  Clear-Markers; New-Item (Join-Path $sandbox ".fake-merge-fail") | Out-Null; Assert-Exit "merge failure" 31

  Clear-Markers
  $env:MATERIAL_WORKER_RELEASE_COMMIT = "ccccccc"
  Assert-Exit "commit pin mismatch" 29

  Write-Output "PowerShell pinned-release worker update regression tests passed (7 scenarios)."
} finally {
  if ($savedPath) { $env:Path = $savedPath }
  if ($null -eq $savedRef) { Remove-Item Env:MATERIAL_WORKER_RELEASE_REF -ErrorAction SilentlyContinue } else { $env:MATERIAL_WORKER_RELEASE_REF = $savedRef }
  if ($null -eq $savedCommit) { Remove-Item Env:MATERIAL_WORKER_RELEASE_COMMIT -ErrorAction SilentlyContinue } else { $env:MATERIAL_WORKER_RELEASE_COMMIT = $savedCommit }
  if ($null -eq $savedSigned) { Remove-Item Env:MATERIAL_WORKER_REQUIRE_SIGNED_TAG -ErrorAction SilentlyContinue } else { $env:MATERIAL_WORKER_REQUIRE_SIGNED_TAG = $savedSigned }
  Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}
