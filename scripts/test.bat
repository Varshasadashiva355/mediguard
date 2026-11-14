@echo off
echo ========================================================
echo   MediGuard AI - Automated Clinical Verification Suite
echo ========================================================
cd /d "%~dp0\.."

echo [1/3] Running RLS & RBAC Verification Suite...
.\.venv\Scripts\python.exe -m scripts.rls_verify
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] RLS Verification failed!
    exit /b %ERRORLEVEL%
)

echo.
echo [2/3] Running Unit & Integration Pytest Suite...
.\.venv\Scripts\python.exe -m pytest tests/ -v
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Pytest suite failed!
    exit /b %ERRORLEVEL%
)

echo.
echo [3/3] Running End-to-End Clinical Lifecycle Smoke Test...
.\.venv\Scripts\python.exe -m pytest tests/test_e2e_smoke.py -v
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] End-to-end smoke test failed!
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================
echo   ALL CLINICAL TEST SUITES PASSED CLEANLY!
echo ========================================================
