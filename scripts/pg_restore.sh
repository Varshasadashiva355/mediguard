#!/usr/bin/env bash
# ==============================================================================
# MediGuard AI – PostgreSQL Restore Script (Unix / Linux)
# Restores database from a custom-format pg_dump archive (.dump)
# Usage: ./pg_restore.sh <path_to_dump_file>
# ==============================================================================
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <path_to_dump_file>" >&2
    exit 1
fi

DUMP_FILE="$1"
if [ ! -f "$DUMP_FILE" ]; then
    echo "[ERROR] Dump file not found: $DUMP_FILE" >&2
    exit 1
fi

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-mediguard}"
PGDATABASE="${PGDATABASE:-mediguard}"

echo "===================================================================="
echo "MediGuard AI – Restoring PostgreSQL Database"
echo "Target DB: ${PGDATABASE} on ${PGHOST}:${PGPORT}"
echo "Dump file: ${DUMP_FILE}"
echo "===================================================================="

if [ -f "${DUMP_FILE}.sha256" ]; then
    echo "Verifying backup checksum..."
    sha256sum -c "${DUMP_FILE}.sha256" || echo "Warning: Checksum verification mismatch"
fi

pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" --clean --if-exists -v "$DUMP_FILE"

echo "[SUCCESS] Database restored successfully to ${PGDATABASE}!"
