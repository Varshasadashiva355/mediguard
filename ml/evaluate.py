"""
MediGuard AI – 12-Lead ECG Model Evaluation and Calibration Reporting
Held-out Test Fold (Fold 10) Evaluation
Optimal Threshold Tuning on Validation Fold (Fold 9)
Computes AUROC, AUPRC, Precision, Recall, F1, Confusion Matrices, and Calibration Plots.

Non-Negotiable Rule 1 & 2: Output scores are strictly experimental decision-support scores,
NOT calibrated diagnostic probabilities.
"""

import os
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Headless backend
import matplotlib.pyplot as plt

import torch
from torch.utils.data import DataLoader
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_recall_fscore_support,
    confusion_matrix,
    roc_curve,
    precision_recall_curve
)
from sklearn.calibration import calibration_curve

from ml.model import ResNet1D_MediGuard, build_model, SUPERCLASSES
from ml.preprocessing import ECGStandardizer, STANDARD_LEADS
from ml.train import PTBXLDataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mediguard.evaluate")


def find_optimal_thresholds(y_true: np.ndarray, y_scores: np.ndarray) -> Dict[str, float]:
    """
    Tune per-superclass decision thresholds on the VALIDATION fold (Fold 9)
    by searching for the threshold that maximizes F1 score.
    """
    thresholds = {}
    candidate_thresholds = np.linspace(0.1, 0.9, 81)

    for i, sc in enumerate(SUPERCLASSES):
        y_t = y_true[:, i]
        y_s = y_scores[:, i]

        best_th = 0.5
        best_f1 = -1.0

        if len(np.unique(y_t)) > 1:
            for th in candidate_thresholds:
                preds = (y_s >= th).astype(int)
                _, _, f1, _ = precision_recall_fscore_support(y_t, preds, average="binary", zero_division=0)
                if f1 > best_f1:
                    best_f1 = f1
                    best_th = th

        thresholds[sc] = round(float(best_th), 3)

    logger.info("Validation-tuned optimal thresholds: %s", thresholds)
    return thresholds


