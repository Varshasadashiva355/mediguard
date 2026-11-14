@echo off
echo ========================================================
echo   MediGuard AI - Synthetic Cardiology Data Seeder
echo ========================================================
cd /d "%~dp0\.."
.\.venv\Scripts\python.exe -m backend.db.cli seed
echo Seeding complete! Run 'scripts\run_all.bat' to launch services.
