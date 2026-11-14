"""
MediGuard AI – Encrypted ECG Per-File Manifest Generator & Validator
Generates companion manifest JSON files (<file>.manifest.json) alongside each encrypted
ECG waveform archive, containing: report_id, sha256, report_date, file_name, and size.
"""
import os
import sys
import json
import hashlib
import logging
from datetime import datetime, timezone, date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("mediguard.ecg_manifest")

DEFAULT_STORAGE_DIR = BASE_DIR / "storage" / "ecg_files"


def compute_sha256(file_path: Path) -> str:
    """Calculate the SHA-256 hex digest of a file in streaming chunks."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_manifest_for_file(file_path: Path, report_id: str = None, report_date: str = None) -> Path:
    """Generate a .manifest.json file next to an encrypted ECG file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Target ECG file not found: {file_path}")

    sha256_hash = compute_sha256(file_path)
    file_stat = file_path.stat()

    # Determine report_id from filename if not explicitly provided
    # e.g., "55555555-5555-5555-5555-555555550101_12lead.enc" -> "55555555-5555-5555-5555-555555550101"
    if not report_id:
        stem = file_path.name.replace(".enc", "").replace(".dat", "").replace("_12lead", "")
        report_id = stem

    if not report_date:
        # Default to file modification date or current UTC date
        report_date = date.fromtimestamp(file_stat.st_mtime).isoformat()

    manifest_data = {
        "report_id": report_id,
        "file_name": file_path.name,
        "sha256": sha256_hash,
        "report_date": report_date,
        "size_bytes": file_stat.st_size,
        "encrypted": True,
        "encryption_algorithm": "AES-256-GCM / ChaCha20-Poly1305",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.0"
    }

    manifest_path = file_path.parent / f"{file_path.name}.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    logger.info("Manifest created: %s [SHA256: %s...]", manifest_path.name, sha256_hash[:12])
    return manifest_path


def verify_file_manifest(manifest_path: Path) -> bool:
    """Verify that the encrypted ECG file matches the SHA-256 in its companion manifest."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Locate companion file
    file_name = manifest.get("file_name")
    if not file_name:
        raise ValueError(f"Manifest {manifest_path} missing 'file_name'")

    target_file = manifest_path.parent / file_name
    if not target_file.exists():
        logger.error("Target ECG file %s does not exist next to manifest %s", file_name, manifest_path)
        return False

    actual_hash = compute_sha256(target_file)
    expected_hash = manifest.get("sha256")

    if actual_hash != expected_hash:
        logger.error("Integrity check FAILED for %s! Expected: %s, Found: %s", file_name, expected_hash, actual_hash)
        return False

    logger.info("Integrity check PASSED for %s (Report ID: %s, Date: %s)", file_name, manifest.get("report_id"), manifest.get("report_date"))
    return True


def scan_and_generate_all(storage_dir: Path = DEFAULT_STORAGE_DIR):
    """Scan directory and generate missing manifests for all encrypted ECG files."""
    if not storage_dir.exists():
        storage_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for ext in ("*.enc", "*.dat"):
        for ecg_file in storage_dir.glob(ext):
            generate_manifest_for_file(ecg_file)
            count += 1

    logger.info("Processed %d ECG files in %s", count, storage_dir)
    return count


def verify_all_in_dir(storage_dir: Path = DEFAULT_STORAGE_DIR) -> tuple:
    """Verify all manifests in the given directory."""
    manifests = list(storage_dir.glob("*.manifest.json"))
    passed = 0
    failed = 0

    for m in manifests:
        if verify_file_manifest(m):
            passed += 1
        else:
            failed += 1

    return passed, failed


def create_sample_encrypted_ecg_suite(target_dir: Path = DEFAULT_STORAGE_DIR):
    """Create sample encrypted ECG files and companion manifests for validation."""
    target_dir.mkdir(parents=True, exist_ok=True)
    sample_records = [
        ("55555555-5555-5555-5555-555555550101", "2026-11-10", b"MEDIGUARD_ENCRYPTED_AES256GCM_SAMPLE_RECORD_01"),
        ("55555555-5555-5555-5555-555555550102", "2026-11-11", b"MEDIGUARD_ENCRYPTED_AES256GCM_SAMPLE_RECORD_02"),
        ("55555555-5555-5555-5555-555555550103", "2026-11-12", b"MEDIGUARD_ENCRYPTED_AES256GCM_SAMPLE_RECORD_03"),
        ("55555555-5555-5555-5555-555555550104", "2026-11-13", b"MEDIGUARD_ENCRYPTED_AES256GCM_SAMPLE_RECORD_04"),
    ]

    for rep_id, rep_date, data in sample_records:
        ecg_file = target_dir / f"{rep_id}_12lead.enc"
        ecg_file.write_bytes(data)
        generate_manifest_for_file(ecg_file, report_id=rep_id, report_date=rep_date)

    logger.info("Created %d sample encrypted ECG files and companion manifests in %s", len(sample_records), target_dir)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MediGuard ECG Manifest Tool")
    parser.add_argument("--create-samples", action="store_true", help="Generate sample encrypted ECG files and manifests")
    parser.add_argument("--verify", action="store_true", help="Verify all manifests in storage directory")
    args = parser.parse_args()

    if args.create_samples:
        create_sample_encrypted_ecg_suite()
    
    if args.verify or not sys.argv[1:]:
        create_sample_encrypted_ecg_suite()
        passed, failed = verify_all_in_dir()
        print(f"\nVerification Results: {passed} PASSED, {failed} FAILED")
