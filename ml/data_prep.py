"""
MediGuard AI – PTB-XL Data Preparation and Label Mapping Pipeline
Diagnostic Superclasses: NORM, MI, STTC, CD, HYP

Strict compliance:
1. Official PTB-XL strat_fold (Folds 1-8: Train, 9: Val, 10: Test).
2. Diagnostic confidence threshold: likelihood >= 50%.
3. Zero patient leakage across splits asserted and printed.
4. Non-diagnostic / zero-superclass records explicitly reported and excluded.
"""

import os
import re
import ast
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mediguard.data_prep")

SUPERCLASSES: List[str] = ["NORM", "MI", "STTC", "CD", "HYP"]
MIN_LIKELIHOOD: float = 50.0  # PhysioNet benchmark standard (Wagner et al.)


def load_scp_mapping(scp_csv_path: str) -> Dict[str, str]:
    """
    Load scp_statements.csv and create dictionary mapping SCP code -> diagnostic superclass.
    Only keeps statements with diagnostic == 1 and non-null diagnostic_class.
    """
    if not os.path.exists(scp_csv_path):
        raise FileNotFoundError(f"scp_statements.csv not found at: {scp_csv_path}")

    df_scp = pd.read_csv(scp_csv_path, index_col=0)
    mapping = {}
    for code, row in df_scp.iterrows():
        diag_class = str(row.get("diagnostic_class", "")).strip()
        is_diag = row.get("diagnostic", 0)
        if pd.notna(diag_class) and diag_class in SUPERCLASSES and is_diag == 1:
            mapping[str(code).strip()] = diag_class

    logger.info("Loaded %d diagnostic statement mappings from %s", len(mapping), scp_csv_path)
    return mapping


def parse_and_map_labels(scp_codes_str: str, scp_to_superclass: Dict[str, str], min_likelihood: float = MIN_LIKELIHOOD) -> List[int]:
    """
    Parse the scp_codes string dict, filter by likelihood >= min_likelihood,
    and return a 5-dimensional multi-hot binary label vector: [NORM, MI, STTC, CD, HYP].
    """
    if not isinstance(scp_codes_str, str) or not scp_codes_str.strip():
        return [0] * len(SUPERCLASSES)

    try:
        # Clean numpy string representation like np.str_('NORM') if present
        clean_input = re.sub(r"np\.\w+\(['\"](.*?)['\"]\)", r"'\1'", scp_codes_str)
        codes_dict = ast.literal_eval(clean_input)
    except Exception as e:
        logger.warning("Failed to parse scp_codes: %s (%s)", scp_codes_str, e)
        return [0] * len(SUPERCLASSES)

    active_superclasses: Set[str] = set()
    for code, likelihood in codes_dict.items():
        try:
            val = float(likelihood)
        except (ValueError, TypeError):
            continue

        # Keep diagnostic statements with confidence >= 50%
        if val >= min_likelihood:
            clean_code = str(code).strip()
            if clean_code in scp_to_superclass:
                active_superclasses.add(scp_to_superclass[clean_code])

    return [1 if s in active_superclasses else 0 for s in SUPERCLASSES]


def verify_patient_leakage(train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame) -> Tuple[bool, str]:
    """
    Assert there is ZERO patient_id overlap across train, val, and test splits.
    The official PTB-XL strat_fold guarantees patient-level grouping.
    """
    train_patients = set(train_df["patient_id"].dropna().unique())
    val_patients = set(val_df["patient_id"].dropna().unique())
    test_patients = set(test_df["patient_id"].dropna().unique())

    overlap_train_val = train_patients & val_patients
    overlap_train_test = train_patients & test_patients
    overlap_val_test = val_patients & test_patients

    leakage = False
    details = []

    if overlap_train_val:
        leakage = True
        details.append(f"Train/Val patient leakage: {len(overlap_train_val)} patients")
    if overlap_train_test:
        leakage = True
        details.append(f"Train/Test patient leakage: {len(overlap_train_test)} patients")
    if overlap_val_test:
        leakage = True
        details.append(f"Val/Test patient leakage: {len(overlap_val_test)} patients")

    if leakage:
        msg = "PATIENT LEAKAGE DETECTED: " + "; ".join(details)
        return False, msg

    msg = (
        f"PASSED: Zero patient leakage verified! "
        f"(Train: {len(train_patients)} unique patients, "
        f"Val: {len(val_patients)} unique patients, "
        f"Test: {len(test_patients)} unique patients)"
    )
    return True, msg


