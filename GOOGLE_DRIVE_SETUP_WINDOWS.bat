@echo off
cd /d "%~dp0"
start "SMH Google Drive Setup" cmd.exe /d /k call "%~dp0GOOGLE_DRIVE_SETUP_CORE.cmd"
exit /b
