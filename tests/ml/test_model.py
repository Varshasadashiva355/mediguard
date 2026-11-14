"""
Unit tests for MediGuard AI ResNet-1D Architecture
Verifies tensor forward pass shapes, parameter counts, and inference output bounds.
"""

import torch
import pytest

from ml.model import ResNet1D_MediGuard, build_model, get_model_summary, SUPERCLASSES


def test_model_instantiation():
    """Verify ResNet-1D initialization and parameter count."""
    model = build_model()
    summary = get_model_summary(model)

    assert summary["model_name"] == "ResNet1D_MediGuard"
    assert summary["trainable_params"] > 100_000
    assert len(SUPERCLASSES) == 5


def test_forward_pass_shape():
    """Verify raw logits output shape: (batch_size, 5)."""
    model = build_model()
    batch_size = 4
    seq_length = 1000  # 10s @ 100Hz
    x = torch.randn(batch_size, 12, seq_length)

    model.eval()
    with torch.no_grad():
        logits = model(x)

    assert logits.shape == (batch_size, 5)


def test_predict_scores_sigmoid_range():
    """Verify that predict_scores applies sigmoid and bounds outputs in [0.0, 1.0]."""
    model = build_model()
    x = torch.randn(2, 12, 1000)

    scores = model.predict_scores(x)
    assert scores.shape == (2, 5)
    assert (scores >= 0.0).all() and (scores <= 1.0).all()


def test_invalid_input_dimensions():
    """Verify that non-12-lead inputs raise a clear ValueError."""
    model = build_model()
    # 3 leads instead of 12
    x_bad_leads = torch.randn(2, 3, 1000)
    with pytest.raises(ValueError, match="Expected input shape"):
        model(x_bad_leads)
