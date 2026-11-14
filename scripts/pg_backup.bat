@echo off
REM ==============================================================================
REM MediGuard AI – Daily PostgreSQL Backup Script (Windows)
REM Performs an automated compressed backup with pg_dump and retains daily archives.
REM ==============================================================================

setlocal enabledelayedexpansion

REM Configuration defaults (can be overridden via environment)
if "%PGHOST%"=="" set PGHOST=localhost
if "%PGPORT%"=="" set PGPORT=5432
if "%PGUSER%"=="" set PGUSER=mediguard
if "%PGDATABASE%"=="" set PGDATABASE=mediguard
if "%BACKUP_DIR%"=="" set BACKUP_DIR=%USERPROFILE%\mediguard_backups

if not exist "%BACKUP_DIR%" (
    mkdir "%BACKUP_DIR%"
    echo Created backup directory: %BACKUP_DIR%
)

REM Compute timestamp (YYYYMMDD_HHMMSS)
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set dt=%%I
set TIMESTAMP=%dt:~0,4%%dt:~4,2%%dt:~6,2%_%dt:~8,2%%dt:~10,2%%dt:~12,2%
if "%TIMESTAMP%"=="" set TIMESTAMP=%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%

set BACKUP_FILE=%BACKUP_DIR%\mediguard_%TIMESTAMP%.dump
set LOG_FILE=%BACKUP_DIR%\backup_%TIMESTAMP%.log

echo ====================================================================
echo Starting MediGuard AI Database Backup...
echo Host:     %PGHOST%:%PGPORT%
echo Database: %PGDATABASE%
echo Target:   %BACKUP_FILE%
echo ====================================================================

pg_dump -h %PGHOST% -p %PGPORT% -U %PGUSER% -Fc -b -v %PGDATABASE% > "%BACKUP_FILE%" 2> "%LOG_FILE%"

if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] Backup completed successfully: %BACKUP_FILE%
    REM Generate SHA-256 checksum for backup integrity verification
    certutil -hashfile "%BACKUP_FILE%" SHA256 > "%BACKUP_FILE%.sha256"
    echo Checksum written to %BACKUP_FILE%.sha256
) else (
    echo [ERROR] pg_dump failed with exit code %ERRORLEVEL%. Check log: %LOG_FILE%
    exit /b %ERRORLEVEL%
)

endlocal
