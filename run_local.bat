@echo off
setlocal
cd /d "%~dp0"
title AI Surveillance - Weapon Detection Demo

echo =====================================================================
echo        AI SURVEILLANCE - WEAPON DETECTION DEMO LAUNCHER
echo =====================================================================
echo.
echo [1/2] Launching FastAPI Backend on http://localhost:8000 ...
start "Weapon Surveillance Backend (Port 8000)" cmd /k "backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload"

echo [2/2] Launching React Frontend on http://localhost:5173 ...
start "Weapon Surveillance Frontend (Port 5173)" cmd /k "cd frontend && npm run dev"

echo.
echo =====================================================================
echo Both services are starting in separate console windows!
echo - Web UI:  http://localhost:5173
echo - Backend: http://localhost:8000
echo - API:     http://localhost:8000/docs
echo - Mode:    WEAPON DETECTION ONLY (Pistols, Knives, Firearms)
echo =====================================================================
echo.
pause
