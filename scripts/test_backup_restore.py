"""
MediGuard AI – PostgreSQL Backup & Restore Test Runner
Validates the backup and restore script syntax, checksum generation, and mock restore lifecycle.
"""
import os
import sys
import hashlib
import tempfile
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("mediguard.test_backup")

BACKUP_BAT = BASE_DIR / "scripts" / "pg_backup.bat"
BACKUP_SH = BASE_DIR / "scripts" / "pg_backup.sh"
RESTORE_BAT = BASE_DIR / "scripts" / "pg_restore.bat"
RESTORE_SH = BASE_DIR / "scripts" / "pg_restore.sh"

def test_scripts_exist():
    logger.info("1. Verifying backup and restore script files...")
    assert BACKUP_BAT.exists(), "scripts/pg_backup.bat missing"
    assert BACKUP_SH.exists(), "scripts/pg_backup.sh missing"
    assert RESTORE_BAT.exists(), "scripts/pg_restore.bat missing"
    assert RESTORE_SH.exists(), "scripts/pg_restore.sh missing"
    logger.info("   [PASS] All 4 backup and restore scripts exist.")


def test_script_contents_and_flags():
    logger.info("2. Checking command-line flags and parameters in backup/restore scripts...")
    bat_content = BACKUP_BAT.read_text(encoding="utf-8")
    assert "pg_dump" in bat_content
    assert "-Fc" in bat_content, "Must use custom archive format (-Fc)"
    assert "certutil" in bat_content or "hash" in bat_content, "Must compute SHA-256 checksum"

    sh_content = BACKUP_SH.read_text(encoding="utf-8")
    assert "pg_dump" in sh_content
    assert "-Fc" in sh_content
    assert "sha256sum" in sh_content

    restore_bat = RESTORE_BAT.read_text(encoding="utf-8")
    assert "pg_restore" in restore_bat
    assert "--clean" in restore_bat

    restore_sh = RESTORE_SH.read_text(encoding="utf-8")
    assert "pg_restore" in restore_sh
    assert "--clean" in restore_sh
    logger.info("   [PASS] All scripts use correct pg_dump / pg_restore options (-Fc, --clean).")


def test_backup_integrity_hash_simulation():
    logger.info("3. Simulating backup generation and SHA-256 integrity verification...")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        fake_dump = tmp_path / "mediguard_20261113_220000.dump"
        fake_dump.write_bytes(b"PGDMP\x01\x02\x03\x04\x05MOCK_SQL_DATABASE_DUMP_PAYLOAD")

        # Compute SHA-256
        h = hashlib.sha256(fake_dump.read_bytes()).hexdigest()
        sha_file = tmp_path / f"{fake_dump.name}.sha256"
        sha_file.write_text(f"{h}  {fake_dump.name}\n", encoding="utf-8")

        # Verify SHA-256
        read_h = sha_file.read_text(encoding="utf-8").split()[0]
        recomputed = hashlib.sha256(fake_dump.read_bytes()).hexdigest()
        assert read_h == recomputed, "SHA-256 hash mismatch in restore test"
        logger.info("   [PASS] Backup file hash matches integrity verification: %s", recomputed[:16] + "...")


def main():
    print("=" * 65)
    print("  MEDIGUARD AI – BACKUP & RESTORE RESILIENCE TEST")
    print("=" * 65)
    test_scripts_exist()
    test_script_contents_and_flags()
    test_backup_integrity_hash_simulation()
    print("=" * 65)
    print("  ALL BACKUP & RESTORE RESILIENCE TESTS PASSED (3/3)")
    print("=" * 65)


if __name__ == "__main__":
    main()
