"""
Unit tests for MediGuard AI Data Preparation Pipeline
Verifies SCP statement mapping, likelihood thresholding (>= 50%),
multi-hot vector construction, and official PTB-XL split zero patient leakage.
"""

import os
import tempfile
import pandas as pd
import pytest

from ml.data_prep import (
    load_scp_mapping,
    parse_and_map_labels,
    verify_patient_leakage,
    compute_split_statistics,
    generate_synthetic_ptbxl_data,
    prepare_ptbxl_data,
    SUPERCLASSES
)


@pytest.fixture
def sample_scp_mapping():
    return {
        "NORM": "NORM",
        "IMI": "MI",
        "AMI": "MI",
        "STTC": "STTC",
        "LBBB": "CD",
        "LVH": "HYP"
    }


def test_parse_and_map_labels_threshold(sample_scp_mapping):
    """Verify that statements with likelihood >= 50% are mapped, and < 50% are excluded."""
    # NORM at 100%, IMI at 40% (below 50 threshold -> should NOT trigger MI)
    scp_str = "{'NORM': 100.0, 'IMI': 40.0}"
    labels = parse_and_map_labels(scp_str, sample_scp_mapping, min_likelihood=50.0)

    assert labels == [1, 0, 0, 0, 0], f"Expected only NORM, got {labels}"

    # Multiple conditions: IMI at 80% (MI=1) and STTC at 60% (STTC=1)
    scp_str2 = "{'IMI': 80.0, 'STTC': 60.0}"
    labels2 = parse_and_map_labels(scp_str2, sample_scp_mapping, min_likelihood=50.0)
    assert labels2 == [0, 1, 1, 0, 0], f"Expected MI and STTC, got {labels2}"


def test_parse_empty_or_malformed_scp(sample_scp_mapping):
    """Malformed or empty SCP strings return all zeros gracefully."""
    assert parse_and_map_labels("", sample_scp_mapping) == [0, 0, 0, 0, 0]
    assert parse_and_map_labels("invalid_dict", sample_scp_mapping) == [0, 0, 0, 0, 0]


def test_verify_patient_leakage_assertion():
    """Verify that patient leakage detection catches overlaps and passes disjoint splits."""
    # Disjoint splits: should PASS
    train_df = pd.DataFrame({"patient_id": [1, 2, 3, 4], "strat_fold": [1, 2, 3, 4]})
    val_df = pd.DataFrame({"patient_id": [5, 6], "strat_fold": [9, 9]})
    test_df = pd.DataFrame({"patient_id": [7, 8], "strat_fold": [10, 10]})

    is_ok, msg = verify_patient_leakage(train_df, val_df, test_df)
    assert is_ok is True
    assert "PASSED: Zero patient leakage verified" in msg

    # Leaking splits: patient 4 appears in both train and test
    leaking_test_df = pd.DataFrame({"patient_id": [4, 8], "strat_fold": [10, 10]})
    is_ok2, msg2 = verify_patient_leakage(train_df, val_df, leaking_test_df)
    assert is_ok2 is False
    assert "PATIENT LEAKAGE DETECTED" in msg2


def test_end_to_end_data_prep_synthetic(tmp_path):
    """Run full data_prep pipeline with synthetic dataset and verify output CSVs."""
    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "proc"

    generate_synthetic_ptbxl_data(str(raw_dir), num_records=100)
    stats = prepare_ptbxl_data(str(raw_dir), str(proc_dir), min_likelihood=50.0)

    assert (proc_dir / "train.csv").exists()
    assert (proc_dir / "val.csv").exists()
    assert (proc_dir / "test.csv").exists()
    assert (proc_dir / "class_statistics.json").exists()

    train_df = pd.read_csv(proc_dir / "train.csv")
    val_df = pd.read_csv(proc_dir / "val.csv")
    test_df = pd.read_csv(proc_dir / "test.csv")

    # Assert fold assignments
    assert train_df["strat_fold"].between(1, 8).all()
    assert (val_df["strat_fold"] == 9).all()
    assert (test_df["strat_fold"] == 10).all()

    # Zero patient leakage
    leakage_ok, _ = verify_patient_leakage(train_df, val_df, test_df)
    assert leakage_ok is True
