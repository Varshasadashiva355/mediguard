"""
MediGuard AI – Clinical 12-Lead ECG PDF Report Generator
Generates an authentic hospital-grade 12-lead ECG report PDF for monitored patient
MG-2026-000101 (James Harrison, CCU Bed 4) using Matplotlib's vector PDF backend.
"""
import os
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.gridspec as gridspec

# Set temporary config dir for matplotlib sandbox compatibility
os.environ["MPLCONFIGDIR"] = os.environ.get("TEMP", "C:/Windows/Temp")

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "samples" / "ecg"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = OUTPUT_DIR / "patient_MG-2026-000101_12lead_ecg.pdf"

STANDARD_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def generate_clean_ecg_lead(duration_sec=2.5, sampling_rate=250, st_elev=0.0, inv_t=False, amp=1.0):
    """Generate clean synthetic P-Q-R-S-T cardiac cycle waveform."""
    t = np.linspace(0, duration_sec, int(duration_sec * sampling_rate))
    signal = np.zeros_like(t)
    hr_period = 0.8  # ~75 bpm

    for i, ti in enumerate(t):
        cycle_t = ti % hr_period

        # Baseline
        val = 0.0

        # P wave (atrium depolarization)
        if 0.10 <= cycle_t < 0.18:
            val += 0.18 * np.sin((cycle_t - 0.10) * np.pi / 0.08)

        # Q wave
        elif 0.22 <= cycle_t < 0.25:
            val -= 0.15 * np.sin((cycle_t - 0.22) * np.pi / 0.03)

        # R wave (ventricular depolarization)
        elif 0.25 <= cycle_t < 0.31:
            val += 1.6 * amp * np.sin((cycle_t - 0.25) * np.pi / 0.06)

        # S wave
        elif 0.31 <= cycle_t < 0.35:
            val -= 0.35 * np.sin((cycle_t - 0.31) * np.pi / 0.04)

        # ST segment elevation (STEMI pattern)
        if 0.35 <= cycle_t <= 0.60:
            val += st_elev

        # T wave (ventricular repolarization)
        if 0.45 <= cycle_t < 0.65:
            t_wave = 0.35 * np.sin((cycle_t - 0.45) * np.pi / 0.20)
            val += (-t_wave if inv_t else t_wave)

        # Slight physiologic baseline wander
        val += 0.02 * np.sin(2 * np.pi * 0.15 * ti)

        signal[i] = val

    return t, signal


