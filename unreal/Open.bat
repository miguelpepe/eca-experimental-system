@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\unreal.ps1" -Action Open %*
exit /b %ERRORLEVEL%
