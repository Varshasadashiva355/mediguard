"""
Unit tests for MediGuard AI ECG Waveform Analysis API
Verifies /api/ecg/analyze endpoint invoking the PyTorch ResNet-1D model.
"""

import pytest


def test_analyze_ecg_authenticated(client, cardio_token):
    """Cardiologist or clinician can execute 12-lead ECG model inference via REST API."""
    response = client.post(
        "/api/ecg/analyze",
        headers={"Authorization": f"Bearer {cardio_token}"},
        json={"sampling_rate": 100.0}
    )
    assert response.status_code == 200
    data = response.get_json()["data"]

    assert "scores" in data
    assert "signal_quality" in data
    assert "model_version" in data
    assert "disclaimer" in data

    scores = data["scores"]
    for sc in ["NORM", "MI", "STTC", "CD", "HYP"]:
        assert sc in scores
        assert 0.0 <= scores[sc] <= 1.0


def test_analyze_ecg_unauthorized(client):
    """Unauthenticated request to analyze ECG is rejected (401)."""
    response = client.post("/api/ecg/analyze", json={})
    assert response.status_code == 401