def create_clinical_12lead_pdf(pdf_filepath: Path):
    with PdfPages(pdf_filepath) as pdf:
        # Standard US Letter Landscape: 11 x 8.5 inches
        fig = plt.figure(figsize=(11, 8.5), dpi=300)
        fig.patch.set_facecolor("#FFFFFF")

        # ----------------------------------------------------------------------
        # Top Header & Clinical Banner
        # ----------------------------------------------------------------------
        header_ax = fig.add_axes([0.05, 0.86, 0.90, 0.11])
        header_ax.axis("off")

        # Hospital Branding
        header_ax.text(0.00, 0.90, "🏥 MEDIGUARD CARDIOLOGY CARE & CLINICAL CATH LAB",
                       fontsize=12, fontweight="bold", color="#123B4A")
        header_ax.text(0.00, 0.65, "Department of Interventional Cardiology & Cardiac Intensive Care Unit (CCU)",
                       fontsize=8.5, color="#475569")
        header_ax.text(0.00, 0.40, "GE MAC 5500 HD &bull; 12-Lead Diagnostic Resting ECG &bull; 25 mm/s &bull; 10 mm/mV &bull; Filter: 0.05-150 Hz",
                       fontsize=8, color="#64748B", family="monospace")

        # Patient Demographics Box (Right Side)
        demographics_box = (
            "PATIENT ID:       MG-2026-000101\n"
            "PATIENT NAME:     James Harrison\n"
            "DOB / AGE:        1962-04-12 (64 M)\n"
            "LOCATION:         CCU Bed 4\n"
            "ACQUISITION DATE: 2026-11-13 14:32 EST\n"
            "ATTENDING DOC:    Dr. Alexander Hayes, FACC"
        )
        header_ax.text(0.68, 0.95, demographics_box, fontsize=7.5, family="monospace",
                       color="#0F172A", verticalalignment="top",
                       bbox=dict(boxstyle="round,pad=0.4", facecolor="#F8FAFC", edgecolor="#CBD5E1", linewidth=0.8))

        # Thin divider
        line = plt.Line2D([0.05, 0.95], [0.85, 0.85], transform=fig.transFigure, color="#14B8A6", linewidth=2.0)
        fig.add_artist(line)

        # ----------------------------------------------------------------------
        # Clinical Measurements Sub-banner
        # ----------------------------------------------------------------------
        meas_ax = fig.add_axes([0.05, 0.81, 0.90, 0.035])
        meas_ax.axis("off")
        measurements_text = (
            "HR: 76 bpm  |  PR Int: 164 ms  |  QRS Dur: 88 ms  |  QT/QTc: 412/456 ms  |  P-R-T Axes: 48° / 62° / 74°  |  "
            "LVEF: 42.0%  |  STENT: Everolimus DES (Proximal LAD)"
        )
        meas_ax.text(0.0, 0.5, measurements_text, fontsize=8, fontweight="bold",
                     family="monospace", color="#0F172A", verticalalignment="center")

        # ----------------------------------------------------------------------
        # 12-Lead Waveform Grid: 4 columns x 3 rows + Lead II Rhythm Strip
        # ----------------------------------------------------------------------
        # Columns:
        # Col 0: I,   II,  III
        # Col 1: aVR, aVL, aVF
        # Col 2: V1,  V2,  V3 (STEMI elevation)
        # Col 3: V4,  V5,  V6
        lead_order = [
            ["I",   "aVR", "V1", "V4"],
            ["II",  "aVL", "V2", "V5"],
            ["III", "aVF", "V3", "V6"]
        ]

        # Waveform Grid layout
        left, bottom, width, height = 0.05, 0.22, 0.90, 0.57
        gs = gridspec.GridSpec(3, 4, left=left, bottom=bottom, right=left+width, top=bottom+height,
                              wspace=0.08, hspace=0.18)

        sampling_rate = 250
        duration = 2.5

        for r in range(3):
            for c in range(4):
                lead_name = lead_order[r][c]
                ax = fig.add_subplot(gs[r, c])

                # ST elevation in anterior leads (V2, V3, V4)
                st_elev = 0.0
                inv_t = False
                amp = 1.0

                if lead_name in ("V2", "V3"):
                    st_elev = 0.45  # Pronounced STEMI ST elevation
                    amp = 1.3
                elif lead_name == "V4":
                    st_elev = 0.25
                elif lead_name == "aVR":
                    amp = -0.8
                    inv_t = True
                elif lead_name in ("II", "V5"):
                    amp = 1.1

                t, sig = generate_clean_ecg_lead(duration_sec=duration, sampling_rate=sampling_rate,
                                                 st_elev=st_elev, inv_t=inv_t, amp=amp)

                # Draw standard ECG Millimeter Grid (Pink grid: 0.04s small, 0.2s large)
                ax.set_facecolor("#FFF9F8")  # Classic ECG paper off-pink tint
                ax.set_xlim(0, duration)
                ax.set_ylim(-1.5, 2.5)

                # Minor grid: 0.04 sec (time), 0.1 mV (voltage)
                ax.set_xticks(np.arange(0, duration + 0.01, 0.04), minor=True)
                ax.set_yticks(np.arange(-1.5, 2.51, 0.1), minor=True)
                ax.grid(which="minor", color="#FBCFE8", linestyle="-", linewidth=0.3, alpha=0.6)

                # Major grid: 0.2 sec (time), 0.5 mV (voltage)
                ax.set_xticks(np.arange(0, duration + 0.01, 0.2), minor=False)
                ax.set_yticks(np.arange(-1.5, 2.51, 0.5), minor=False)
                ax.grid(which="major", color="#F472B6", linestyle="-", linewidth=0.6, alpha=0.7)

                ax.set_xticklabels([])
                ax.set_yticklabels([])
                ax.tick_params(left=False, bottom=False, which="both")

                # Plot dark navy cardiac tracing
                ax.plot(t, sig, color="#0F172A", linewidth=1.1, antialiased=True)

                # Lead Label badge
                badge_bg = "#EF4444" if st_elev > 0.2 else "#123B4A"
                ax.text(0.04, 0.88, f" {lead_name} ", transform=ax.transAxes,
                        fontsize=8, fontweight="bold", color="#FFFFFF",
                        verticalalignment="top",
                        bbox=dict(boxstyle="square,pad=0.2", facecolor=badge_bg, edgecolor="none"))

                if st_elev > 0.2:
                    ax.text(0.96, 0.88, "ST ↑", transform=ax.transAxes,
                            fontsize=7.5, fontweight="bold", color="#DC2626",
                            horizontalalignment="right", verticalalignment="top")

                for spine in ax.spines.values():
                    spine.set_color("#E2E8F0")
                    spine.set_linewidth(0.8)

        # ----------------------------------------------------------------------
        # Full-Width Rhythm Strip (Lead II) across bottom
        # ----------------------------------------------------------------------
        rhythm_ax = fig.add_axes([0.05, 0.12, 0.90, 0.08])
        rhythm_duration = 10.0
        t_rhythm, sig_rhythm = generate_clean_ecg_lead(duration_sec=rhythm_duration, sampling_rate=sampling_rate,
                                                       st_elev=0.08, amp=1.15)

        rhythm_ax.set_facecolor("#FFF9F8")
        rhythm_ax.set_xlim(0, rhythm_duration)
        rhythm_ax.set_ylim(-1.5, 2.5)

        rhythm_ax.set_xticks(np.arange(0, rhythm_duration + 0.01, 0.04), minor=True)
        rhythm_ax.set_yticks(np.arange(-1.5, 2.51, 0.1), minor=True)
        rhythm_ax.grid(which="minor", color="#FBCFE8", linestyle="-", linewidth=0.25, alpha=0.5)

        rhythm_ax.set_xticks(np.arange(0, rhythm_duration + 0.01, 0.2), minor=False)
        rhythm_ax.set_yticks(np.arange(-1.5, 2.51, 0.5), minor=False)
        rhythm_ax.grid(which="major", color="#F472B6", linestyle="-", linewidth=0.5, alpha=0.6)

        rhythm_ax.set_xticklabels([])
        rhythm_ax.set_yticklabels([])
        rhythm_ax.tick_params(left=False, bottom=False, which="both")

        rhythm_ax.plot(t_rhythm, sig_rhythm, color="#0F172A", linewidth=1.0)
        rhythm_ax.text(0.01, 0.85, " Lead II (Continuous 10s Rhythm Strip) ", transform=rhythm_ax.transAxes,
                       fontsize=7.5, fontweight="bold", color="#FFFFFF",
                       bbox=dict(boxstyle="square,pad=0.2", facecolor="#14B8A6", edgecolor="none"))

        for spine in rhythm_ax.spines.values():
            spine.set_color("#E2E8F0")
            spine.set_linewidth(0.8)

        # ----------------------------------------------------------------------
        # Bottom Clinical Certification & Protocol Compliance Block
        # ----------------------------------------------------------------------
        footer_ax = fig.add_axes([0.05, 0.02, 0.90, 0.085])
        footer_ax.axis("off")

        # Clinical Diagnosis Statement
        diagnosis_text = (
            "AUTOMATED PRELIMINARY INTERPRETATION:\n"
            "** SINUS RHYTHM WITH ACUTE ANTERIOR INJURY PATTERN (STEMI) **\n"
            "Marked ST elevation in leads V2-V4. Reciprocal changes in inferior leads. Prior stent in LAD vessel."
        )
        footer_ax.text(0.00, 0.95, diagnosis_text, fontsize=7.5, color="#7F1D1D",
                       fontweight="bold", family="monospace", verticalalignment="top")

        # Rule 4 & Clinical Protocol Notice
        protocol_notice = (
            "MEDIGUARD PROTOCOL RULE 4 NOTICE:\n"
            "This recording is stored as a clinical PDF document. Under Rule 4, automated neural network inference applies\n"
            "exclusively to digital CSV signals. Scanned PDFs are routed directly to attending physician visual review."
        )
        footer_ax.text(0.48, 0.95, protocol_notice, fontsize=7, color="#1E3A8A",
                       family="monospace", verticalalignment="top")

        # Physician Signature Line
        footer_ax.text(0.82, 0.35, "________________________________________", fontsize=8, color="#94A3B8")
        footer_ax.text(0.82, 0.10, "Dr. Alexander Hayes, MD, FACC\nCertified Attending Cardiologist",
                       fontsize=7.5, color="#123B4A", fontweight="bold")

        # Save and close PDF
        pdf.savefig(fig)
        plt.close(fig)

    print(f"Successfully generated clinical 12-lead PDF at: {pdf_filepath}")
    print(f"File size: {pdf_filepath.stat().st_size} bytes")


if __name__ == "__main__":
    create_clinical_12lead_pdf(PDF_PATH)
