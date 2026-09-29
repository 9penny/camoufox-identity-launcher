@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
    echo Setup failed with exit code %RESULT%.
) else (
    echo Setup finished successfully.
)
pause
exit /b %RESULT%
