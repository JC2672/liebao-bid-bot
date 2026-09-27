@echo off
REM Launches backend (FastAPI) and frontend (Vite) each in their own window.
REM Double-click this file, or run it from a terminal. Close either window to stop that half.

set ROOT=%~dp0

REM Bind/browse via 127.0.0.1, not "localhost" - some VPN clients override DNS
REM so "localhost" no longer resolves to loopback, which looks exactly like
REM "the page won't load" even though both servers started fine.
start "liebao-bid-bot backend" cmd /k "cd /d "%ROOT%backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
start "liebao-bid-bot frontend" cmd /k "cd /d "%ROOT%web" && npm run dev -- --host 127.0.0.1"

timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:5173"
