"""
Unit tests for MediGuard AI Predict Engine
Enforces Rule 1, 2, 3, 4 compliance:
- Refuses incompatible inputs (3-lead signals, 2-second recordings) with clear errors.
- Never fabricates output (marks untyped models as DEMONSTRATION DATA).
- Validates 5 experimental model scores, quality metrics, and mandatory disclaimer.
"""

import numpy as np
import pytest

from ml.predict import ECGPredictor, load_model, predict, CLINICAL_DISCLAIMER
from ml.model import SUPERCLASSES


def test_predict_refuses_3_lead_signal():
    """Predict engine strictly refuses 3-lead signals (Rule 4: ML inference ONLY on digital 12-lead signals)."""
    predictor = load_model()
    three_lead_signal = np.random.normal(0, 1, (3, 1000)).astype(np.float32)

    with pytest.raises(ValueError, match="Incompatible ECG signal: expected 12 leads"):
        predictor.predict(three_lead_signal, sampling_rate=100.0)


def test_predict_refuses_short_2_second_signal():
    """Predict engine strictly refuses signals shorter than minimum required duration (5s)."""
    predictor = load_model()
    # 2 seconds at 100 Hz = 200 samples
    short_signal = np.random.normal(0, 1, (12, 200)).astype(np.float32)

    with pytest.raises(ValueError, match="recording too short"):
        predictor.predict(short_signal, sampling_rate=100.0)


def test_predict_refuses_all_zero_flatline():
    """Predict engine refuses signals where all 12 leads are zero."""
    predictor = load_model()
    flat_signal = np.zeros((12, 1000), dtype=np.float32)

    with pytest.raises(ValueError, match="all 12 leads are zero"):
        predictor.predict(flat_signal, sampling_rate=100.0)


def test_predict_valid_12_lead_inference():
    """Valid 12-lead signal returns 5 experimental model scores, quality, and disclaimer."""
    predictor = load_model()
    valid_signal = np.random.normal(0, 0.5, (12, 1000)).astype(np.float32)

    result = predictor.predict(valid_signal, sampling_rate=100.0)

    # Structure checks
    assert "scores" in result
    assert "signal_quality" in result
    assert "model_version" in result
    assert "is_demonstration_data" in result
    assert "disclaimer" in result

    # All 5 superclasses present
    for sc in SUPERCLASSES:
        assert sc in result["scores"]
        score = result["scores"][sc]
        assert 0.0 <= score <= 1.0, f"Score for {sc} out of bounds: {score}"

    # Signal quality structure
    assert result["signal_quality"]["rating"] in ["good", "acceptable", "poor"]
    assert 0.0 <= result["signal_quality"]["overall_quality"] <= 1.0

    # Mandatory disclaimer present
    assert CLINICAL_DISCLAIMER in result["disclaimer"]


def test_functional_predict_helper():
    """Verify one-line functional predict helper."""
    sig = np.random.normal(0, 0.5, (12, 1000)).astype(np.float32)
    res = predict(sig, sampling_rate=100.0)
    assert len(res["scores"]) == 5
    assert isinstance(res["is_demonstration_data"], bool)

    # When pointing to a non-existent checkpoint, DEMONSTRATION DATA mode is activated
    res_demo = predict(sig, sampling_rate=100.0, checkpoint_path="non_existent_model.pt")
    assert res_demo["is_demonstration_data"] is True
