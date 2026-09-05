@echo off
setlocal EnableExtensions

rem ================================================================
rem  Swing Trading Picks - one-command launcher (backend + frontend)
rem
rem  Run it either way:
rem     - double-click start.cmd in Explorer
rem     - from PowerShell/cmd:  .\start.cmd
rem
rem  It first kills any stale servers from a previous run (the usual
rem  cause of 404s), then starts fresh and opens the app.
rem ================================================================

set "ROOT=%~dp0"
set "NODE=%ROOT%.tools\node-v20.20.2-win-x64"

if not exist "%ROOT%backend\app\main.py" (
    echo [ERROR] Backend not found at: %ROOT%backend
    pause
    exit /b 1
)

rem ---- 1) Free up ports 3000/8000 from any stale previous run --------------
echo Stopping any previous servers on ports 3000 and 8000 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
timeout /t 2 /nobreak >nul

rem ---- 2) Use the bundled portable Node (adds npm to PATH) ------------------
if exist "%NODE%\npm.cmd" set "PATH=%NODE%;%PATH%"

rem ---- 3) Start backend + frontend in their own windows ---------------------
echo [1/2] Starting backend  -> http://127.0.0.1:8000
start "SwingTrading - Backend" /D "%ROOT%backend" cmd /k "python -m uvicorn app.main:app --port 8000 --reload"

echo [2/2] Starting frontend -> http://localhost:3000
start "SwingTrading - Frontend" /D "%ROOT%frontend" cmd /k "npm run dev"

rem ---- 4) Wait until the frontend responds, then open the browser -----------
echo Waiting for the app to be ready ...
powershell -NoProfile -Command "for ($i=0; $i -lt 90; $i++) { try { $r = Invoke-WebRequest -UseBasicParsing http://localhost:3000 -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { break } } catch {}; Start-Sleep -Seconds 2 }"
start "" http://localhost:3000

echo.
echo   Backend docs : http://127.0.0.1:8000/docs
echo   App          : http://localhost:3000
echo   Login        : admin / changeme
echo.
echo   First boot seeds demo data (~15s). If you linked Alpaca, click
echo   "Refresh data" in the app to pull real prices.
echo   To stop the app, run stop.cmd (or press Ctrl+C in each window).
echo.
endlocal
