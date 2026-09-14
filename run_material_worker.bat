@echo off
setlocal
cd /d "%~dp0"
if not exist .local-worker.env goto run
for /f "usebackq tokens=1,* delims==" %%A in (".local-worker.env") do if not "%%A"=="" set "%%A=%%B"
:run
if "%TEACHER_BASE_URL%"=="" echo TEACHER_BASE_URL is required & exit /b 2
if "%MATERIAL_WORKER_TOKEN%"=="" echo MATERIAL_WORKER_TOKEN is required & exit /b 2
python -u material_worker.py
