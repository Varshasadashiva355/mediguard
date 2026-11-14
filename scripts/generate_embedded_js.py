from pathlib import Path

csv_path = Path("samples/ecg/patient_MG-2026-000104_12lead_ecg.csv")
js_path = Path("frontend/js/beatrice_ecg_data.js")

content = csv_path.read_text(encoding="utf-8")
js_code = f"window.BEATRICE_ECG_CSV = {repr(content)};\n"
js_path.write_text(js_code, encoding="utf-8")
print(f"Generated {js_path} ({len(js_code)} bytes)")