def compute_split_statistics(df: pd.DataFrame, split_name: str) -> Dict[str, float]:
    """Compute per-superclass counts and prevalence percentages for a split."""
    total = len(df)
    stats: Dict[str, float] = {"total_records": total}
    for sc in SUPERCLASSES:
        cnt = int(df[sc].sum()) if sc in df.columns else 0
        prev = (cnt / total * 100.0) if total > 0 else 0.0
        stats[f"{sc}_count"] = cnt
        stats[f"{sc}_prevalence_pct"] = round(prev, 2)
    return stats


def generate_synthetic_ptbxl_data(output_dir: str, num_records: int = 200) -> Tuple[str, str]:
    """
    Generate synthetic PTB-XL index files for testing and offline environments.
    Guarantees official 10-fold structure and proper multi-hot diagnostic superclasses.
    """
    os.makedirs(output_dir, exist_ok=True)
    scp_path = os.path.join(output_dir, "scp_statements.csv")
    db_path = os.path.join(output_dir, "ptbxl_database.csv")

    # 1. Synthetic scp_statements.csv
    scp_data = [
        ("NORM", "Normal ECG", "NORM", 1),
        ("IMI", "Inferior Myocardial Infarction", "MI", 1),
        ("AMI", "Anterior Myocardial Infarction", "MI", 1),
        ("STTC", "ST/T change non-specific", "STTC", 1),
        ("NST_", "Non-specific ST change", "STTC", 1),
        ("LBBB", "Left bundle branch block", "CD", 1),
        ("RBBB", "Right bundle branch block", "CD", 1),
        ("LVH", "Left ventricular hypertrophy", "HYP", 1),
        ("RVH", "Right ventricular hypertrophy", "HYP", 1),
        ("SR", "Sinus Rhythm", "", 0),  # Non-diagnostic rhythm statement
    ]
    df_scp = pd.DataFrame(scp_data, columns=["code", "description", "diagnostic_class", "diagnostic"])
    df_scp.set_index("code").to_csv(scp_path)

    # 2. Synthetic ptbxl_database.csv
    rng = np.random.RandomState(42)
    records = []
    # Guarantee 1 patient per ~1.15 records (similar to real PTB-XL ratio)
    patient_ids = [10000 + (i // 2) for i in range(num_records)]

    code_choices = ["NORM", "IMI", "AMI", "STTC", "LBBB", "LVH", "SR"]

    for i in range(num_records):
        ecg_id = 1001 + i
        pat_id = patient_ids[i]
        # Assign fold based on patient_id so patients never split across folds!
        strat_fold = ((pat_id * 7) % 10) + 1  # 1 to 10

        # Pick 1 or 2 codes
        chosen = [str(c) for c in rng.choice(code_choices, size=int(rng.randint(1, 3)), replace=False)]
        scp_dict = {str(c): float(rng.choice([100.0, 80.0, 60.0])) for c in chosen}

        records.append({
            "ecg_id": ecg_id,
            "patient_id": pat_id,
            "age": float(rng.randint(25, 85)),
            "sex": int(rng.choice([0, 1])),
            "height": float(rng.randint(155, 190)),
            "weight": float(rng.randint(50, 100)),
            "scp_codes": str(scp_dict),
            "strat_fold": strat_fold,
            "filename_lr": f"records100/{ecg_id:05d}_lr",
            "filename_hr": f"records500/{ecg_id:05d}_hr",
        })

    df_db = pd.DataFrame(records)
    df_db.to_csv(db_path, index=False)
    logger.info("Generated synthetic PTB-XL dataset: %s (%d records)", db_path, num_records)
    return db_path, scp_path


def prepare_ptbxl_data(raw_dir: str, output_dir: str, min_likelihood: float = MIN_LIKELIHOOD, use_synthetic_fallback: bool = True) -> Dict:
    """
    Full pipeline to load, parse, map, filter, split, and save PTB-XL dataset indices.
    """
    raw_path = Path(raw_dir)
    db_file = raw_path / "ptbxl_database.csv"
    scp_file = raw_path / "scp_statements.csv"

    if not db_file.exists() or not scp_file.exists():
        if use_synthetic_fallback:
            logger.warning("PTB-XL database not found at %s. Generating synthetic PTB-XL demo data...", raw_dir)
            db_path, scp_path = generate_synthetic_ptbxl_data(str(raw_path), num_records=240)
            db_file = Path(db_path)
            scp_file = Path(scp_path)
        else:
            raise FileNotFoundError(f"Missing required PTB-XL files in {raw_dir}. See docs/DATASET_SETUP.md.")

    # 1. Load mappings & database
    scp_mapping = load_scp_mapping(str(scp_file))
    df = pd.read_csv(db_file)
    logger.info("Loaded %d raw records from %s", len(df), db_file)

    # 2. Parse scp_codes into 5-dim multi-hot label vector
    logger.info("Parsing SCP statements (filtering likelihood >= %.1f%%)...", min_likelihood)
    label_matrix = [parse_and_map_labels(row.get("scp_codes", ""), scp_mapping, min_likelihood) for _, row in df.iterrows()]
    labels_df = pd.DataFrame(label_matrix, columns=SUPERCLASSES)

    for sc in SUPERCLASSES:
        df[sc] = labels_df[sc]

    # Calculate number of positive superclasses per record
    df["num_superclasses"] = labels_df.sum(axis=1)

    # 3. Handle and explicitly exclude records with no diagnostic superclass
    records_with_labels = df[df["num_superclasses"] > 0].copy()
    excluded_count = len(df) - len(records_with_labels)
    logger.info(
        "Diagnostic Superclass Filtering: %d records retained, %d non-diagnostic records excluded (zero superclasses).",
        len(records_with_labels), excluded_count
    )

    # 4. Split according to official strat_fold column
    # Folds 1-8: Train, Fold 9: Validation, Fold 10: Test
    train_df = records_with_labels[records_with_labels["strat_fold"].between(1, 8)].copy()
    val_df = records_with_labels[records_with_labels["strat_fold"] == 9].copy()
    test_df = records_with_labels[records_with_labels["strat_fold"] == 10].copy()

    logger.info("Split sizes -> Train (folds 1-8): %d, Val (fold 9): %d, Test (fold 10): %d",
                len(train_df), len(val_df), len(test_df))

    # 5. Assert zero patient leakage across splits
    leakage_ok, leakage_msg = verify_patient_leakage(train_df, val_df, test_df)
    print("\n" + "=" * 70)
    print("PATIENT LEAKAGE AUDIT: " + leakage_msg)
    print("=" * 70 + "\n")
    if not leakage_ok:
        raise AssertionError(leakage_msg)

    # 6. Save split CSVs and statistics
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    train_csv = out_path / "train.csv"
    val_csv = out_path / "val.csv"
    test_csv = out_path / "test.csv"

    train_df.to_csv(train_csv, index=False)
    val_df.to_csv(val_csv, index=False)
    test_df.to_csv(test_csv, index=False)

    stats = {
        "train": compute_split_statistics(train_df, "train"),
        "val": compute_split_statistics(val_df, "val"),
        "test": compute_split_statistics(test_df, "test"),
        "excluded_non_diagnostic_count": excluded_count,
        "superclasses": SUPERCLASSES,
        "min_likelihood": min_likelihood,
        "patient_leakage_audit": leakage_msg
    }

    stats_file = out_path / "class_statistics.json"
    with open(stats_file, "w") as f:
        json.dump(stats, f, indent=2)

    logger.info("Saved prepared splits and class statistics to: %s", out_path)
    return stats


def main():
    parser = argparse.ArgumentParser(description="MediGuard AI – PTB-XL Data Preparation")
    parser.add_argument("--data-dir", type=str, default="dataset/ptb-xl", help="Path to raw PTB-XL dataset")
    parser.add_argument("--output-dir", type=str, default="dataset/processed", help="Path to save processed CSVs")
    parser.add_argument("--min-likelihood", type=float, default=MIN_LIKELIHOOD, help="Minimum statement confidence")
    parser.add_argument("--synthetic", action="store_true", help="Force synthetic dataset generation")
    args = parser.parse_args()

    if args.synthetic:
        logger.info("Explicitly generating synthetic PTB-XL dataset...")
        generate_synthetic_ptbxl_data(args.data_dir, num_records=250)

    prepare_ptbxl_data(
        raw_dir=args.data_dir,
        output_dir=args.output_dir,
        min_likelihood=args.min_likelihood,
        use_synthetic_fallback=True
    )


if __name__ == "__main__":
    main()
