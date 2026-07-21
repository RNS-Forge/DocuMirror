@echo off
cd /d "%~dp0node_server"

echo [1/2] Installing dependencies...
call npm install
if %errorlevel% neq 0 (
    echo ERROR: npm install failed. Make sure Node.js 18+ is installed.
    pause
    exit /b 1
)

echo.
echo [2/2] Starting DocuMirror server on http://localhost:3000
echo       Press Ctrl+C to stop.
echo.
call npm run dev
pause
