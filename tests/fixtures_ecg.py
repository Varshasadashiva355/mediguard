"""
MediGuard AI – Phase 4 ECG Test Fixtures
Generates clean, verified test files for unit and integration testing:
- Valid digital 12-lead CSV waveforms (clearly synthetic)
- Valid clinical images and PDFs
- Invalid / spoofed test files (wrong magic bytes, empty, short duration, wrong columns)
"""
import io
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image

STANDARD_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def generate_synthetic_ecg_csv_bytes(samples: int = 1000, sampling_rate: float = 100.0) -> bytes:
    """Generate synthetic 12-lead ECG CSV bytes with standard column headers."""
    t = np.linspace(0, samples / sampling_rate, samples)
    data = {}
    base_wave = np.sin(2 * np.pi * 1.25 * t) * 0.5
    spike = np.exp(-((np.mod(t, 0.8) - 0.1) ** 2) / (2 * 0.015 ** 2)) * 1.5

    for idx, lead in enumerate(STANDARD_LEADS):
        gain = 1.0 if idx < 6 else 1.25
        noise = np.random.normal(0, 0.02, samples)
        st_elevation = 0.35 if lead in ("V2", "V3", "V4") else 0.0
        data[lead] = (base_wave + spike) * gain + st_elevation + noise

    df = pd.DataFrame(data)
    out = io.StringIO()
    df.to_csv(out, index=False)
    return out.getvalue().encode("utf-8")


def generate_synthetic_image_bytes(format_type: str = "JPEG", size=(400, 300)) -> bytes:
    """Generate valid JPEG or PNG bytes."""
    img = Image.new("RGB", size, color=(240, 244, 248))
    bio = io.BytesIO()
    img.save(bio, format=format_type)
    return bio.getvalue()


def generate_synthetic_pdf_bytes() -> bytes:
    """Generate minimal valid PDF bytes with %PDF- header."""
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj\n"
        b"xref\n"
        b"0 4\n"
        b"0000000000 65535 f \n"
        b"0000000010 00000 n \n"
        b"0000000060 00000 n \n"
        b"0000000117 00000 n \n"
        b"trailer << /Size 4 /Root 1 0 R >>\n"
        b"startxref\n"
        b"190\n"
        b"%%EOF\n"
    )
    return pdf_content
