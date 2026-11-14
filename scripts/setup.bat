@echo off
echo ========================================================
echo   MediGuard AI - Automated Environment Setup
echo ========================================================
cd /d "%~dp0\.."

if not exist .venv (
    echo Creating Python virtual environment in .venv...
    python -m venv .venv
)

echo Upgrading pip and installing requirements...
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if not exist .env (
    echo Copying .env.example to .env...
    copy .env.example .env
)

echo Setup completed successfully!
echo Run 'scripts\seed.bat' to populate synthetic data.
