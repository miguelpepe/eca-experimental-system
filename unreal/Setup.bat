@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\unreal.ps1" -Action Setup %*
set "ECA_SETUP_EXIT=%ERRORLEVEL%"
if not "%ECA_SETUP_EXIT%"=="0" pause
exit /b %ECA_SETUP_EXIT%
