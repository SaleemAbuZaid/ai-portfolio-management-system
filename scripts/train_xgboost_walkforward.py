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
import os
import sys
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import TimeSeriesSplit
import matplotlib.pyplot as plt
import seaborn as sns
import json
from datetime import datetime

# Set paths
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT_DIR, "data", "training", "market_training_long.parquet")
MODELS_DIR = os.path.join(ROOT_DIR, "backend", "app", "services", "ai_engine", "models")
ARTIFACTS_DIR = os.path.join(ROOT_DIR, "data", "training", "artifacts")

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

def load_data():
    if not os.path.exists(DATA_PATH):
        print(f"Error: Dataset not found at {DATA_PATH}")
        sys.exit(1)
    
    print(f"Loading dataset from {DATA_PATH}...")
    df = pd.read_parquet(DATA_PATH)
    print(f"Loaded {len(df)} rows.")
    return df

def preprocess_data(df):
    print("Preprocessing data & engineering features...")
    df_clean = df.copy()
    
    # 1. Normalized Gaps (%)
    for period in [5, 10, 20, 50]:
        sma_col = f'sma_{period}'
        if sma_col in df_clean.columns:
            df_clean[f'sma_{period}_gap_pct'] = (df_clean['close'] / df_clean[sma_col]) - 1.0
        else:
            df_clean[f'sma_{period}_gap_pct'] = 0.0

    for period in [10, 20]:
        ema_col = f'ema_{period}'
        if ema_col in df_clean.columns:
            df_clean[f'ema_{period}_gap_pct'] = (df_clean['close'] / df_clean[ema_col]) - 1.0
        else:
            df_clean[f'ema_{period}_gap_pct'] = 0.0

    # 2. MACD % and ATR %
    if 'macd' in df_clean.columns:
        df_clean['macd_pct'] = df_clean['macd'] / df_clean['close']
    else:
        df_clean['macd_pct'] = 0.0
        
    # 3. Volatility
    if 'volatility_10' not in df_clean.columns:
        df_clean['volatility_10'] = df_clean['return_1'].rolling(window=10).std()
    if 'volatility_20' not in df_clean.columns:
        df_clean['volatility_20'] = df_clean['return_1'].rolling(window=20).std()

    # 4. Enforce numeric columns
    numeric_features = [
        'return_1', 'return_3', 'return_5', 'return_10', 'return_20',
        'sma_5_gap_pct', 'sma_10_gap_pct', 'sma_20_gap_pct', 'sma_50_gap_pct',
        'ema_10_gap_pct', 'ema_20_gap_pct', 'rsi_14', 'macd_pct',
        'volatility_10', 'volatility_20', 'close_zscore_20', 'volume_zscore_20',
        'finbert_score'
    ]
    
    for col in numeric_features:
        if col not in df_clean.columns:
            df_clean[col] = 0.0
        df_clean[col] = df_clean[col].fillna(0.0)

    # 5. Categorical One-Hot (Symbol & Asset Type)
    # Get symbols
    symbols = df_clean['symbol'].unique()
    asset_types = df_clean['asset_type'].unique() if 'asset_type' in df_clean.columns else ['UNKNOWN']
    
    df_clean = pd.get_dummies(df_clean, columns=['symbol'], prefix='sym')
    if 'asset_type' in df_clean.columns:
        df_clean = pd.get_dummies(df_clean, columns=['asset_type'], prefix='type')
    
    # Update feature list to include dummies
    final_feature_cols = numeric_features + [col for col in df_clean.columns if col.startswith('sym_') or col.startswith('type_')]
    
    target_col = 'target_direction'
    # Drop NaNs for training
    df_clean = df_clean.dropna(subset=[target_col]).copy()
    
    # Map target_direction (-1, 0, 1) -> (0, 1, 2)
    target_map = {-1: 0, 0: 1, 1: 2}
    df_clean['target'] = df_clean[target_col].map(target_map)
    
    # Binary Target: 1 if Bullish (1), else 0
    df_clean['binary_target'] = (df_clean[target_col] == 1).astype(int)
    
    # Sort by time
    df_clean = df_clean.sort_values(by=['timestamp'])
    
    print(f"Final Features ({len(final_feature_cols)}): {final_feature_cols[:5]}...")
    return df_clean, final_feature_cols

