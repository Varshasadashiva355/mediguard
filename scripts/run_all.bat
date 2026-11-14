@echo off
echo ========================================================
echo   MediGuard AI - Dual Services Launcher
echo   Backend REST API + Background Inference Worker
echo ========================================================
cd /d "%~dp0\.."

echo Launching Background Inference Worker in new window...
start "MediGuard Background Worker" cmd /k ".\.venv\Scripts\python.exe -m backend.worker.worker --interval 1.0"

echo Launching Flask Backend API on http://127.0.0.1:5000...
.\.venv\Scripts\python.exe -m backend.app
