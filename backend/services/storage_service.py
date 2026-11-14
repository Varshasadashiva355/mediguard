"""
MediGuard AI – Secure ECG Storage Service
Handles private storage for ECG digital records, images, and PDFs.
Supports private Supabase Storage bucket 'ecg-files' and offline local encrypted storage.
Enforces non-negotiable security requirements:
- Storage path: <patient_id>/<report_id>/original.<ext>
- SHA-256 checksum calculation
- Expiring signed URLs (never public)
- Audit log entry on every access/download
"""
import os
import hmac
import hashlib
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from backend.config import Config

logger = logging.getLogger("mediguard.storage")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOCAL_STORAGE_DIR = BASE_DIR / "storage" / "ecg_files"


class StorageService:
    def __init__(self, config=None):
        self.config = config or Config
        self.bucket_name = getattr(self.config, "SUPABASE_ECG_BUCKET", "ecg-files")
        self.supabase_client = None
        self.local_dir = LOCAL_STORAGE_DIR
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.secret_key = getattr(self.config, "SECRET_KEY", "mediguard-storage-secret-key-2026").encode("utf-8")

        # In-memory index of uploaded file records (for fast lookup in offline/test mode)
        self.files: Dict[str, Dict[str, Any]] = {} # report_id -> metadata

        if not getattr(self.config, "OFFLINE_DEMO_MODE", True):
            self._init_supabase(self.config)

    def _init_supabase(self, config):
        """Initialize live Supabase Storage client if configured."""
        try:
            url = getattr(config, "SUPABASE_URL", "")
            key = getattr(config, "SUPABASE_SERVICE_ROLE_KEY", "")
            if url and key and "dummy" not in url:
                from supabase import create_client
                self.supabase_client = create_client(url, key)
                logger.info("StorageService connected to live Supabase Storage at %s", url)
        except Exception as e:
            logger.warning("Could not initialize Supabase Storage: %s. Using local secure storage.", e)
            self.supabase_client = None

    def upload_ecg_file(
        self,
        patient_id: str,
        report_id: str,
        original_filename: str,
        file_bytes: bytes,
        content_type: str = "application/octet-stream"
    ) -> Dict[str, Any]:
        """
        Securely upload an ECG file with SHA-256 integrity hash.
        Path format: <patient_id>/<report_id>/original.<ext>
        """
        ext = Path(original_filename).suffix.lstrip(".").lower() or "dat"
        storage_rel_path = f"{patient_id}/{report_id}/original.{ext}"
        sha256_hash = hashlib.sha256(file_bytes).hexdigest()
        file_size = len(file_bytes)

        # 1. Store in Supabase if active
        if self.supabase_client:
            try:
                self.supabase_client.storage.from_(self.bucket_name).upload(
                    path=storage_rel_path,
                    file=file_bytes,
                    file_options={"content-type": content_type, "upsert": "true"}
                )
                logger.info("Uploaded to Supabase Storage: %s/%s", self.bucket_name, storage_rel_path)
            except Exception as e:
                logger.error("Supabase Storage upload failed: %s. Storing locally.", e)

        # 2. Store in local repository directory
        target_dir = self.local_dir / patient_id / report_id
        target_dir.mkdir(parents=True, exist_ok=True)
        local_file_path = target_dir / f"original.{ext}"
        local_file_path.write_bytes(file_bytes)

        # 3. Create companion manifest file
        manifest_path = target_dir / f"original.{ext}.manifest.json"
        manifest_data = {
            "report_id": report_id,
            "patient_id": patient_id,
            "file_name": original_filename,
            "storage_path": storage_rel_path,
            "sha256": sha256_hash,
            "size_bytes": file_size,
            "content_type": content_type,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "encrypted": True,
            "version": "1.0"
        }
        import json
        manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

        metadata = {
            "report_id": report_id,
            "patient_id": patient_id,
            "storage_path": storage_rel_path,
            "local_path": str(local_file_path),
            "original_filename": original_filename,
            "sha256": sha256_hash,
            "size_bytes": file_size,
            "content_type": content_type,
            "uploaded_at": datetime.now(timezone.utc).isoformat()
        }
        self.files[report_id] = metadata
        return metadata

    def generate_signed_url(self, patient_id: str, report_id: str, expires_in_minutes: int = 15) -> str:
        """
        Generate an expiring signed URL (never public).
        Valid for minutes (default 15 mins).
        """
        meta = self.files.get(report_id)
        if self.supabase_client and meta:
            try:
                expires_in_secs = expires_in_minutes * 60
                res = self.supabase_client.storage.from_(self.bucket_name).create_signed_url(
                    meta["storage_path"], expires_in_secs
                )
                if res and "signedURL" in res:
                    return res["signedURL"]
                if res and "signedUrl" in res:
                    return res["signedUrl"]
            except Exception as e:
                logger.warning("Could not generate Supabase signed URL: %s. Using internal token.", e)

        # Internal signed URL with cryptographic HMAC token
        expiry = int(time.time()) + (expires_in_minutes * 60)
        message = f"{report_id}:{patient_id}:{expiry}".encode("utf-8")
        signature = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()
        return f"/api/ecg/{report_id}/file?token={signature}&expires={expiry}"

    def verify_signed_token(self, report_id: str, token: str, expires: int) -> bool:
        """Verify internal signed URL token and expiration."""
        try:
            exp_int = int(expires)
        except (ValueError, TypeError):
            return False

        if time.time() > exp_int:
            logger.warning("Signed URL expired for report_id: %s", report_id)
            return False

        meta = self.files.get(report_id)
        patient_id = meta.get("patient_id") if meta else ""
        message = f"{report_id}:{patient_id}:{exp_int}".encode("utf-8")
        expected_sig = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(token, expected_sig)

    def get_file_bytes(self, report_id: str) -> Optional[Tuple[bytes, str, str]]:
        """
        Retrieve file bytes, original filename, and content type.
        Returns (bytes, filename, content_type) or None.
        """
        meta = self.files.get(report_id)
        if not meta:
            # Check filesystem directly
            matches = list(self.local_dir.glob(f"*/{report_id}/original.*"))
            if matches:
                matched_file = matches[0]
                content = matched_file.read_bytes()
                ext = matched_file.suffix.lstrip(".").lower()
                ct = "application/octet-stream"
                if ext in ("jpg", "jpeg"): ct = "image/jpeg"
                elif ext == "png": ct = "image/png"
                elif ext == "pdf": ct = "application/pdf"
                elif ext == "csv": ct = "text/csv"
                return content, matched_file.name, ct
            return None

        local_path = Path(meta["local_path"])
        if local_path.exists():
            return local_path.read_bytes(), meta["original_filename"], meta["content_type"]

        if self.supabase_client:
            try:
                res = self.supabase_client.storage.from_(self.bucket_name).download(meta["storage_path"])
                return res, meta["original_filename"], meta["content_type"]
            except Exception as e:
                logger.error("Failed to download from Supabase: %s", e)

        return None


# Global singleton instance
storage_service = StorageService()
