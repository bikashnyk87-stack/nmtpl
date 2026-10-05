@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_PC_SITE_SOFTWARE.ps1" %*
if errorlevel 1 (
  echo.
  echo INSTALLATION FAILED. The automatic backup is still available.
  pause
  exit /b 1
)
echo.
echo INSTALLATION COMPLETED.
pause
