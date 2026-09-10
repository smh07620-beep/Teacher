@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title SMH Teaching Portal - Google Drive Setup

set "PIP_LOG=%~dp0GOOGLE_DRIVE_SETUP_PIP_LOG.txt"
set "ERR_LOG=%~dp0GOOGLE_DRIVE_SETUP_ERROR.txt"
del /q "%ERR_LOG%" >nul 2>&1

echo ============================================================
echo SMH Teaching Portal V5.3.2 - Google Drive Setup
echo ============================================================
echo.
echo This window will stay open even if setup fails.
echo Project folder: %CD%
echo.

set "PY_CMD="
where py >nul 2>&1
if not errorlevel 1 set "PY_CMD=py"
if defined PY_CMD goto PY_FOUND
where python >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"

:PY_FOUND
if not defined PY_CMD goto NO_PYTHON

echo [1/4] Python launcher found: %PY_CMD%
%PY_CMD% --version
if errorlevel 1 goto NO_PYTHON

if exist ".venv_gdrive\Scripts\python.exe" goto VENV_READY

echo [2/4] Creating Python virtual environment...
%PY_CMD% -m venv .venv_gdrive
if errorlevel 1 goto VENV_FAILED

:VENV_READY
set "VPY=%CD%\.venv_gdrive\Scripts\python.exe"
if not exist "%VPY%" goto VENV_FAILED
echo [2/4] Virtual environment ready.

echo [3/4] Installing Google Drive packages...
echo Installation details will be written to:
echo %PIP_LOG%
"%VPY%" -m pip install --disable-pip-version-check --upgrade pip >"%PIP_LOG%" 2>&1
if errorlevel 1 goto PIP_FAILED
"%VPY%" -m pip install --disable-pip-version-check "google-auth>=2.35,<3.0" "google-auth-oauthlib>=1.2,<2.0" "google-api-python-client>=2.150,<3.0" >>"%PIP_LOG%" 2>&1
if errorlevel 1 goto PIP_FAILED
echo [3/4] Required packages installed.

set "JSON_PATH="
for %%F in (client_secret*.json) do if not defined JSON_PATH set "JSON_PATH=%%~fF"
if defined JSON_PATH goto JSON_FOUND

echo.
echo No client_secret*.json was found in this folder.
echo Copy the Google OAuth Desktop JSON into:
echo %CD%
echo.
set /p "JSON_PATH=Paste the FULL JSON file path here, then press Enter: "
set "JSON_PATH=%JSON_PATH:"=%"

:JSON_FOUND
if not defined JSON_PATH goto JSON_MISSING
if not exist "%JSON_PATH%" goto JSON_MISSING

echo [4/4] OAuth JSON found:
echo %JSON_PATH%
echo.
echo A browser window will open for Google authorization.
echo Sign in with the Google account that will store teaching materials.
echo If Google shows an app warning, only continue if this is your own SMH project.
echo.

"%VPY%" tools\google_drive_setup.py "%JSON_PATH%" --output GOOGLE_DRIVE_RENDER_ENV.txt 2>"%ERR_LOG%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto OAUTH_FAILED

echo.
echo ============================================================
echo SUCCESS
echo ============================================================
echo Render environment variables were written to:
echo %CD%\GOOGLE_DRIVE_RENDER_ENV.txt
echo.
echo IMPORTANT:
echo Do NOT upload GOOGLE_DRIVE_RENDER_ENV.txt or client_secret*.json to GitHub.
echo.
echo You may close this window now.
echo ============================================================
goto KEEP_OPEN

:NO_PYTHON
echo.
echo [ERROR] Python was not found or could not start.
echo Install Python 3.11 or newer from python.org.
echo During installation, enable "Add python.exe to PATH".
echo Then run this setup file again.
goto FAIL

:VENV_FAILED
echo.
echo [ERROR] Python virtual environment could not be created.
echo Try opening Command Prompt in this folder and run:
echo   py -m venv .venv_gdrive
echo.
echo If that fails, send the displayed error to ChatGPT.
goto FAIL

:PIP_FAILED
echo.
echo [ERROR] Required Google Python packages could not be installed.
echo Check internet access, proxy, firewall, or antivirus restrictions.
echo.
echo ---- pip log ----
type "%PIP_LOG%"
echo ---- end pip log ----
goto FAIL

:JSON_MISSING
echo.
echo [ERROR] OAuth client JSON was not found.
echo Put client_secret_....json in the same folder as this setup file.
goto FAIL

:OAUTH_FAILED
echo.
echo [ERROR] Google authorization/setup failed. Exit code: %RC%
echo.
if exist "%ERR_LOG%" (
  echo ---- Google setup error ----
  type "%ERR_LOG%"
  echo ---- end error ----
)
echo.
echo Common causes:
echo  1. Google Drive API is not enabled.
echo  2. Your Google account is not added as an OAuth Test User.
echo  3. OAuth Client type is not Desktop app.
echo  4. Browser authorization was cancelled.
echo  5. Hospital/company firewall blocks localhost OAuth callback.
goto FAIL

:FAIL
echo.
echo ============================================================
echo SETUP DID NOT COMPLETE.
echo This window will remain open so you can screenshot the error.
echo ============================================================

:KEEP_OPEN
echo.
echo Press any key only when you are ready to close this window.
pause >nul
endlocal
exit /b
