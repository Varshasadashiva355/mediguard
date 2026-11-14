"""
Unit tests for 12-lead ECG Signal Preprocessing & Signal Quality
Verifies fixed lead order, Butterworth band-pass filter (0.5-40Hz),
ECGStandardizer (fitted strictly on train fold), and signal quality assessment.
"""

import numpy as np
import pytest

from ml.preprocessing import (
    enforce_lead_order,
    butter_bandpass_filter,
    assess_signal_quality,
    standardize_signal_length,
    ECGStandardizer,
    apply_training_augmentations,
    STANDARD_LEADS
)


def test_enforce_lead_order():
    """Verify standard clinical lead reordering across diverse lead namings."""
    # Custom permuted order
    permuted_leads = ["V6", "V5", "V4", "V3", "V2", "V1", "aVF", "aVL", "aVR", "III", "II", "I"]
    dummy_signal = np.arange(12).reshape(12, 1) * np.ones((1, 500))

    ordered = enforce_lead_order(dummy_signal, permuted_leads)
    assert ordered.shape == (12, 500)

    # In the original, Lead I was at index 11. In ordered, Lead I must be at index 0.
    np.testing.assert_array_equal(ordered[0, :], dummy_signal[11, :])
    # Lead V6 was at index 0. In ordered, Lead V6 must be at index 11.
    np.testing.assert_array_equal(ordered[11, :], dummy_signal[0, :])


def test_butter_bandpass_filter():
    """Bandpass filter removes DC baseline wander (0 Hz) while preserving cardiac frequencies."""
    t = np.linspace(0, 10, 1000)
    fs = 100.0
    # DC baseline wander (0.1 Hz) + Cardiac wave (1.5 Hz)
    dc_drift = np.sin(2 * np.pi * 0.05 * t) * 2.0
    cardiac = np.sin(2 * np.pi * 1.5 * t) * 1.0
    sig = np.tile(dc_drift + cardiac, (12, 1)).astype(np.float32)

    filtered = butter_bandpass_filter(sig, lowcut=0.5, highcut=40.0, fs=fs, order=2)
    assert filtered.shape == (12, 1000)
    # The slow DC drift variance should be dramatically reduced
    assert np.std(filtered[0, :]) < np.std(sig[0, :])


def test_standardize_signal_length():
    """Verify padding of short signals and center cropping of long signals."""
    short_sig = np.ones((12, 800))
    padded = standardize_signal_length(short_sig, target_length=1000)
    assert padded.shape == (12, 1000)
    assert padded[0, 0] == 0.0  # Zero-padded at edge

    long_sig = np.ones((12, 1200))
    cropped = standardize_signal_length(long_sig, target_length=1000)
    assert cropped.shape == (12, 1000)


def test_assess_signal_quality_flatline_and_clipping():
    """Quality metric properly flags disconnected/flatlined leads and amplifier saturation."""
    # 1. Normal clean signal
    clean_sig = np.random.normal(0, 0.5, (12, 1000)).astype(np.float32)
    q_clean = assess_signal_quality(clean_sig, fs=100.0)
    assert q_clean["rating"] in ["good", "acceptable"]
    assert q_clean["is_acceptable"] is True
    assert q_clean["flatline_leads"] == 0

    # 2. Flatlined signal (4 dead leads)
    flat_sig = clean_sig.copy()
    flat_sig[0:4, :] = 0.0
    q_flat = assess_signal_quality(flat_sig, fs=100.0)
    assert q_flat["flatline_leads"] == 4
    assert q_flat["overall_quality"] < q_clean["overall_quality"]

    # 3. Saturated / clipping signal (> 5 mV)
    clip_sig = clean_sig.copy()
    clip_sig[:, 100:200] = 8.0  # Saturated beyond clinical bounds
    q_clip = assess_signal_quality(clip_sig, fs=100.0)
    assert q_clip["clipping_ratio"] > 0.0


def test_ecg_standardizer_train_only(tmp_path):
    """Verify train-only standardizer serialization and transform."""
    train_signals = [np.random.normal(1.0, 2.0, (12, 500)).astype(np.float32) for _ in range(10)]
    standardizer = ECGStandardizer().fit(train_signals)

    assert standardizer.means.shape == (12, 1)
    assert standardizer.stds.shape == (12, 1)
    assert np.all(standardizer.stds > 0.0)

    # Save and reload
    save_file = str(tmp_path / "standardizer.json")
    standardizer.save(save_file)
    loaded = ECGStandardizer.load(save_file)

    np.testing.assert_allclose(standardizer.means, loaded.means, rtol=1e-5)
    np.testing.assert_allclose(standardizer.stds, loaded.stds, rtol=1e-5)

    # Verify transform normalizes data close to mean 0, std 1
    test_sig = np.random.normal(1.0, 2.0, (12, 500)).astype(np.float32)
    normed = loaded.transform(test_sig)
    assert np.abs(np.mean(normed)) < 0.5
