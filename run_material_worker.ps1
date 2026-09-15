$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (Test-Path ".local-worker.env") {
  Get-Content ".local-worker.env" | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)\s*$') {
      [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
  }
}

# MEGAcmd on Windows installs official .bat wrappers here. Keep this change
# process-local so it neither alters the system PATH nor permits a shell lookup.
$megaDirectories = @(
  $env:MEGACMD_PATH,
  $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles "MEGAcmd" }),
  $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} "MEGAcmd" })
) | Where-Object { $_ -and (Test-Path $_ -PathType Container) }
$pathParts = @($env:Path -split [regex]::Escape([IO.Path]::PathSeparator) | Where-Object { $_ })
foreach ($directory in $megaDirectories) {
  if ($pathParts -notcontains $directory) {
    $pathParts = @($directory) + $pathParts
  }
}
$env:Path = $pathParts -join [IO.Path]::PathSeparator

if (-not $env:TEACHER_BASE_URL -or -not $env:MATERIAL_WORKER_TOKEN) {
  throw "Set TEACHER_BASE_URL and MATERIAL_WORKER_TOKEN in .local-worker.env or this session."
}

python -u material_worker.py