def calculate_baselines(df):
    print("Calculating baselines...")
    majority_class = df['target'].mode()[0]
    majority_acc = (df['target'] == majority_class).mean()
    
    # Momentum Baseline
    momentum_preds = np.where(df['return_1'] > 0, 2, np.where(df['return_1'] < 0, 0, 1))
    momentum_acc = accuracy_score(df['target'], momentum_preds)
    
    # Binary Baselines
    binary_majority_class = df['binary_target'].mode()[0]
    binary_majority_acc = (df['binary_target'] == binary_majority_class).mean()
    binary_momentum_preds = (df['return_1'] > 0).astype(int)
    binary_momentum_acc = accuracy_score(df['binary_target'], binary_momentum_preds)
    
    return {
        "majority_class": float(majority_acc),
        "random_walk": 1.0 / 3.0,
        "momentum": float(momentum_acc),
        "binary_majority_class": float(binary_majority_acc),
        "binary_momentum": float(binary_momentum_acc)
    }

def walk_forward_validation(df, feature_cols, splits=5):
    print(f"\nStarting Walk-Forward Validation ({splits} splits)...")
    tscv = TimeSeriesSplit(n_splits=splits)
    X = df[feature_cols].values
    
    # Targets
    y_multi = df['target'].values
    y_binary = df['binary_target'].values
    
    results_multi = []
    results_binary = []
    
    for train_index, test_index in tscv.split(X):
        X_train, X_test = X[train_index], X[test_index]
        
        # 3-Class
        y_train_multi, y_test_multi = y_multi[train_index], y_multi[test_index]
        model_multi = xgb.XGBClassifier(
            objective='multi:softprob', num_class=3, eval_metric='mlogloss',
            n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42, n_jobs=-1
        )
        model_multi.fit(X_train, y_train_multi)
        preds_multi = model_multi.predict(X_test)
        acc_multi = accuracy_score(y_test_multi, preds_multi)
        precision_m, recall_m, f1_m, _ = precision_recall_fscore_support(y_test_multi, preds_multi, average='macro', zero_division=0)
        results_multi.append({
            'accuracy': acc_multi, 'macro_f1': f1_m, 'precision_macro': precision_m, 'recall_macro': recall_m,
            'y_test': y_test_multi, 'preds': preds_multi
        })
        
        # Binary
        y_train_bin, y_test_bin = y_binary[train_index], y_binary[test_index]
        model_bin = xgb.XGBClassifier(
            objective='binary:logistic', eval_metric='logloss',
            n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42, n_jobs=-1
        )
        model_bin.fit(X_train, y_train_bin)
        preds_bin = model_bin.predict(X_test)
        
        # Convert probabilities to binary predictions
        preds_bin_class = (preds_bin > 0.5).astype(int)
        acc_bin = accuracy_score(y_test_bin, preds_bin_class)
        precision_b, recall_b, f1_b, _ = precision_recall_fscore_support(y_test_bin, preds_bin_class, average='macro', zero_division=0)
        results_binary.append({
            'accuracy': acc_bin, 'macro_f1': f1_b, 'precision_macro': precision_b, 'recall_macro': recall_b,
            'y_test': y_test_bin, 'preds': preds_bin_class
        })
        
    # Final Models
    print("Training final models on full history...")
    final_model_multi = xgb.XGBClassifier(
        objective='multi:softprob', num_class=3, n_estimators=150, max_depth=6, learning_rate=0.05, random_state=42, n_jobs=-1
    )
    final_model_multi.fit(X, y_multi)
    
    final_model_binary = xgb.XGBClassifier(
        objective='binary:logistic', n_estimators=150, max_depth=6, learning_rate=0.05, random_state=42, n_jobs=-1
    )
    final_model_binary.fit(X, y_binary)
    
    return final_model_multi, final_model_binary, results_multi, results_binary

