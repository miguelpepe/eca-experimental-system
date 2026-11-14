@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" -Action Setup %*
if errorlevel 1 (
  pause
  exit /b 1
)
pause
