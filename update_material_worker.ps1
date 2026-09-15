[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
Set-Location $root

function Fail-Update([string]$Message, [int]$Code) {
  [Console]::Error.WriteLine("Safe worker update refused: $Message")
  exit $Code
}

try {
  if (-not (Test-Path (Join-Path $root ".git") -PathType Container)) {
    Fail-Update "this script must be run from the Teacher repository root" 20
  }
  $branch = (& git branch --show-current).Trim()
  if ($LASTEXITCODE -ne 0 -or $branch -ne "main") {
    Fail-Update "current branch must be main" 21
  }
  $originUrl = (& git remote get-url origin).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $originUrl) {
    Fail-Update "required remote origin is missing" 22
  }
  # Ignored local configuration (including .local-worker.env) is deliberately
  # excluded by Git; no configuration file is read, moved, or printed here.
  $dirty = & git status --porcelain --untracked-files=all
  if ($LASTEXITCODE -ne 0) { Fail-Update "could not inspect working tree" 23 }
  if ($dirty) { Fail-Update "working tree is dirty; no files were changed" 24 }

  & git fetch origin main
  if ($LASTEXITCODE -ne 0) { Fail-Update "git fetch origin main failed; keeping local version" 25 }
  $previous = (& git rev-parse HEAD).Trim()
  $remote = (& git rev-parse origin/main).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $previous -or -not $remote) {
    Fail-Update "could not resolve local HEAD or origin/main" 26
  }
  if ($previous -eq $remote) {
    Write-Output "Already up to date ($previous)"
    exit 0
  }
  & git merge-base --is-ancestor HEAD origin/main
  if ($LASTEXITCODE -ne 0) {
    Fail-Update "local HEAD has diverged from origin/main; fast-forward only" 27
  }

  # This is intentionally the only command that changes the checkout.  It
  # cannot rewrite history, switch branches, reset, stash, or alter remotes.
  & git pull --ff-only origin main
  if ($LASTEXITCODE -ne 0) { Fail-Update "fast-forward update failed; keeping local version" 28 }
  $current = (& git rev-parse HEAD).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $current) { Fail-Update "could not resolve updated HEAD" 29 }
  Write-Output "Safe worker update complete"
  Write-Output "Previous SHA: $previous"
  Write-Output "New SHA: $current"
  Write-Output ("Timestamp: " + [DateTime]::UtcNow.ToString("o"))
  exit 0
} catch {
  # Do not echo command environment or exception details, which could contain
  # local paths or configuration values.  The checkout is left untouched.
  [Console]::Error.WriteLine("Safe worker update failed; keeping local version.")
  exit 30
}