def evaluate_test_set(
    model: torch.nn.Module,
    test_loader: DataLoader,
    optimal_thresholds: Dict[str, float],
    device: torch.device
) -> Tuple[Dict, np.ndarray, np.ndarray]:
    """
    Evaluate trained model on the held-out test fold (Fold 10).
    Computes per-label AUROC, AUPRC, Precision, Recall, F1, and 2x2 confusion matrices.
    """
    model.eval()
    all_targets = []
    all_scores = []

    with torch.no_grad():
        for signals, targets in test_loader:
            signals = signals.to(device)
            scores = model.predict_scores(signals)
            all_targets.append(targets.cpu().numpy())
            all_scores.append(scores.cpu().numpy())

    y_true = np.concatenate(all_targets, axis=0)
    y_scores = np.concatenate(all_scores, axis=0)

    metrics_per_label = {}
    valid_aurocs = []
    valid_auprcs = []
    valid_f1s = []

    for i, sc in enumerate(SUPERCLASSES):
        y_t = y_true[:, i]
        y_s = y_scores[:, i]
        th = optimal_thresholds.get(sc, 0.5)
        preds = (y_s >= th).astype(int)

        # AUROC & AUPRC
        if len(np.unique(y_t)) > 1:
            auc = float(roc_auc_score(y_t, y_s))
            auprc = float(average_precision_score(y_t, y_s))
        else:
            auc = 0.5
            auprc = float(np.mean(y_t))

        valid_aurocs.append(auc)
        valid_auprcs.append(auprc)

        prec, rec, f1, _ = precision_recall_fscore_support(y_t, preds, average="binary", zero_division=0)
        valid_f1s.append(float(f1))

        # 2x2 Confusion Matrix: [[TN, FP], [FN, TP]]
        cm = confusion_matrix(y_t, preds, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel()

        metrics_per_label[sc] = {
            "optimal_threshold": th,
            "auroc": round(auc, 4),
            "auprc": round(auprc, 4),
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
            "f1_score": round(float(f1), 4),
            "confusion_matrix": {
                "true_negative": int(tn),
                "false_positive": int(fp),
                "false_negative": int(fn),
                "true_positive": int(tp)
            }
        }

    macro_results = {
        "macro_auroc": round(float(np.mean(valid_aurocs)), 4),
        "macro_auprc": round(float(np.mean(valid_auprcs)), 4),
        "macro_f1": round(float(np.mean(valid_f1s)), 4),
        "test_sample_count": len(y_true),
        "per_superclass_metrics": metrics_per_label,
        "disclaimer": (
            "MANDATORY CLINICAL DISCLAIMER: Research prototype decision support only. "
            "Model scores are uncalibrated experimental scores, NOT clinical diagnoses."
        )
    }

    return macro_results, y_true, y_scores


def plot_and_save_visualizations(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    metrics: Dict,
    save_dir: Path
):
    """Generate Matplotlib plots: ROC curves, PR curves, Confusion Matrices, and Calibration."""
    save_dir.mkdir(parents=True, exist_ok=True)
    colors = ["#14B8A6", "#EF4444", "#3B82F6", "#8B5CF6", "#F59E0B"]

    # 1. ROC Curves
    plt.figure(figsize=(8, 6), dpi=150)
    for i, sc in enumerate(SUPERCLASSES):
        if len(np.unique(y_true[:, i])) > 1:
            fpr, tpr, _ = roc_curve(y_true[:, i], y_scores[:, i])
            auc = metrics["per_superclass_metrics"][sc]["auroc"]
            plt.plot(fpr, tpr, label=f"{sc} (AUROC = {auc:.3f})", color=colors[i], lw=2)
    plt.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.6)
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel("False Positive Rate (1 - Specificity)")
    plt.ylabel("True Positive Rate (Sensitivity)")
    plt.title(f"MediGuard AI – Held-Out Test Fold ROC Curves (Macro AUROC: {metrics['macro_auroc']:.3f})")
    plt.legend(loc="lower right")
    plt.grid(True, alpha=0.3)
    roc_path = save_dir / "roc_curves.png"
    plt.savefig(roc_path, bbox_inches="tight")
    plt.close()

    # 2. Confusion Matrices (5 Subplots)
    fig, axes = plt.subplots(1, 5, figsize=(18, 3.6), dpi=150)
    for i, sc in enumerate(SUPERCLASSES):
        cm_data = metrics["per_superclass_metrics"][sc]["confusion_matrix"]
        cm_arr = np.array([
            [cm_data["true_negative"], cm_data["false_positive"]],
            [cm_data["false_negative"], cm_data["true_positive"]]
        ])
        ax = axes[i]
        cax = ax.matshow(cm_arr, cmap="Blues", alpha=0.8)
        for (r, c), val in np.ndenumerate(cm_arr):
            ax.text(c, r, f"{val}", ha="center", va="center", color="black", fontsize=11, fontweight="bold")
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(["Neg", "Pos"])
        ax.set_yticklabels(["Neg", "Pos"])
        th = metrics["per_superclass_metrics"][sc]["optimal_threshold"]
        ax.set_title(f"{sc}\n(Th={th:.2f}, F1={metrics['per_superclass_metrics'][sc]['f1_score']:.2f})", fontsize=10)
        ax.set_xlabel("Predicted")
        if i == 0:
            ax.set_ylabel("Ground Truth")
    plt.suptitle("MediGuard AI – Test Fold Confusion Matrices", fontsize=13, y=1.05)
    plt.tight_layout()
    cm_path = save_dir / "confusion_matrices.png"
    plt.savefig(cm_path, bbox_inches="tight")
    plt.close()

    # 3. Reliability / Calibration Curves
    plt.figure(figsize=(8, 6), dpi=150)
    for i, sc in enumerate(SUPERCLASSES):
        if len(np.unique(y_true[:, i])) > 1:
            try:
                prob_true, prob_pred = calibration_curve(y_true[:, i], y_scores[:, i], n_bins=8, strategy="uniform")
                plt.plot(prob_pred, prob_true, marker="s", label=sc, color=colors[i], lw=2)
            except Exception:
                pass
    plt.plot([0, 1], [0, 1], "k--", label="Perfect Calibration (Diagonal)", lw=1.2)
    plt.xlabel("Mean Predicted Score (Sigmoid Output)")
    plt.ylabel("Fraction of True Positives")
    plt.title("Reliability / Calibration Curve (Test Fold)\n*Experimental model scores are uncalibrated unless temperature scaling is applied*")
    plt.legend(loc="upper left")
    plt.grid(True, alpha=0.3)
    cal_path = save_dir / "reliability_calibration.png"
    plt.savefig(cal_path, bbox_inches="tight")
    plt.close()

    logger.info("Saved evaluation charts to: %s", save_dir)


