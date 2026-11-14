"""
MediGuard AI – Phase 4 Sample Files Generator
Creates realistic synthetic sample files for testing all ECG ingestion pipelines:
1. sample_12lead_acute_stemi.csv   - Digital 12-lead CSV with anterior ST elevation (ML compatible)
2. sample_12lead_normal_sinus.csv  - Digital 12-lead CSV with normal sinus rhythm (ML compatible)
3. sample_scanned_rhythm_strip.jpg - Scanned ECG rhythm strip image (Cardiologist review only, No ML)
4. sample_telemetry_strip.png      - Telemetry rhythm strip image (Cardiologist review only, No ML)
5. sample_clinical_ecg_report.pdf  - Clinical ECG hospital PDF document (Cardiologist review only, No ML)
6. sample_corrupted_spoofed.csv    - Invalid file to verify validation checks
"""
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

STANDARD_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples" / "ecg"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def create_digital_csv(filename: str, st_elevation_leads: list = None, samples: int = 1000, sampling_rate: float = 100.0):
    t = np.linspace(0, samples / sampling_rate, samples)
    data = {}
    base_wave = np.sin(2 * np.pi * 1.25 * t) * 0.4
    spike = np.exp(-((np.mod(t, 0.8) - 0.1) ** 2) / (2 * 0.015 ** 2)) * 1.6

    for idx, lead in enumerate(STANDARD_LEADS):
        gain = 1.0 if idx < 6 else 1.25
        noise = np.random.normal(0, 0.015, samples)
        st_elev = 0.40 if (st_elevation_leads and lead in st_elevation_leads) else 0.0
        data[lead] = np.round((base_wave + spike) * gain + st_elev + noise, 4)

    df = pd.DataFrame(data)
    file_path = SAMPLES_DIR / filename
    df.to_csv(file_path, index=False)
    print(f"Generated: {file_path.name} ({file_path.stat().st_size} bytes)")
    return file_path


def create_scanned_image(filename: str, format_type: str = "JPEG"):
    width, height = 800, 300
    img = Image.new("RGB", (width, height), color=(255, 250, 245))
    draw = ImageDraw.Draw(img)

    # Draw pink/red ECG grid
    for x in range(0, width, 20):
        draw.line([(x, 0), (x, height)], fill=(255, 220, 220), width=1)
    for y in range(0, height, 20):
        draw.line([(0, y), (width, y)], fill=(255, 220, 220), width=1)
    for x in range(0, width, 100):
        draw.line([(x, 0), (x, height)], fill=(255, 180, 180), width=1)
    for y in range(0, height, 100):
        draw.line([(0, y), (width, y)], fill=(255, 180, 180), width=1)

    # Draw ECG waveform tracing
    points = []
    for x in range(width):
        t = (x % 160) / 160.0
        y_val = 150
        if 0.15 < t < 0.25:
            y_val -= 15 * np.sin((t - 0.15) * np.pi / 0.1)
        elif 0.28 < t < 0.30:
            y_val += 10
        elif 0.30 < t < 0.35:
            y_val -= 90 * np.sin((t - 0.30) * np.pi / 0.05)
        elif 0.35 < t < 0.38:
            y_val += 25
        elif 0.48 < t < 0.65:
            y_val -= 20 * np.sin((t - 0.48) * np.pi / 0.17)
        points.append((x, int(y_val)))

    draw.line(points, fill=(18, 59, 74), width=2)
    draw.text((25, 20), f"MediGuard AI - Scanned Rhythm Strip (Lead II) [DEMO ONLY]", fill=(18, 59, 74))
    draw.text((25, 40), f"25 mm/s, 10 mm/mV - Awaiting Attending Cardiologist Interpretation", fill=(100, 116, 139))

    file_path = SAMPLES_DIR / filename
    img.save(file_path, format=format_type)
    print(f"Generated: {file_path.name} ({file_path.stat().st_size} bytes)")
    return file_path


def create_clinical_pdf(filename: str):
    # Valid minimal PDF conforming to PDF-1.4 standard
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj\n"
        b"4 0 obj << /Length 135 >> stream\n"
        b"BT\n"
        b"/F1 14 Tf\n"
        b"72 720 Td\n"
        b"(MediGuard AI Hospital Cardiology - 12-Lead ECG Report) Tj\n"
        b"0 -24 Td\n"
        b"(Rule 4 Clinical Protocol: Document PDF routed to Attending Cardiologist Review.) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"xref\n"
        b"0 5\n"
        b"0000000000 65535 f \n"
        b"0000000010 00000 n \n"
        b"0000000060 00000 n \n"
        b"0000000117 00000 n \n"
        b"0000000213 00000 n \n"
        b"trailer << /Size 5 /Root 1 0 R >>\n"
        b"startxref\n"
        b"402\n"
        b"%%EOF\n"
    )
    file_path = SAMPLES_DIR / filename
    file_path.write_bytes(pdf_bytes)
    print(f"Generated: {file_path.name} ({file_path.stat().st_size} bytes)")
    return file_path


def create_invalid_file(filename: str):
    # Non-CSV binary contents disguised as CSV
    file_path = SAMPLES_DIR / filename
    file_path.write_bytes(b"\x00\x01\x02\xFF\xFE\xFD" * 50)
    print(f"Generated: {file_path.name} ({file_path.stat().st_size} bytes)")
    return file_path


if __name__ == "__main__":
    print("Generating Phase 4 sample files in:", SAMPLES_DIR)
    create_digital_csv("sample_12lead_acute_stemi.csv", st_elevation_leads=["V2", "V3", "V4"])
    create_digital_csv("sample_12lead_normal_sinus.csv", st_elevation_leads=None)
    create_scanned_image("sample_scanned_rhythm_strip.jpg", format_type="JPEG")
    create_scanned_image("sample_telemetry_strip.png", format_type="PNG")
    create_clinical_pdf("sample_clinical_ecg_report.pdf")
    create_invalid_file("sample_corrupted_spoofed.csv")
    print("All sample files generated successfully!")
