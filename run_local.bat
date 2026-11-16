@echo off
echo ========================================================
echo Starting AI Surveillance Backend and Frontend
echo ========================================================

echo [1/2] Launching Backend on http://localhost:8000 ...
start "IDS Backend (Port 8000)" cmd /k "backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload"

echo [2/2] Launching Frontend on http://localhost:5173 ...
start "IDS Frontend (Port 5173)" cmd /k "cd frontend && npm run dev"

echo ========================================================
echo Services started!
echo Frontend: http://localhost:5173
echo Backend:  http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo ========================================================
pause
