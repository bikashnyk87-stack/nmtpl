@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ROLLBACK_PC_MERGE_R11.ps1" %*
pause
