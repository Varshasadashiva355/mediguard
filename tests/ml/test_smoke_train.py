"""
Unit test: End-to-End CPU Smoke Training Pipeline
Runs a fast 2-epoch training run on a small synthetic batch of 12-lead ECGs.
Guarantees the complete PyTorch training, loss calculation, evaluation,
and checkpointing loop executes without syntax or runtime errors on CPU.
"""

import os
import argparse
import tempfile
import yaml
from pathlib import Path
import pytest
import torch

from ml.train import run_training
from ml.evaluate import run_evaluation


def test_cpu_smoke_train_and_evaluate(tmp_path):
    """Run 2 epochs of synthetic training on CPU and verify checkpoint creation."""
    config_file = tmp_path / "test_config.yaml"
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = tmp_path / "raw_ptbxl"
    proc_dir = tmp_path / "processed"

    config_data = {
        "data": {
            "raw_dir": str(raw_dir),
            "processed_dir": str(proc_dir),
            "sampling_rate": 100,
            "duration_sec": 10,
            "leads": ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"],
            "superclasses": ["NORM", "MI", "STTC", "CD", "HYP"],
            "min_likelihood": 50
        },
        "preprocessing": {
            "bandpass_low": 0.5,
            "bandpass_high": 40.0,
            "filter_order": 2,
            "apply_baseline_removal": True,
            "quality_thresholds": {
                "max_flatline_sec": 0.5,
                "max_clipping_ratio": 0.05,
                "max_noise_ratio": 0.25
            }
        },
        "model": {
            "name": "ResNet1D_MediGuard",
            "in_channels": 12,
            "num_classes": 5,
            "base_filters": 16,  # Small base filters for lightning fast test
            "kernel_size": 5,
            "dropout": 0.1,
            "version": "v1.0.0-smoke-test"
        },
        "training": {
            "seed": 42,
            "batch_size": 16,
            "epochs": 2,
            "learning_rate": 0.005,
            "weight_decay": 0.01,
            "pos_weight": True,
            "grad_clip": 1.0,
            "early_stopping_patience": 2,
            "scheduler": "cosine",
            "device": "cpu"
        },
        "checkpoints": {
            "save_dir": str(ckpt_dir),
            "best_name": "best_smoke_model.pt",
            "last_name": "last_smoke_model.pt",
            "metrics_file": "metrics.json"
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    cli_args = argparse.Namespace(
        epochs=2,
        batch_size=16,
        lr=0.005,
        seed=42,
        use_100hz=True,
        synthetic_run=True,
        quick=True
    )

    # 1. Run Smoke Training
    train_res = run_training(str(config_file), cli_args)

    assert os.path.exists(train_res["best_checkpoint"]), "best checkpoint was not created!"
    assert os.path.exists(train_res["last_checkpoint"]), "last checkpoint was not created!"
    assert len(train_res["history"]) == 2, "Expected 2 epochs in training history"

    # Verify checkpoint contents
    ckpt = torch.load(train_res["best_checkpoint"], map_location="cpu")
    assert "state_dict" in ckpt
    assert "means" in ckpt
    assert "stds" in ckpt
    assert ckpt["model_version"] == "v1.0.0-smoke-test"

    # 2. Run Evaluation on the generated checkpoint
    eval_metrics = run_evaluation(
        checkpoint_path=train_res["best_checkpoint"],
        data_dir=str(proc_dir),
        output_dir=str(ckpt_dir),
        use_synthetic_if_missing=True
    )

    assert "macro_auroc" in eval_metrics
    assert "macro_auprc" in eval_metrics
    assert "per_superclass_metrics" in eval_metrics
    assert os.path.exists(ckpt_dir / "metrics.json")
    assert os.path.exists(ckpt_dir / "roc_curves.png")
    assert os.path.exists(ckpt_dir / "confusion_matrices.png")
    assert os.path.exists(ckpt_dir / "reliability_calibration.png")
