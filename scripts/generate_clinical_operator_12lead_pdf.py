"""
MediGuard AI – Clinical Operator 12-Lead ECG PDF Generator
Generates a hospital-grade, error-free vector 12-Lead ECG PDF report
featuring authentic clinical operator metadata, calibrated millimeter grid,
standard diagnostic measurements, and verified physician sign-off.
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
PDF_PATH = OUTPUT_DIR / "patient_MG-2026-000101_12lead_clinical_operators.pdf"

STANDARD_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def generate_cardiac_cycle(duration_sec=2.5, sampling_rate=250, st_elev=0.0, inv_t=False, amp=1.0, hr_bpm=76):
    """Generate authentic P-Q-R-S-T waveform with calibrated intervals."""
    t = np.linspace(0, duration_sec, int(duration_sec * sampling_rate))
    signal = np.zeros_like(t)
    hr_period = 60.0 / hr_bpm  # ~0.789s for 76 bpm

    for i, ti in enumerate(t):
        cycle_t = ti % hr_period
        val = 0.0

        # P Wave (Atrial Depolarization: duration ~80ms, amp ~0.15mV)
        if 0.08 <= cycle_t < 0.16:
            val += 0.15 * np.sin((cycle_t - 0.08) * np.pi / 0.08)

        # PR Segment (AV Node conduction delay ~60ms)
        # Q Wave (Septal Depolarization: duration ~30ms, negative deflection)
        elif 0.22 <= cycle_t < 0.25:
            val -= 0.18 * np.sin((cycle_t - 0.22) * np.pi / 0.03)

        # R Wave (Ventricular Depolarization: sharp peak ~1.4 - 1.8mV)
        elif 0.25 <= cycle_t < 0.31:
            val += 1.65 * amp * np.sin((cycle_t - 0.25) * np.pi / 0.06)

        # S Wave (Late Ventricular Depolarization)
        elif 0.31 <= cycle_t < 0.35:
            val -= 0.35 * np.sin((cycle_t - 0.31) * np.pi / 0.04)

        # ST Segment (Anterior STEMI elevation)
        if 0.35 <= cycle_t <= 0.58:
            val += st_elev

        # T Wave (Ventricular Repolarization)
        if 0.45 <= cycle_t < 0.65:
            t_val = 0.38 * np.sin((cycle_t - 0.45) * np.pi / 0.20)
            val += (-t_val if inv_t else t_val)

        # Physiologic respiratory baseline wander (0.15 Hz)
        val += 0.015 * np.sin(2 * np.pi * 0.15 * ti)

        signal[i] = val

    return t, signal


def generate_calibration_pulse(sampling_rate=250):
    """Standard 1 mV = 10 mm calibration step pulse (duration 0.2s)."""
    t_pulse = np.linspace(0, 0.4, int(0.4 * sampling_rate))
    pulse = np.zeros_like(t_pulse)
    for i, ti in enumerate(t_pulse):
        if 0.10 <= ti <= 0.30:
            pulse[i] = 1.0  # 1.0 mV standard calibration square wave
    return t_pulse, pulse


def build_clinical_operators_pdf(pdf_filepath: Path):
    with PdfPages(pdf_filepath) as pdf:
        # Standard US Letter Landscape: 11.0 x 8.5 inches
        fig = plt.figure(figsize=(11.0, 8.5), dpi=300)
        fig.patch.set_facecolor("#FFFFFF")

        # ----------------------------------------------------------------------
        # Top Header: Hospital Brand, Clinical Operators & Patient Metadata
        # ----------------------------------------------------------------------
        header_ax = fig.add_axes([0.04, 0.84, 0.92, 0.13])
        header_ax.axis("off")

        # Left Column: Hospital & Department Branding
        header_ax.text(0.00, 0.95, "MEDIGUARD CARDIOLOGY CARE & CLINICAL CATH LAB",
                       fontsize=11.5, fontweight="bold", color="#123B4A")
        header_ax.text(0.00, 0.72, "Cardiac Intensive Care Unit (CCU) & Interventional Cardiology Service",
                       fontsize=8.5, color="#334155")
        header_ax.text(0.00, 0.48, "Institutional NPI: 1982736410  |  Clinical Station: CCU-WEST-MONITOR-04",
                       fontsize=7.5, color="#64748B", family="monospace")
        header_ax.text(0.00, 0.24, "Acquisition Console: GE Healthcare MAC 5500 HD / Marquette 12SL v23.1",
                       fontsize=7.5, color="#64748B", family="monospace")
        header_ax.text(0.00, 0.02, "Calibration: 25 mm/s  |  10 mm/mV  |  Bandwidth: 0.05 - 150 Hz  |  Notch: 60 Hz Active",
                       fontsize=7.5, fontweight="bold", color="#0F766E", family="monospace")

        # Middle Column: Clinical Operators Box
        operators_box = (
            "CLINICAL OPERATORS & STAFF:\n"
            "Recording Tech: Maria Santos, CCT (ID: STF-0202)\n"
            "Bedside Nurse:  RN Robert Davis, BSN (ID: STF-0201)\n"
            "Ordering Doc:   Dr. Sarah Chen, MD (NPI: 1948201948)\n"
            "Attending Doc:  Dr. Alexander Hayes, FACC (NPI: 1829402910)\n"
            "Console Status: Calibrated & Operator Verified OK"
        )
        header_ax.text(0.42, 0.95, operators_box, fontsize=7.2, family="monospace",
                       color="#0F172A", verticalalignment="top",
                       bbox=dict(boxstyle="round,pad=0.35", facecolor="#F1F5F9", edgecolor="#CBD5E1", linewidth=0.8))

        # Right Column: Patient Profile Box (Matched to Database)
        patient_box = (
            "PATIENT REGISTRY RECORD:\n"
            "Patient ID:  MG-2026-000101\n"
            "Name:        James Harrison\n"
            "DOB / Age:   1962-04-12 (64 M)\n"
            "Location:    CCU Bed 4 (Bedside)\n"
            "Recorded:    2026-11-14 04:30:00 EST\n"
            "Stents / EF: Everolimus DES (LAD) | 42%"
        )
        header_ax.text(0.725, 0.95, patient_box, fontsize=7.2, family="monospace",
                       color="#0F172A", verticalalignment="top",
                       bbox=dict(boxstyle="round,pad=0.35", facecolor="#F8FAFC", edgecolor="#94A3B8", linewidth=0.8))

        # Teal Accent Separator Line
        divider = plt.Line2D([0.04, 0.96], [0.835, 0.835], transform=fig.transFigure, color="#14B8A6", linewidth=1.8)
        fig.add_artist(divider)

        # ----------------------------------------------------------------------
        # Clinical Measurements Bar
        # ----------------------------------------------------------------------
        meas_ax = fig.add_axes([0.04, 0.80, 0.92, 0.032])
        meas_ax.axis("off")
        meas_text = (
            "HR: 76 bpm  |  PR: 164 ms  |  QRS: 94 ms  |  QT/QTc: 412/448 ms  |  Axes (P/QRS/T): 52° / 64° / 78°  |  "
            "R-R: 789 ms  |  Triage Urgency: URGENT (Acute STEMI)"
        )
        meas_ax.text(0.00, 0.5, meas_text, fontsize=8.0, fontweight="bold",
                     family="monospace", color="#0F172A", verticalalignment="center")

        # ----------------------------------------------------------------------
        # 12-Lead Waveform Grid (4 Columns x 3 Rows)
        # ----------------------------------------------------------------------
        lead_order = [
            ["I",   "aVR", "V1", "V4"],
            ["II",  "aVL", "V2", "V5"],
            ["III", "aVF", "V3", "V6"]
        ]

        left, bottom, width, height = 0.04, 0.20, 0.92, 0.58
        gs = gridspec.GridSpec(3, 4, left=left, bottom=bottom, right=left+width, top=bottom+height,
                              wspace=0.07, hspace=0.16)

        sampling_rate = 250
        duration = 2.5

        for r in range(3):
            for c in range(4):
                lead_name = lead_order[r][c]
                ax = fig.add_subplot(gs[r, c])

                # Clinical STEMI wave modifications
                st_elev = 0.0
                inv_t = False
                amp = 1.0

                if lead_name in ("V2", "V3"):
                    st_elev = 0.42  # Marked ST elevation in anterior leads
                    amp = 1.25
                elif lead_name == "V4":
                    st_elev = 0.22
                    amp = 1.15
                elif lead_name in ("III", "aVF"):
                    inv_t = True  # Reciprocal inferior T-wave inversion
                    amp = 0.85
                elif lead_name == "aVR":
                    amp = -0.85
                    inv_t = True
                elif lead_name in ("I", "II", "V5", "V6"):
                    amp = 1.05

                t, sig = generate_cardiac_cycle(duration_sec=duration, sampling_rate=sampling_rate,
                                                st_elev=st_elev, inv_t=inv_t, amp=amp, hr_bpm=76)

                # Set ECG Pink Millimeter Grid Paper Style
                ax.set_facecolor("#FFF9F8")
                ax.set_xlim(0, duration)
                ax.set_ylim(-1.5, 2.5)

                # Minor grid: 0.04s (time), 0.1mV (voltage)
                ax.set_xticks(np.arange(0, duration + 0.01, 0.04), minor=True)
                ax.set_yticks(np.arange(-1.5, 2.51, 0.1), minor=True)
                ax.grid(which="minor", color="#FBCFE8", linestyle="-", linewidth=0.3, alpha=0.55)

                # Major grid: 0.20s (time), 0.5mV (voltage)
                ax.set_xticks(np.arange(0, duration + 0.01, 0.20), minor=False)
                ax.set_yticks(np.arange(-1.5, 2.51, 0.5), minor=False)
                ax.grid(which="major", color="#F472B6", linestyle="-", linewidth=0.6, alpha=0.7)

                ax.set_xticklabels([])
                ax.set_yticklabels([])
                ax.tick_params(left=False, bottom=False, which="both")

                # Plot cardiac trace
                ax.plot(t, sig, color="#0F172A", linewidth=1.15, antialiased=True)

                # Lead Badge
                badge_bg = "#EF4444" if st_elev > 0.2 else "#123B4A"
                ax.text(0.03, 0.88, f" {lead_name} ", transform=ax.transAxes,
                        fontsize=7.5, fontweight="bold", color="#FFFFFF",
                        verticalalignment="top",
                        bbox=dict(boxstyle="square,pad=0.2", facecolor=badge_bg, edgecolor="none"))

                if st_elev > 0.2:
                    ax.text(0.97, 0.88, "ST ↑ Anteroseptal", transform=ax.transAxes,
                            fontsize=7.0, fontweight="bold", color="#DC2626",
                            horizontalalignment="right", verticalalignment="top")
                elif inv_t and lead_name in ("III", "aVF"):
                    ax.text(0.97, 0.88, "Reciprocal T↓", transform=ax.transAxes,
                            fontsize=7.0, color="#64748B",
                            horizontalalignment="right", verticalalignment="top")

                for spine in ax.spines.values():
                    spine.set_color("#CBD5E1")
                    spine.set_linewidth(0.7)

        # ----------------------------------------------------------------------
        # Full-Width Continuous 10-Second Lead II Rhythm Strip with Calibration Pulse
        # ----------------------------------------------------------------------
        rhythm_ax = fig.add_axes([0.04, 0.10, 0.92, 0.085])
        rhythm_duration = 10.0
        t_rhythm, sig_rhythm = generate_cardiac_cycle(duration_sec=rhythm_duration, sampling_rate=sampling_rate,
                                                      st_elev=0.06, amp=1.1, hr_bpm=76)

        # Add 1mV calibration step pulse at the start of rhythm strip (0.0 to 0.4s)
        t_pulse, pulse = generate_calibration_pulse(sampling_rate=sampling_rate)
        sig_rhythm[:len(pulse)] = pulse

        rhythm_ax.set_facecolor("#FFF9F8")
        rhythm_ax.set_xlim(0, rhythm_duration)
        rhythm_ax.set_ylim(-1.5, 2.5)

        rhythm_ax.set_xticks(np.arange(0, rhythm_duration + 0.01, 0.04), minor=True)
        rhythm_ax.set_yticks(np.arange(-1.5, 2.51, 0.1), minor=True)
        rhythm_ax.grid(which="minor", color="#FBCFE8", linestyle="-", linewidth=0.25, alpha=0.5)

        rhythm_ax.set_xticks(np.arange(0, rhythm_duration + 0.01, 0.20), minor=False)
        rhythm_ax.set_yticks(np.arange(-1.5, 2.51, 0.5), minor=False)
        rhythm_ax.grid(which="major", color="#F472B6", linestyle="-", linewidth=0.55, alpha=0.65)

        rhythm_ax.set_xticklabels([])
        rhythm_ax.set_yticklabels([])
        rhythm_ax.tick_params(left=False, bottom=False, which="both")

        rhythm_ax.plot(t_rhythm, sig_rhythm, color="#0F172A", linewidth=1.05)
        rhythm_ax.text(0.01, 0.85, " Lead II (Continuous 10s Rhythm Strip & 1mV Calibration Pulse) ",
                       transform=rhythm_ax.transAxes, fontsize=7.2, fontweight="bold", color="#FFFFFF",
                       bbox=dict(boxstyle="square,pad=0.2", facecolor="#14B8A6", edgecolor="none"))

        for spine in rhythm_ax.spines.values():
            spine.set_color("#CBD5E1")
            spine.set_linewidth(0.7)

        # ----------------------------------------------------------------------
        # Footer: Operator Verification, Clinical Interpretation & Legal Disclaimers
        # ----------------------------------------------------------------------
        footer_ax = fig.add_axes([0.04, 0.012, 0.92, 0.08])
        footer_ax.axis("off")

        # Preliminary Automated Interpretation
        diag_statement = (
            "PRELIMINARY MACHINE READ:\n"
            "ACUTE ANTERIOR WALL MYOCARDIAL INFARCTION (STEMI)  |  SINUS RHYTHM AT 76 BPM\n"
            "Significant ST elevation in leads V2-V4. Reciprocal ST/T depression in III, aVF. Post-PCI LAD stent on file."
        )
        footer_ax.text(0.00, 0.95, diag_statement, fontsize=7.2, color="#991B1B",
                       fontweight="bold", family="monospace", verticalalignment="top")

        # Clinical Operators Verification
        op_sign = (
            "OPERATOR ACQUISITION VERIFICATION:\n"
            "Technician: Maria Santos, CCT [Verified OK]\n"
            "Acquisition Time: 2026-11-14 04:30:15 EST\n"
            "Lead Contact Impedance: Low (<5 kOhm) - High Quality"
        )
        footer_ax.text(0.44, 0.95, op_sign, fontsize=7.0, color="#334155",
                       family="monospace", verticalalignment="top")

        # Attending Physician Electronic Signature
        footer_ax.text(0.78, 0.95, "ATTENDING PHYSICIAN REVIEW:\nDr. Alexander Hayes, MD, FACC\nNPI: 1829402910 | Status: SIGNED & ACTIVE\nClinical Decision: Cath Lab Urgent Review",
                       fontsize=7.0, color="#123B4A", fontweight="bold", family="monospace", verticalalignment="top")

        # Save PDF cleanly
        pdf.savefig(fig)
        plt.close(fig)

    print(f"Successfully created clinical operators 12-lead PDF at: {pdf_filepath}")
    print(f"File size: {pdf_filepath.stat().st_size} bytes")


if __name__ == "__main__":
    build_clinical_operators_pdf(PDF_PATH)