def run_evaluation(
    checkpoint_path: str = "saved_models/best_model.pt",
    data_dir: str = "dataset/processed",
    output_dir: str = "saved_models",
    use_synthetic_if_missing: bool = True
) -> Dict:
    """Full evaluation pipeline on validation and held-out test sets."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    save_path = Path(output_dir)

    # 1. Load Checkpoint or Initialize Demonstration Weights
    if os.path.exists(checkpoint_path):
        logger.info("Loading trained checkpoint from: %s", checkpoint_path)
        checkpoint = torch.load(checkpoint_path, map_location=device)
        model = build_model(checkpoint.get("config", {})).to(device)
        model.load_state_dict(checkpoint["state_dict"])
        model_version = checkpoint.get("model_version", "v1.0.0-ptbxl")
        standardizer = ECGStandardizer(means=checkpoint.get("means"), stds=checkpoint.get("stds"))
        is_demo = checkpoint.get("is_demonstration_data", False)
    else:
        if not use_synthetic_if_missing:
            raise FileNotFoundError(f"Checkpoint not found at: {checkpoint_path}")
        logger.warning("No checkpoint found at %s. Initializing model for demonstration evaluation.", checkpoint_path)
        model = build_model().to(device)
        model_version = "v1.0.0-ptbxl-DEMO"
        standardizer = ECGStandardizer()
        is_demo = True

    # 2. Load Validation & Test Splits
    val_csv = Path(data_dir) / "val.csv"
    test_csv = Path(data_dir) / "test.csv"

    if not val_csv.exists() or not test_csv.exists():
        from ml.data_prep import prepare_ptbxl_data
        prepare_ptbxl_data(raw_dir="dataset/ptb-xl", output_dir=data_dir, use_synthetic_fallback=True)

    val_df = pd.read_csv(val_csv)
    test_df = pd.read_csv(test_csv)

    val_dataset = PTBXLDataset(val_df, "dataset/ptb-xl", sampling_rate=100, standardizer=standardizer, is_training=False)
    test_dataset = PTBXLDataset(test_df, "dataset/ptb-xl", sampling_rate=100, standardizer=standardizer, is_training=False)

    val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False)

    # 3. Collect validation predictions for threshold tuning
    model.eval()
    val_targets = []
    val_scores = []
    with torch.no_grad():
        for sigs, tgts in val_loader:
            sigs = sigs.to(device)
            scs = model.predict_scores(sigs)
            val_targets.append(tgts.numpy())
            val_scores.append(scs.cpu().numpy())

    y_val_true = np.concatenate(val_targets, axis=0)
    y_val_scores = np.concatenate(val_scores, axis=0)
    optimal_thresholds = find_optimal_thresholds(y_val_true, y_val_scores)

    # 4. Evaluate on held-out test fold
    metrics, y_test_true, y_test_scores = evaluate_test_set(model, test_loader, optimal_thresholds, device)
    metrics["model_version"] = model_version
    metrics["is_demonstration_data"] = is_demo

    # 5. Save metrics.json and plots
    metrics_file = save_path / "metrics.json"
    with open(metrics_file, "w") as f:
        json.dump(metrics, f, indent=2)
    logger.info("Saved evaluation metrics to: %s", metrics_file)

    plot_and_save_visualizations(y_test_true, y_test_scores, metrics, save_path)

    # Print summary table
    print("\n" + "=" * 80)
    print(f"MEDIGUARD AI – TEST FOLD EVALUATION SUMMARY (Model: {model_version})")
    print(f"Macro AUROC: {metrics['macro_auroc']:.4f} | Macro AUPRC: {metrics['macro_auprc']:.4f} | Macro F1: {metrics['macro_f1']:.4f}")
    print("-" * 80)
    print(f"{'Superclass':<10} {'AUROC':<10} {'AUPRC':<10} {'Precision':<12} {'Recall':<10} {'F1':<10} {'Threshold':<10}")
    print("-" * 80)
    for sc in SUPERCLASSES:
        m = metrics["per_superclass_metrics"][sc]
        print(f"{sc:<10} {m['auroc']:<10.4f} {m['auprc']:<10.4f} {m['precision']:<12.4f} {m['recall']:<10.4f} {m['f1_score']:<10.4f} {m['optimal_threshold']:<10.2f}")
    print("=" * 80 + "\n")

    return metrics


def main():
    parser = argparse.ArgumentParser(description="MediGuard AI – 12-Lead ECG Model Evaluation")
    parser.add_argument("--checkpoint", type=str, default="saved_models/best_model.pt", help="Path to checkpoint")
    parser.add_argument("--data-dir", type=str, default="dataset/processed", help="Path to processed splits")
    parser.add_argument("--output-dir", type=str, default="saved_models", help="Directory to save metrics and plots")
    args = parser.parse_args()

    run_evaluation(args.checkpoint, args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
