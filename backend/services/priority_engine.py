"""
MediGuard AI – Clinical Review Priority Engine
Rule-based, transparent, and configurable decision support priority engine.

NON-NEGOTIABLE SAFETY CONSTRAINTS:
1. Rules are decision support examples: "Example clinical rules – replace with hospital-approved escalation protocol."
2. ML scores may ONLY add a supporting reason (e.g. "experimental model score elevated for MI/STTC – for clinician attention").
3. ML scores can NEVER lower a category.
4. ML scores can NEVER create or escalate to 'urgent' on their own.
5. Every decision returns human-readable reasons (no black-box ranking).
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml

logger = logging.getLogger("mediguard.priority_engine")

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "priority_rules.yaml"


@dataclass
class PriorityResult:
    priority: str  # "urgent", "prompt", "routine"
    reasons: List[str]
    ml_supporting_notes: List[str] = field(default_factory=list)
    rule_disclaimer: str = "Example clinical rules – replace with hospital-approved escalation protocol."
    matched_rules: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "priority": self.priority,
            "reasons": self.reasons,
            "ml_supporting_notes": self.ml_supporting_notes,
            "rule_disclaimer": self.rule_disclaimer,
            "matched_rules": self.matched_rules
        }


class PriorityEngine:
    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config_path = config_path
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        """Load configuration from priority_rules.yaml with safe defaults."""
        if not self.config_path.exists():
            logger.warning(f"Priority rules file not found at {self.config_path}. Using fallback configuration.")
            return self._fallback_rules()

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config or self._fallback_rules()
        except Exception as e:
            logger.error(f"Failed to parse priority rules YAML: {e}. Using fallback configuration.")
            return self._fallback_rules()

    def _fallback_rules(self) -> Dict[str, Any]:
        return {
            "disclaimer": "Example clinical rules – replace with hospital-approved escalation protocol.",
            "thresholds": {
                "urgent_symptoms": ["chest_pain", "syncope", "acute_dyspnea", "ischemic_chest_pressure"],
                "urgent_clinician_urgencies": ["stat_emergency", "urgent"],
                "recent_angioplasty_days_urgent": 14,
                "recent_angioplasty_days_prompt": 30,
                "overdue_followup_days_prompt": 1,
                "min_stent_count_prompt": 1,
                "urgent_validated_findings": ["acute_anterior_stemi", "inferior_stemi", "stemi", "ventricular_tachycardia"],
                "prompt_validated_findings": ["nstemi", "unstable_angina", "atrial_fibrillation"],
                "ml_informative_threshold": 0.65,
                "ml_high_risk_classes": ["MI", "STTC", "CD"]
            },
            "safety_constraints": {
                "ml_can_create_urgent": False,
                "ml_can_lower_category": False
            }
        }

    def evaluate_priority(self, patient_context: Dict[str, Any], ecg_context: Optional[Dict[str, Any]] = None) -> PriorityResult:
        """
        Evaluate clinical priority based on transparent rules.
        
        Args:
            patient_context: Dict containing:
                - clinician_urgency (str): "stat_emergency", "urgent", "routine"
                - symptoms (list of str): e.g. ["chest_pain", "syncope"]
                - days_since_angioplasty (int/float, optional): days since last PCI
                - stent_count (int, optional): number of implanted stents
                - is_overdue_followup (bool, optional): whether follow-up visit is overdue
                - overdue_days (int, optional): number of days overdue
                - previous_findings (list of str, optional): past clinical diagnoses
            ecg_context: Dict containing:
                - model_scores (dict): e.g. {"MI": 0.85, "STTC": 0.72, "NORM": 0.05}
                - signal_quality (str): "good", "acceptable", "poor"
        """
        thresholds = self.rules.get("thresholds", {})
        disclaimer = self.rules.get("disclaimer", "Example clinical rules – replace with hospital-approved escalation protocol.")
        
        reasons: List[str] = []
        matched_rules: List[str] = []
        ml_notes: List[str] = []

        is_urgent = False
        is_prompt = False

        # -------------------------------------------------------------
        # 1. Clinician-Assigned Urgency
        # -------------------------------------------------------------
        clinician_urgency = (patient_context.get("clinician_urgency") or patient_context.get("urgency") or "").lower().strip()
        urgent_urgencies = thresholds.get("urgent_clinician_urgencies", ["stat_emergency", "urgent"])
        if clinician_urgency in urgent_urgencies:
            is_urgent = True
            matched_rules.append("CLINICIAN_URGENCY_URGENT")
            reasons.append(f"Clinician-assigned urgency level: '{clinician_urgency.upper()}'")

        # -------------------------------------------------------------
        # 2. Acute Symptoms Recorded by Staff
        # -------------------------------------------------------------
        symptoms = [s.lower().strip() for s in (patient_context.get("symptoms") or [])]
        urgent_symptoms = thresholds.get("urgent_symptoms", [])
        matched_urgent_symptoms = [s for s in symptoms if s in urgent_symptoms]
        if matched_urgent_symptoms:
            is_urgent = True
            matched_rules.append("ACUTE_SYMPTOM_PRESENT")
            symptoms_str = ", ".join(s.replace("_", " ").title() for s in matched_urgent_symptoms)
            reasons.append(f"Staff recorded acute cardiac symptoms: {symptoms_str}")

        # -------------------------------------------------------------
        # 3. Time Since Angioplasty / Stenting
        # -------------------------------------------------------------
        days_since_pci = patient_context.get("days_since_angioplasty")
        if days_since_pci is not None:
            urgent_pci_days = thresholds.get("recent_angioplasty_days_urgent", 14)
            prompt_pci_days = thresholds.get("recent_angioplasty_days_prompt", 30)
            
            if days_since_pci <= urgent_pci_days:
                is_urgent = True
                matched_rules.append("RECENT_PCI_URGENT")
                reasons.append(f"Recent angioplasty/PCI within {int(days_since_pci)} days (threshold: \u2264 {urgent_pci_days} days)")
            elif days_since_pci <= prompt_pci_days:
                is_prompt = True
                matched_rules.append("RECENT_PCI_PROMPT")
                reasons.append(f"Post-angioplasty recovery at {int(days_since_pci)} days (threshold: \u2264 {prompt_pci_days} days)")

        # -------------------------------------------------------------
        # 4. Stent History
        # -------------------------------------------------------------
        stent_count = patient_context.get("stent_count", 0)
        min_stents = thresholds.get("min_stent_count_prompt", 1)
        if stent_count >= min_stents:
            matched_rules.append("STENT_HISTORY_PRESENT")
            reasons.append(f"Patient has active coronary stent history ({stent_count} stent{'s' if stent_count > 1 else ''})")
            if not is_urgent:
                is_prompt = True

        # -------------------------------------------------------------
        # 5. Overdue Follow-up Visit
        # -------------------------------------------------------------
        is_overdue = patient_context.get("is_overdue_followup", False)
        overdue_days = patient_context.get("overdue_days", 0)
        if is_overdue or overdue_days > 0:
            is_prompt = True
            matched_rules.append("OVERDUE_FOLLOWUP")
            reasons.append(f"Cardiology follow-up appointment is overdue by {overdue_days} day(s)")

        # -------------------------------------------------------------
        # 6. Previous Validated Cardiologist Findings
        # -------------------------------------------------------------
        prev_findings = [f.lower().strip() for f in (patient_context.get("previous_findings") or [])]
        urgent_findings = thresholds.get("urgent_validated_findings", [])
        prompt_findings = thresholds.get("prompt_validated_findings", [])

        for f in prev_findings:
            if any(uf in f for uf in urgent_findings):
                is_urgent = True
                matched_rules.append("PREVIOUS_VALIDATED_FINDING_URGENT")
                reasons.append(f"Previous physician-validated high-risk finding: '{f.title()}'")
                break
            elif any(pf in f for pf in prompt_findings):
                is_prompt = True
                matched_rules.append("PREVIOUS_VALIDATED_FINDING_PROMPT")
                reasons.append(f"Previous physician-validated cardiac finding: '{f.title()}'")

        # -------------------------------------------------------------
        # 7. ML Experimental Decision Support Scores (Strict Safety Enforcement)
        # -------------------------------------------------------------
        if ecg_context and ecg_context.get("model_scores"):
            scores = ecg_context["model_scores"]
            ml_threshold = thresholds.get("ml_informative_threshold", 0.65)
            high_risk_classes = thresholds.get("ml_high_risk_classes", ["MI", "STTC", "CD"])

            elevated_classes = []
            for cls in high_risk_classes:
                val = scores.get(cls, 0.0)
                if val >= ml_threshold:
                    elevated_classes.append((cls, val))

            if elevated_classes:
                matched_rules.append("ML_SUPPORTING_CONCERNING_SCORE")
                for cls, val in elevated_classes:
                    note = f"Experimental model score elevated for {cls} ({val:.2f}) \u2013 for clinician attention"
                    ml_notes.append(note)
                    reasons.append(note)

                # SAFETY RULE: ML score can elevate routine to prompt, but NEVER to urgent!
                if not is_urgent:
                    is_prompt = True

        # -------------------------------------------------------------
        # Final Priority Determination
        # -------------------------------------------------------------
        final_priority = "routine"
        if is_urgent:
            final_priority = "urgent"
        elif is_prompt:
            final_priority = "prompt"

        if not reasons:
            reasons.append("Routine post-procedure outpatient monitoring cohort.")

        return PriorityResult(
            priority=final_priority,
            reasons=reasons,
            ml_supporting_notes=ml_notes,
            rule_disclaimer=disclaimer,
            matched_rules=matched_rules
        )


priority_engine = PriorityEngine()
