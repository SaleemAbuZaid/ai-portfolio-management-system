"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Project source/configuration file supporting the APEX AI Portfolio Management System.
"""
import json
import os
import sys
import pandas as pd
from datetime import datetime, timezone
from loguru import logger

# Configuration
PROJECT_ROOT = os.getcwd()
ARTIFACT_DIR = os.path.join(PROJECT_ROOT, "data/training/artifacts")
MODEL_DIR = os.path.join(PROJECT_ROOT, "backend/app/services/ai_engine/models")
DATA_DIR = os.path.join(PROJECT_ROOT, "data/training")
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

FORBIDDEN_STRINGS = [
    "internal latency for proof",
    "Generating plausible baseline for defense",
    "150.0 # Default fallback",
    "internal_LATENCY",
    "internal_PRICE",
    "Synthetic Data",
    "PLACEHOLDER_SIGNAL",
    "85% Accuracy",
    "90% Accuracy",
    "return 0, 0.5", # Old internal fallback
    "Placeholder for NLP",
    "Placeholder",
    "hardcoded confidence",
    "current_price or 0.0"
]

REQUIRED_FILES = [
    os.path.join(DATA_DIR, "market_training_long.xlsx"),
    os.path.join(DATA_DIR, "market_training_long.csv"),
    os.path.join(DATA_DIR, "market_training_long.parquet"),
    os.path.join(DATA_DIR, "training_data_quality_report.md"),
    os.path.join(ARTIFACT_DIR, "xgboost_metrics.json"),
    os.path.join(ARTIFACT_DIR, "xgboost_feature_columns.json"),
    os.path.join(ARTIFACT_DIR, "lstm_metrics.json"),
    os.path.join(MODEL_DIR, "xgboost_apex.json"),
    os.path.join(MODEL_DIR, "xgboost_binary.json"),
    os.path.join(ARTIFACT_DIR, "xgboost_model_comparison.json"),
    os.path.join(MODEL_DIR, "xgboost_feature_columns.json")
]

SCAN_TARGETS = [
    os.path.join(BACKEND_DIR, "app/api/v1/ai.py"),
    os.path.join(BACKEND_DIR, "app/services/ai_engine/xgboost_inference.py"),
    os.path.join(BACKEND_DIR, "app/services/ai_engine/recommender.py"),
    os.path.join(BACKEND_DIR, "app/services/prediction_service.py"),
    os.path.join(BACKEND_DIR, "app/services/ai_engine/forecast_model.py")
]

def check_file_for_forbidden_strings(file_path):
    """Scan files for forbidden strings."""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            found = []
            for s in FORBIDDEN_STRINGS:
                if s.lower() in content.lower():
                    found.append(s)
            return found
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return []

def validate_data_artifacts():
    """Verify market data files are valid and contain real columns."""
    results = {}
    for f in [REQUIRED_FILES[0], REQUIRED_FILES[1], REQUIRED_FILES[2]]: # xlsx, csv, parquet
        if not os.path.exists(f):
            logger.error(f"Missing Data Artifact: {f}")
            results[os.path.basename(f)] = "MISSING"
            continue
            
        try:
            if f.endswith(".xlsx"):
                df = pd.read_excel(f, nrows=5)
            elif f.endswith(".csv"):
                df = pd.read_csv(f, nrows=5)
            elif f.endswith(".parquet"):
                df = pd.read_parquet(f)
                df = df.head(5)
            
            if "close" in df.columns and "symbol" in df.columns:
                logger.success(f"Data Verified: {os.path.basename(f)} (Columns: {len(df.columns)})")
                results[os.path.basename(f)] = "VALID"
            else:
                logger.error(f"Data Invalid: {os.path.basename(f)} - Missing core columns.")
                results[os.path.basename(f)] = "INVALID_COLUMNS"
        except Exception as e:
            logger.error(f"Error reading {f}: {e}")
            results[os.path.basename(f)] = f"ERROR: {str(e)}"
    return results

def validate_feature_consistency():
    """Check if backend and artifact feature columns match."""
    art_path = os.path.join(ARTIFACT_DIR, "xgboost_feature_columns.json")
    back_path = os.path.join(MODEL_DIR, "xgboost_feature_columns.json")
    
    if not os.path.exists(art_path) or not os.path.exists(back_path):
        logger.error("Feature column files missing for consistency check.")
        return False
        
    try:
        with open(art_path, 'r') as f:
            art_cols = json.load(f)
        with open(back_path, 'r') as f:
            back_cols = json.load(f)
            
        if art_cols == back_cols:
            logger.success("Feature Column Consistency: Backend matches Artifact.")
            return True
        else:
            logger.error("CRITICAL: Feature Column Mismatch between Backend and Artifact!")
            return False
    except Exception as e:
        logger.error(f"Consistency Check Error: {e}")
        return False

def main():
    logger.info("🚀 Starting FINAL ML TRUTH AUDIT for Graduation Defense...")
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "details": {
            "existence": {},
            "forbidden_scan": {},
            "data_validation": {},
            "consistency": False
        }
    }
    
    # 1. Existence Check
    for f in REQUIRED_FILES:
        exists = os.path.exists(f)
        report["details"]["existence"][os.path.basename(f)] = "EXISTS" if exists else "MISSING"
        if not exists:
            logger.error(f"MISSING: {f}")
            report["passed"] = False
        else:
            logger.success(f"FOUND: {os.path.basename(f)}")

    # 2. Forbidden String Scan
    for target in SCAN_TARGETS:
        found = check_file_for_forbidden_strings(target)
        if found:
            logger.error(f"FORBIDDEN STRINGS in {os.path.basename(target)}: {found}")
            report["details"]["forbidden_scan"][os.path.basename(target)] = found
            report["passed"] = False
        else:
            logger.success(f"TRUTH AUDIT PASSED: {os.path.basename(target)}")

    # 3. Data Integrity
    data_results = validate_data_artifacts()
    report["details"]["data_validation"] = data_results
    if any(v != "VALID" for v in data_results.values()):
        report["passed"] = False

    # 4. Consistency
    report["details"]["consistency"] = validate_feature_consistency()
    if not report["details"]["consistency"]:
        report["passed"] = False

    # 4.5. XGBoost Metrics Check
    metrics_path = os.path.join(ARTIFACT_DIR, "xgboost_metrics.json")
    comp_path = os.path.join(ARTIFACT_DIR, "xgboost_model_comparison.json")
    
    report["details"]["xgboost_metrics"] = {}
    if os.path.exists(metrics_path) and os.path.exists(comp_path):
        try:
            with open(metrics_path, "r") as f:
                metrics_data = json.load(f)
            with open(comp_path, "r") as f:
                comp_data = json.load(f)
            
            required_keys = ["macro_f1", "precision_macro", "recall_macro", "baseline_pass"]
            missing_keys = [k for k in required_keys if k not in metrics_data]
            
            binary_exists = "binary_action" in comp_data.get("xgboost_models", {})
            
            report["details"]["xgboost_metrics"] = {
                "metrics_complete": len(missing_keys) == 0,
                "missing_metrics": missing_keys,
                "binary_action_exists": binary_exists,
                "3_class_accuracy": metrics_data.get("average_accuracy", 0.0),
                "3_class_baseline_pass": metrics_data.get("baseline_pass", False),
                "binary_accuracy": comp_data.get("xgboost_models", {}).get("binary_action", {}).get("average_accuracy", 0.0),
                "binary_baseline_pass": comp_data.get("xgboost_models", {}).get("binary_action", {}).get("beats_majority", False),
                "majority_baseline": comp_data.get("baselines", {}).get("3_class_majority", 0.0),
                "honest_model_assessment": metrics_data.get("honest_model_assessment", "N/A")
            }
            if not report["details"]["xgboost_metrics"]["metrics_complete"] or not binary_exists:
                report["passed"] = False
        except Exception as e:
            logger.error(f"Failed to read xgboost metrics for validation: {e}")
            report["passed"] = False
    else:
        logger.error("XGBoost metrics or comparison file missing for validation.")
        report["passed"] = False

    # 5. LSTM check (12 required models)
    required_lstm_models = [
        "forecast_aapl.pth", "forecast_brent.pth", "forecast_btc_usd.pth",
        "forecast_eth_usd.pth", "forecast_eur_usd.pth", "forecast_gbp_usd.pth",
        "forecast_tsla.pth", "forecast_usd_jpy.pth", "forecast_usd_try.pth",
        "forecast_wti.pth", "forecast_xag_usd.pth", "forecast_xau_usd.pth"
    ]
    
    report["details"]["lstm_models"] = {}
    for lstm_file in required_lstm_models:
        f_path = os.path.join(MODEL_DIR, lstm_file)
        if os.path.exists(f_path):
            logger.success(f"FOUND LSTM: {lstm_file}")
            report["details"]["lstm_models"][lstm_file] = "EXISTS"
        else:
            logger.error(f"MISSING LSTM: {lstm_file}")
            report["details"]["lstm_models"][lstm_file] = "MISSING"
            report["passed"] = False

    # 6. Output Generation
    proof_dir = os.path.join(PROJECT_ROOT, "proofs", "final")
    os.makedirs(proof_dir, exist_ok=True)
    
    txt_path = os.path.join(proof_dir, "ml_artifact_validation.txt")
    json_path = os.path.join(proof_dir, "ml_artifact_validation.json")
    
    xgb_metrics = report["details"].get("xgboost_metrics", {})
    
    with open(txt_path, 'w') as f:
        f.write("=== APEX FINAL ML TRUTH AUDIT ===\n")
        f.write(f"Timestamp: {report['timestamp']}\n")
        f.write(f"OVERALL STATUS: {'TRUTH AUDIT PASSED' if report['passed'] else 'TRUTH AUDIT FAILED'}\n\n")
        f.write("=== ARTIFACT EXISTENCE ===\n")
        for k, v in report["details"]["existence"].items():
            f.write(f"- {k}: {v}\n")
        f.write("\n=== FORBIDDEN STRING SCAN ===\n")
        for k, v in report["details"]["forbidden_scan"].items():
            f.write(f"- {k}: {v}\n")
        f.write("\n=== FEATURE CONSISTENCY ===\n")
        f.write(f"- Backend matches Artifact: {report['details']['consistency']}\n")
        f.write("\n=== XGBOOST METRICS ===\n")
        f.write(f"- 3-Class Accuracy: {xgb_metrics.get('3_class_accuracy')}\n")
        f.write(f"- Majority Baseline: {xgb_metrics.get('majority_baseline')}\n")
        f.write(f"- 3-Class Baseline Pass: {xgb_metrics.get('3_class_baseline_pass')}\n")
        f.write(f"- Binary Model Accuracy: {xgb_metrics.get('binary_accuracy')}\n")
        f.write(f"- Binary Baseline Pass: {xgb_metrics.get('binary_baseline_pass')}\n")
        f.write(f"- Honest Assessment: {xgb_metrics.get('honest_model_assessment')}\n")
        f.write("\n=== EXACT LSTM MODEL CHECK ===\n")
        for k, v in report["details"]["lstm_models"].items():
            f.write(f"- {k}: {v}\n")
            
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=4)

    if report["passed"]:
        logger.success("✅ SYSTEM IS TRUTH-VALIDATED FOR FINAL DEFENSE.")
        sys.exit(0)
    else:
        logger.critical("❌ SYSTEM CONTAINS internal/MISSING DATA. DO NOT SUBMIT.")
        sys.exit(1)

if __name__ == "__main__":
    main()
