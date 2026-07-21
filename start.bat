@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title PIC Lite
echo ========================================
echo   PIC Lite - local start (no Docker)
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python is not on PATH.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo ERROR: failed to create .venv
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" scripts\launch_local.py
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
  echo Startup reported a problem. See messages above.
) else (
  echo App is running. Use the browser window that opened.
)
pause
exit /b %EXITCODE%
