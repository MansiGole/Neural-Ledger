@echo off
setlocal

set PORT=8000

:: Check if port is already in use
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% == 0 (
    echo ERROR: Port %PORT% is already in use. Please free the port and try again.
    exit /b 1
)

:: Start the Webhook Server in a new terminal window
echo Starting Webhook Server on port %PORT%...
start cmd /k "uvicorn main:app --reload --port %PORT%"

echo Webhook Server started. Open http://localhost:%PORT% in your browser.
endlocal
