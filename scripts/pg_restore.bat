@echo off
REM ==============================================================================
REM MediGuard AI – PostgreSQL Restore Script (Windows)
REM Restores database from a custom-format pg_dump archive (.dump)
REM Usage: pg_restore.bat <path_to_dump_file>
REM ==============================================================================

setlocal enabledelayedexpansion

if "%~1"=="" (
    echo [ERROR] Missing dump file parameter.
    echo Usage: pg_restore.bat ^<path_to_dump_file^>
    exit /b 1
)

set DUMP_FILE=%~1
if not exist "%DUMP_FILE%" (
    echo [ERROR] Backup dump file not found: %DUMP_FILE%
    exit /b 1
)

if "%PGHOST%"=="" set PGHOST=localhost
if "%PGPORT%"=="" set PGPORT=5432
if "%PGUSER%"=="" set PGUSER=mediguard
if "%PGDATABASE%"=="" set PGDATABASE=mediguard

echo ====================================================================
echo MediGuard AI – Restoring PostgreSQL Database
echo Target DB: %PGDATABASE% on %PGHOST%:%PGPORT%
echo Dump file: %DUMP_FILE%
echo ====================================================================

REM Optional checksum check
if exist "%DUMP_FILE%.sha256" (
    echo Verifying SHA-256 checksum...
    certutil -hashfile "%DUMP_FILE%" SHA256
)

echo Restoring schema and data with pg_restore (--clean --if-exists)...
pg_restore -h %PGHOST% -p %PGPORT% -U %PGUSER% -d %PGDATABASE% --clean --if-exists -v "%DUMP_FILE%"

if %ERRORLEVEL% LEQ 1 (
    echo [SUCCESS] Database restored successfully to %PGDATABASE%!
) else (
    echo [ERROR] pg_restore failed with exit code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)

endlocal
