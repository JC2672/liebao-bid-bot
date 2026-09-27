@echo off
REM Launches backend (FastAPI) and frontend (Vite) each in their own window.
REM Double-click this file, or run it from a terminal. Close either window to stop that half.

set ROOT=%~dp0

start "liebao-bid-bot backend" cmd /k "cd /d "%ROOT%backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload"
start "liebao-bid-bot frontend" cmd /k "cd /d "%ROOT%web" && npm run dev"

timeout /t 3 /nobreak >nul
start "" "http://localhost:5173"
