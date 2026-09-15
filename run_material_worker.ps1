# Compatibility entrypoint.  Task Scheduler should use the canonical
# run_material_worker_autostart.ps1 supervisor directly.  That supervisor
# adds the official MEGAcmd ProgramFiles directory to $env:Path only for this
# process, without persistent machine changes.
& (Join-Path $PSScriptRoot "run_material_worker_autostart.ps1")
exit $LASTEXITCODE
