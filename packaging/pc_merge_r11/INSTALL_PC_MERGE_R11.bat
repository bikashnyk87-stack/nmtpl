@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_PC_MERGE_R11.ps1" %*
if errorlevel 1 (
  echo.
  echo UPDATE NOT COMPLETED. Read PC_MERGE_R11_REPORT.txt in the project folder.
  pause
  exit /b 1
)
echo.
echo NMTPL PC MERGE R11 COMPLETED.
pause
