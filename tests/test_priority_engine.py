"""
Tests for MediGuard AI – Priority Engine
Validates rule-based transparent clinical prioritization and strictly enforces:
- An ML score alone NEVER moves a patient into Urgent.
- ML scores can NEVER lower an existing urgency level.
- Acute symptoms and clinician urgency escalate to Urgent immediately.
"""
import pytest
from backend.services.priority_engine import priority_engine, PriorityEngine


def test_clinician_assigned_urgent():
    """Clinician-assigned urgent or stat_emergency results in Urgent."""
    res = priority_engine.evaluate_priority({"clinician_urgency": "stat_emergency"})
    assert res.priority == "urgent"
    assert any("STAT_EMERGENCY" in r for r in res.reasons)
    assert res.rule_disclaimer is not None


def test_acute_symptoms_urgent():
    """Staff recorded acute symptoms (e.g. chest pain) triggers Urgent."""
    res = priority_engine.evaluate_priority({
        "clinician_urgency": "routine",
        "symptoms": ["chest_pain"]
    })
    assert res.priority == "urgent"
    assert any("Chest Pain" in r for r in res.reasons)


def test_recent_angioplasty_urgent():
    """Recent angioplasty within 14 days triggers Urgent review."""
    res = priority_engine.evaluate_priority({
        "clinician_urgency": "routine",
        "days_since_angioplasty": 5
    })
    assert res.priority == "urgent"
    assert any("angioplasty/PCI within 5 days" in r for r in res.reasons)


def test_stent_history_or_overdue_prompt():
    """Stent history or overdue follow-up elevates to Prompt."""
    res = priority_engine.evaluate_priority({
        "clinician_urgency": "routine",
        "stent_count": 2,
        "is_overdue_followup": True,
        "overdue_days": 10
    })
    assert res.priority == "prompt"
    assert any("2 stents" in r for r in res.reasons)
    assert any("overdue by 10 day" in r for r in res.reasons)


def test_ml_score_alone_never_creates_urgent():
    """
    CRITICAL ACCEPTANCE CHECK:
    An ML score alone NEVER moves a patient into Urgent.
    Even with MI score = 0.99 and STTC = 0.95, it must result in 'prompt' at most.
    """
    patient_context = {
        "clinician_urgency": "routine",
        "symptoms": [],
        "days_since_angioplasty": 180,
        "stent_count": 0,
        "is_overdue_followup": False
    }
    ecg_context = {
        "model_scores": {
            "MI": 0.99,
            "STTC": 0.95,
            "NORM": 0.01,
            "CD": 0.10,
            "HYP": 0.05
        }
    }
    res = priority_engine.evaluate_priority(patient_context, ecg_context)
    
    # Must NOT be urgent
    assert res.priority != "urgent", "Violation of Safety Rule: ML score alone moved patient into Urgent!"
    assert res.priority == "prompt"
    assert any("Experimental model score elevated for MI" in note for note in res.ml_supporting_notes)
    assert any("Experimental model score elevated for STTC" in note for note in res.ml_supporting_notes)


def test_ml_score_never_lowers_urgency():
    """High NORM score can never lower an Urgent or Prompt patient."""
    patient_context = {
        "clinician_urgency": "urgent",
        "symptoms": ["chest_pain"]
    }
    ecg_context = {
        "model_scores": {
            "NORM": 0.99,
            "MI": 0.01
        }
    }
    res = priority_engine.evaluate_priority(patient_context, ecg_context)
    assert res.priority == "urgent"


def test_routine_baseline():
    """Standard post-procedure patient with normal parameters returns routine."""
    patient_context = {
        "clinician_urgency": "routine",
        "symptoms": [],
        "days_since_angioplasty": 90,
        "stent_count": 0,
        "is_overdue_followup": False
    }
    res = priority_engine.evaluate_priority(patient_context)
    assert res.priority == "routine"
    assert len(res.reasons) > 0
