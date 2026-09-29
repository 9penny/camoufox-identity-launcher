@echo off
setlocal
set "APP_HOME=%~dp0"
if not exist "%APP_HOME%.venv\Scripts\pythonw.exe" (
    echo Run setup.ps1 first.
    pause
    exit /b 1
)
start "" "%APP_HOME%.venv\Scripts\pythonw.exe" "%APP_HOME%run.py"