def generate_artifacts(model_multi, model_bin, results_multi, results_bin, feature_cols, baselines, df):
    print("Saving detailed artifacts...")
    accs_m = [r['accuracy'] for r in results_multi]
    avg_acc_m = float(np.mean(accs_m))
    
    accs_b = [r['accuracy'] for r in results_bin]
    avg_acc_b = float(np.mean(accs_b))
    
    avg_f1_m = float(np.mean([r['macro_f1'] for r in results_multi]))
    avg_prec_m = float(np.mean([r['precision_macro'] for r in results_multi]))
    avg_rec_m = float(np.mean([r['recall_macro'] for r in results_multi]))
    
    avg_f1_b = float(np.mean([r['macro_f1'] for r in results_bin]))
    avg_prec_b = float(np.mean([r['precision_macro'] for r in results_bin]))
    avg_rec_b = float(np.mean([r['recall_macro'] for r in results_bin]))
    
    # Main Metrics JSON
    report = {
        "model_name": "XGBoost Apex Classifier",
        "trained_at": datetime.now().isoformat(),
        "training_rows": len(df),
        "unique_assets": int(df.columns.str.startswith('sym_').sum()),
        "average_accuracy": avg_acc_m,
        "macro_f1": avg_f1_m,
        "precision_macro": avg_prec_m,
        "recall_macro": avg_rec_m,
        "split_accuracies": [float(a) for a in accs_m],
        "baselines": baselines,
        "features": feature_cols,
        "baseline_pass": avg_acc_m > baselines['majority_class'],
        "evaluation_method": "TimeSeriesSplit Walk-Forward",
        "honest_model_assessment": "XGBoost did not outperform the majority baseline; it is used as one weak signal inside a multi-signal recommendation engine." if avg_acc_m <= baselines['majority_class'] else "XGBoost slightly outperformed the majority baseline; it provides a predictive signal within the broader pipeline."
    }
    
    with open(os.path.join(ARTIFACTS_DIR, 'xgboost_metrics.json'), 'w') as f:
        json.dump(report, f, indent=4)
        
    # Model Comparison JSON
    comparison_report = {
        "evaluation_method": "Walk-Forward Validation (5 Splits)",
        "baselines": {
            "3_class_majority": baselines['majority_class'],
            "3_class_momentum": baselines['momentum'],
            "binary_majority": baselines['binary_majority_class'],
            "binary_momentum": baselines['binary_momentum']
        },
        "xgboost_models": {
            "3_class": {
                "average_accuracy": avg_acc_m,
                "macro_f1": avg_f1_m,
                "precision_macro": avg_prec_m,
                "recall_macro": avg_rec_m,
                "beats_majority": avg_acc_m > baselines['majority_class'],
                "beats_momentum": avg_acc_m > baselines['momentum']
            },
            "binary_action": {
                "average_accuracy": avg_acc_b,
                "macro_f1": avg_f1_b,
                "precision_macro": avg_prec_b,
                "recall_macro": avg_rec_b,
                "beats_majority": avg_acc_b > baselines['binary_majority_class'],
                "beats_momentum": avg_acc_b > baselines['binary_momentum']
            }
        },
        "conclusion": "The models provide honest signals. They are combined with FinBERT and other components in production to form a robust multi-factor recommendation."
    }
    
    with open(os.path.join(ARTIFACTS_DIR, 'xgboost_model_comparison.json'), 'w') as f:
        json.dump(comparison_report, f, indent=4)

    # Walk-Forward Report (Markdown)
    md_report = f"""# XGBoost Walk-Forward Performance Report
Generated: {datetime.now().isoformat()}

## Summary (3-Class)
- **Average Accuracy:** {avg_acc_m:.4f}
- **Majority Baseline:** {baselines['majority_class']:.4f}
- **Momentum Baseline:** {baselines['momentum']:.4f}

## Summary (Binary)
- **Average Accuracy:** {avg_acc_b:.4f}
- **Majority Baseline:** {baselines['binary_majority_class']:.4f}
- **Momentum Baseline:** {baselines['binary_momentum']:.4f}
"""
    with open(os.path.join(ARTIFACTS_DIR, 'xgboost_walkforward_report.md'), 'w') as f:
        f.write(md_report)

    # Save Models and Feature Columns for Inference Engine
    model_multi.save_model(os.path.join(MODELS_DIR, 'xgboost_apex.json'))
    model_bin.save_model(os.path.join(MODELS_DIR, 'xgboost_binary.json'))
    
    for target_dir in [MODELS_DIR, ARTIFACTS_DIR]:
        with open(os.path.join(target_dir, 'xgboost_feature_columns.json'), 'w') as f:
            json.dump(feature_cols, f, indent=4)

    print("All artifacts generated successfully.")

def main():
    df = load_data()
    df_clean, feature_cols = preprocess_data(df)
    baselines = calculate_baselines(df_clean)
    final_model_multi, final_model_bin, results_multi, results_bin = walk_forward_validation(df_clean, feature_cols)
    generate_artifacts(final_model_multi, final_model_bin, results_multi, results_bin, feature_cols, baselines, df_clean)

if __name__ == "__main__":
    main()
