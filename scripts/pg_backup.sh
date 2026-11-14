#!/usr/bin/env bash
# ==============================================================================
# MediGuard AI – Daily PostgreSQL Backup Script (Unix / Linux)
# Performs compressed pg_dump and calculates SHA-256 integrity hash.
# ==============================================================================
set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-mediguard}"
PGDATABASE="${PGDATABASE:-mediguard}"
BACKUP_DIR="${BACKUP_DIR:-${HOME}/mediguard_backups}"

mkdir -p "$BACKUP_DIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/mediguard_${TIMESTAMP}.dump"
LOG_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.log"

echo "===================================================================="
echo "Starting MediGuard AI PostgreSQL Backup..."
echo "Database: ${PGDATABASE} on ${PGHOST}:${PGPORT}"
echo "Output:   ${BACKUP_FILE}"
echo "===================================================================="

if pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -Fc -b -v "$PGDATABASE" > "$BACKUP_FILE" 2> "$LOG_FILE"; then
    echo "[SUCCESS] Backup completed: ${BACKUP_FILE}"
    sha256sum "$BACKUP_FILE" > "${BACKUP_FILE}.sha256"
    echo "Integrity hash saved to ${BACKUP_FILE}.sha256"
else
    echo "[ERROR] pg_dump failed. Check log at ${LOG_FILE}" >&2
    exit 1
fi
