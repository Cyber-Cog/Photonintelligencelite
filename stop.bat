@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Stopping PIC Lite...

if exist ".tools\pids.txt" (
  for /f %%P in (.tools\pids.txt) do taskkill /PID %%P /T /F >nul 2>&1
  del /f /q .tools\pids.txt >nul 2>&1
)

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do taskkill /PID %%P /F /T >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173 " ^| findstr LISTENING') do taskkill /PID %%P /F /T >nul 2>&1

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\start_local_postgres.py stop
)

echo Done.
pause
