@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_material_worker_autostart.ps1"
exit /b %ERRORLEVEL%
