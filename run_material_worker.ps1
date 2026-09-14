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

if (-not $env:TEACHER_BASE_URL -or -not $env:MATERIAL_WORKER_TOKEN) {
  throw "Set TEACHER_BASE_URL and MATERIAL_WORKER_TOKEN in .local-worker.env or this session."
}

python -u material_worker.py
