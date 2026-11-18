@echo off
setlocal
cd /d "%~dp0"
title AI Surveillance - Weapon Detection Launcher

echo =====================================================================
echo        AI SURVEILLANCE - WEAPON DETECTION DEMO LAUNCHER
echo =====================================================================
echo.
echo Starting backend server on http://localhost:8000 ...
start "Weapon Surveillance Backend (Port 8000)" cmd /k "backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000"

echo Starting frontend web app on http://localhost:5173 ...
start "Weapon Surveillance Frontend (Port 5173)" cmd /k "cd frontend && npm run dev"

timeout /t 3 /nobreak >nul
echo Opening web dashboard in default browser...
start http://localhost:5173/

echo.
echo =====================================================================
echo Services active:
echo - Web Dashboard: http://localhost:5173/
echo - Backend API:   http://localhost:8000/
echo - Active Model:  models/weapon_model.pt
echo =====================================================================
echo.
pause
