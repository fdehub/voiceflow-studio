@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "%~dp0runtime\python.exe" (
    set "PY=%~dp0runtime\python.exe"
) else (
    set "PY=python"
)

start "" "%PY%" desktop_app.py
exit /b 0
