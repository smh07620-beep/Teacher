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
if "%1"=="remote" goto remote
if "%1"=="status" goto status
if "%1"=="fetch" goto fetch
if "%1"=="cat-file" goto catfile
if "%1"=="verify-tag" goto verifytag
if "%1"=="rev-parse" goto revparse
if "%1"=="merge-base" goto mergebase
if "%1"=="merge" goto merge
exit /b 1

:remote
echo https://github.com/smh07620-beep/Teacher.git
exit /b 0

:status
if "%FAKE_GIT_DIRTY%"=="1" echo M material_worker.py
exit /b 0

:fetch
if "%FAKE_GIT_FETCH_FAIL%"=="1" exit /b 1
exit /b 0

:catfile
if "%FAKE_GIT_LIGHTWEIGHT%"=="1" echo commit
if not "%FAKE_GIT_LIGHTWEIGHT%"=="1" echo tag
exit /b 0

:verifytag
if "%FAKE_GIT_UNSIGNED%"=="1" exit /b 1
exit /b 0

:revparse
if "%2"=="HEAD" goto revparsehead
echo bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
exit /b 0

:revparsehead
if exist "%~dp0..\.fake-merged" echo bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
if not exist "%~dp0..\.fake-merged" echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
exit /b 0

:mergebase
if "%FAKE_GIT_DIVERGED%"=="1" exit /b 1
exit /b 0

:merge
if "%FAKE_GIT_MERGE_FAIL%"=="1" exit /b 1
type nul > "%~dp0..\.fake-merged"
exit /b 0
'@ | Set-Content $fakeGit -Encoding ascii

  $savedPath = $env:Path
  $savedRef = $env:MATERIAL_WORKER_RELEASE_REF
  $savedCommit = $env:MATERIAL_WORKER_RELEASE_COMMIT
  $savedSigned = $env:MATERIAL_WORKER_REQUIRE_SIGNED_TAG
  $env:Path = "$fakeBin;$savedPath"
  $env:MATERIAL_WORKER_REQUIRE_SIGNED_TAG = "true"

  function Clear-Markers {
    Remove-Item (Join-Path $sandbox ".fake-merged") -ErrorAction SilentlyContinue
    foreach ($name in @("FAKE_GIT_DIRTY", "FAKE_GIT_FETCH_FAIL", "FAKE_GIT_LIGHTWEIGHT", "FAKE_GIT_UNSIGNED", "FAKE_GIT_DIVERGED", "FAKE_GIT_MERGE_FAIL")) {
      Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue
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

  Clear-Markers; $env:FAKE_GIT_DIRTY = "1"; Assert-Exit "dirty tree" 24
  Clear-Markers
  $env:FAKE_GIT_UNSIGNED = "1"
  & git verify-tag refs/tags/v6.8.1 *> $null
  if ($LASTEXITCODE -ne 1) { throw "fake unsigned-tag fixture did not reject verify-tag" }
  Assert-Exit "unsigned tag" 27
  Clear-Markers; $env:FAKE_GIT_DIVERGED = "1"; Assert-Exit "diverged history" 30
  Clear-Markers; $env:FAKE_GIT_MERGE_FAIL = "1"; Assert-Exit "merge failure" 31

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
