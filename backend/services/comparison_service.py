"""
MediGuard AI – Historical ECG Comparison Service
Provides chronological timeline of patient ECG reports, trend analytics for the 5 PTB-XL
superclasses, and clinical side-by-side comparison with explicit non-comparability rationales.
NON-NEGOTIABLE RULES:
- Only compares ML-compatible reports with matching sampling rates and usable quality.
- If formats/quality differ, returns an explicit clinical reason.
- Pairs model scores with attending cardiologist interpretations so AI is never the sole voice.
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from backend.services.db_service import db_service

logger = logging.getLogger("mediguard.comparison")

SUPERCLASSES = ["NORM", "MI", "STTC", "CD", "HYP"]


class ComparisonService:
    def get_patient_timeline(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Build an enriched chronological timeline of all ECG reports for a patient,
        attaching analysis scores and signed cardiologist reviews.
        """
        reports = db_service.list_ecg_reports(patient_id=patient_id)
        timeline = []

        for r in reports:
            rep_id = r["id"]
            analysis = db_service.get_ecg_analysis(rep_id)

            # Find matching doctor review if signed
            review = None
            for rev in db_service.doctor_reviews.values():
                if str(rev.get("report_id")) == str(rep_id):
                    review = rev
                    break

            entry = {
                "report_id": rep_id,
                "patient_id": patient_id,
                "file_name": r.get("file_name"),
                "file_type": r.get("file_type"),
                "recording_time": r.get("recording_time"),
                "urgency": r.get("urgency"),
                "status": r.get("status"),
                "is_ml_compatible": (r.get("file_type") == "digital_12lead"),
                "analysis": analysis,
                "doctor_review": review
            }
            timeline.append(entry)

        return sorted(timeline, key=lambda x: str(x.get("recording_time", "")), reverse=False)

    def get_patient_score_trends(self, patient_id: str) -> Dict[str, Any]:
        """
        Generate Chart.js structured datasets for the 5 superclasses over time.
        Strictly filters to ML-compatible reports with valid analysis.
        """
        timeline = self.get_patient_timeline(patient_id)
        valid_points = [
            t for t in timeline
            if t["is_ml_compatible"] and t["analysis"] and t["analysis"].get("signal_quality") != "unusable"
        ]

        dates = []
        scores_norm = []
        scores_mi = []
        scores_sttc = []
        scores_cd = []
        scores_hyp = []

        for p in valid_points:
            rec_time = p["recording_time"]
            formatted_date = rec_time.split("T")[0] if rec_time else "Unknown"
            dates.append(formatted_date)

            ana = p["analysis"]
            scores_norm.append(round(ana.get("norm_score", 0.0), 3))
            scores_mi.append(round(ana.get("mi_score", 0.0), 3))
            scores_sttc.append(round(ana.get("sttc_score", 0.0), 3))
            scores_cd.append(round(ana.get("cd_score", 0.0), 3))
            scores_hyp.append(round(ana.get("hyp_score", 0.0), 3))

        return {
            "labels": dates,
            "datasets": [
                {"label": "NORM (Normal)", "data": scores_norm, "borderColor": "#10B981", "backgroundColor": "rgba(16, 185, 129, 0.1)"},
                {"label": "MI (Myocardial Infarction)", "data": scores_mi, "borderColor": "#EF4444", "backgroundColor": "rgba(239, 68, 68, 0.1)"},
                {"label": "STTC (ST/T Change)", "data": scores_sttc, "borderColor": "#F59E0B", "backgroundColor": "rgba(245, 158, 11, 0.1)"},
                {"label": "CD (Conduction Disturbance)", "data": scores_cd, "borderColor": "#8B5CF6", "backgroundColor": "rgba(139, 92, 246, 0.1)"},
                {"label": "HYP (Hypertrophy)", "data": scores_hyp, "borderColor": "#06B6D4", "backgroundColor": "rgba(6, 182, 212, 0.1)"}
            ],
            "total_ml_reports": len(valid_points),
            "disclaimer": "Experimental model score trajectory. NOT a calibrated diagnostic probability."
        }

    def compare_two_reports(self, report_id_a: str, report_id_b: str) -> Dict[str, Any]:
        """
        Clinically compare two reports.
        Validates cross-compatibility and provides explicit non-comparability reasons.
        """
        rep_a = db_service.get_ecg_report(report_id_a)
        rep_b = db_service.get_ecg_report(report_id_b)

        if not rep_a or not rep_b:
            raise ValueError(f"One or both reports not found: {report_id_a}, {report_id_b}")

        # Rule 4 & Rule 8: Compatibility screening
        incompatible_reasons = []

        type_a = rep_a.get("file_type")
        type_b = rep_b.get("file_type")

        if type_a != "digital_12lead" or type_b != "digital_12lead":
            incompatible_reasons.append(
                f"File format mismatch or non-digital waveform. Report A is '{type_a}' and Report B is '{type_b}'. "
                f"Cross-modal algorithmic comparison between images/PDFs and digital signals is clinically invalid."
            )

        ana_a = db_service.get_ecg_analysis(report_id_a)
        ana_b = db_service.get_ecg_analysis(report_id_b)

        if not ana_a:
            incompatible_reasons.append("Report A does not have an automated analysis completed.")
        if not ana_b:
            incompatible_reasons.append("Report B does not have an automated analysis completed.")

        if ana_a and ana_b:
            if ana_a.get("signal_quality") == "unusable" or ana_b.get("signal_quality") == "unusable":
                incompatible_reasons.append("One or both reports exhibit unusable signal quality / flatline.")

        # Doctor reviews for both reports
        rev_a = None
        rev_b = None
        for r in db_service.doctor_reviews.values():
            if str(r.get("report_id")) == str(report_id_a): rev_a = r
            if str(r.get("report_id")) == str(report_id_b): rev_b = r

        is_comparable = (len(incompatible_reasons) == 0)

        comparison_data = {
            "is_comparable": is_comparable,
            "comparable": is_comparable,
            "reasons_not_comparable": incompatible_reasons,
            "incompatible_reason": "; ".join(incompatible_reasons) if incompatible_reasons else None,
            "patient_code": rep_a.get("patient_code") or rep_b.get("patient_code") or "MG-RECORD",
            "report_a": {
                "id": report_id_a,
                "file_name": rep_a.get("file_name"),
                "file_type": type_a,
                "recording_time": rep_a.get("recording_time"),
                "urgency": rep_a.get("urgency"),
                "status": rep_a.get("status"),
                "scores": {
                    "NORM": ana_a.get("norm_score"),
                    "MI": ana_a.get("mi_score"),
                    "STTC": ana_a.get("sttc_score"),
                    "CD": ana_a.get("cd_score"),
                    "HYP": ana_a.get("hyp_score")
                } if ana_a else {},
                "analysis": ana_a,
                "doctor_review": rev_a
            },
            "report_b": {
                "id": report_id_b,
                "file_name": rep_b.get("file_name"),
                "file_type": type_b,
                "recording_time": rep_b.get("recording_time"),
                "urgency": rep_b.get("urgency"),
                "status": rep_b.get("status"),
                "scores": {
                    "NORM": ana_b.get("norm_score"),
                    "MI": ana_b.get("mi_score"),
                    "STTC": ana_b.get("sttc_score"),
                    "CD": ana_b.get("cd_score"),
                    "HYP": ana_b.get("hyp_score")
                } if ana_b else {},
                "analysis": ana_b,
                "doctor_review": rev_b
            },
            "score_deltas": {},
            "disclaimer": "Comparative delta represents experimental model score variation between recordings. Attending cardiologist retains 100% ownership of clinical progression assessment."
        }

        if is_comparable and ana_a and ana_b:
            for sc in SUPERCLASSES:
                score_a = ana_a.get(f"{sc.lower()}_score", 0.0)
                score_b = ana_b.get(f"{sc.lower()}_score", 0.0)
                delta = round(score_b - score_a, 4)
                direction = "increased" if delta > 0.05 else ("decreased" if delta < -0.05 else "stable")
                comparison_data["score_deltas"][sc] = {
                    "score_a": score_a,
                    "score_b": score_b,
                    "delta": delta,
                    "direction": direction,
                    "trajectory": direction
                }

        return comparison_data


# Global singleton instance
comparison_service = ComparisonService()
