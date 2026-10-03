@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "PROJECT=%CD%"
set "PYTHON=%PROJECT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python.exe"

if not exist "%PROJECT%\logs\render_sync" mkdir "%PROJECT%\logs\render_sync" >nul 2>&1

echo ==== %date% %time% ====>>"%PROJECT%\logs\render_sync\scheduler.log"
"%PYTHON%" "%PROJECT%\scripts\pull_render_sync.py" >>"%PROJECT%\logs\render_sync\scheduler.log" 2>&1
set "RC=%ERRORLEVEL%"
echo ExitCode=%RC%>>"%PROJECT%\logs\render_sync\scheduler.log"
exit /b %RC%
