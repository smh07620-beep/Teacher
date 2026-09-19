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
  $releaseRef = [Environment]::GetEnvironmentVariable("MATERIAL_WORKER_RELEASE_REF", "Process")
  if (-not $releaseRef) {
    Fail-Update "MATERIAL_WORKER_RELEASE_REF is not configured; automatic main updates are disabled" 21
  }
  $releaseRef = $releaseRef.Trim()
  if ($releaseRef.StartsWith("refs/tags/")) { $releaseRef = $releaseRef.Substring(10) }
  if ($releaseRef -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$') {
    Fail-Update "release ref must be one simple tag name" 21
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

  $tagRef = "refs/tags/$releaseRef"
  & git fetch --force origin ("refs/tags/{0}:refs/tags/{0}" -f $releaseRef)
  if ($LASTEXITCODE -ne 0) { Fail-Update "release tag fetch failed; keeping local version" 25 }

  $tagType = (& git cat-file -t $tagRef).Trim()
  if ($LASTEXITCODE -ne 0 -or $tagType -ne "tag") {
    Fail-Update "release ref must be an annotated tag" 26
  }
  $requireSignedTag = [Environment]::GetEnvironmentVariable("MATERIAL_WORKER_REQUIRE_SIGNED_TAG", "Process")
  if (-not $requireSignedTag) { $requireSignedTag = "true" }
  if ($requireSignedTag.Trim().ToLowerInvariant() -in @("1", "true", "yes", "on")) {
    & git verify-tag $tagRef *> $null
    if ($LASTEXITCODE -ne 0) { Fail-Update "release tag signature verification failed" 27 }
  }

  $previous = (& git rev-parse HEAD).Trim()
  $remote = (& git rev-parse ("{0}^{{commit}}" -f $tagRef)).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $previous -or -not $remote) {
    Fail-Update "could not resolve local HEAD or release tag" 28
  }
  $expectedCommit = [Environment]::GetEnvironmentVariable("MATERIAL_WORKER_RELEASE_COMMIT", "Process")
  if ($expectedCommit) {
    $expectedCommit = $expectedCommit.Trim().ToLowerInvariant()
    if ($expectedCommit -notmatch '^[a-f0-9]{7,40}$' -or -not $remote.ToLowerInvariant().StartsWith($expectedCommit)) {
      Fail-Update "release tag does not match the approved commit" 29
    }
  }
  if ($previous -eq $remote) {
    Write-Output "Already on approved release $releaseRef ($previous)"
    exit 0
  }
  & git merge-base --is-ancestor HEAD $remote
  if ($LASTEXITCODE -ne 0) {
    Fail-Update "approved release is not a fast-forward from local HEAD" 30
  }

  # This is intentionally the only command that changes the checkout. It
  # advances the current branch only to the verified, explicitly approved tag.
  & git merge --ff-only $remote
  if ($LASTEXITCODE -ne 0) { Fail-Update "fast-forward release update failed; keeping local version" 31 }
  $current = (& git rev-parse HEAD).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $current) { Fail-Update "could not resolve updated HEAD" 32 }
  Write-Output "Approved Worker release installed"
  Write-Output "Release: $releaseRef"
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
