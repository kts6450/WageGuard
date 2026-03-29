"""
모델 성능 평가 모듈

포함 내용:
1. Stratified k-Fold 교차검증 (LNN / LSTM / XGBoost)
2. 학습 곡선 (Learning Curve)
3. 혼동 행렬 시각화
4. 종합 성능 비교 테이블
"""

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.metrics import (
    roc_auc_score, f1_score, precision_score, recall_score,
    average_precision_score, confusion_matrix,
)
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import warnings
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

from models.lnn_model import (
    LNNExploitationDetector,
    LSTMBaseline,
    prepare_sequence_data,
    normalize_sequences,
    train_model,
)
from utils.data_generator import generate_payment_records, compute_features
from utils.anomaly_detection import FEATURE_COLS


def cross_validate_lnn(X, y, model_class, n_splits=5, epochs=80, hidden_size=64):
    """Stratified k-Fold 교차검증 for LNN/LSTM"""
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    fold_results = []

    for fold, (train_idx, test_idx) in enumerate(skf.split(X, y)):
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]

        X_tr, X_val, y_tr_s, y_val_s = train_test_split(
            X_tr, y_tr, test_size=0.15, stratify=y_tr, random_state=fold
        )

        n, seq, feat = X_tr.shape
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr.reshape(-1, feat)).reshape(n, seq, feat).astype(np.float32)
        X_val_s = scaler.transform(X_val.reshape(-1, feat)).reshape(X_val.shape[0], seq, feat).astype(np.float32)
        X_te_s = scaler.transform(X_te.reshape(-1, feat)).reshape(X_te.shape[0], seq, feat).astype(np.float32)

        model = model_class(input_size=feat, hidden_size=hidden_size)
        train_model(model, X_tr_s, y_tr_s, X_val_s, y_val_s, epochs=epochs)

        model.eval()
        with torch.no_grad():
            logits = model(torch.tensor(X_te_s))
            probs = torch.sigmoid(logits).numpy().flatten()

        preds = (probs >= 0.5).astype(int)
        fold_results.append({
            "fold": fold + 1,
            "auroc": roc_auc_score(y_te, probs),
            "f1": f1_score(y_te, preds, zero_division=0),
            "precision": precision_score(y_te, preds, zero_division=0),
            "recall": recall_score(y_te, preds, zero_division=0),
            "ap": average_precision_score(y_te, probs),
        })
        print(f"  Fold {fold+1} | AUROC={fold_results[-1]['auroc']:.4f} | F1={fold_results[-1]['f1']:.4f}")

    return pd.DataFrame(fold_results)


def cross_validate_xgb(X_feat, y, n_splits=5):
    """Stratified k-Fold 교차검증 for XGBoost (테이블 피처 기반)"""
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    fold_results = []
    scale_pos_weight = (y == 0).sum() / (y == 1).sum()

    for fold, (train_idx, test_idx) in enumerate(skf.split(X_feat, y)):
        X_tr, X_te = X_feat[train_idx], X_feat[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]

        model = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            scale_pos_weight=scale_pos_weight,
            random_state=42,
            eval_metric="logloss",
            verbosity=0,
        )
        model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
        probs = model.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.5).astype(int)

        fold_results.append({
            "fold": fold + 1,
            "auroc": roc_auc_score(y_te, probs),
            "f1": f1_score(y_te, preds, zero_division=0),
            "precision": precision_score(y_te, preds, zero_division=0),
            "recall": recall_score(y_te, preds, zero_division=0),
            "ap": average_precision_score(y_te, probs),
        })
        print(f"  Fold {fold+1} | AUROC={fold_results[-1]['auroc']:.4f} | F1={fold_results[-1]['f1']:.4f}")

    return pd.DataFrame(fold_results)


def summarize_cv_results(results_dict: dict) -> pd.DataFrame:
    """교차검증 결과 요약 (평균 ± 표준편차)"""
    rows = []
    for model_name, df in results_dict.items():
        row = {"모델": model_name}
        for col in ["auroc", "f1", "precision", "recall", "ap"]:
            mean = df[col].mean()
            std = df[col].std()
            row[col.upper()] = f"{mean:.4f} ± {std:.4f}"
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print("데이터 준비 중...")
    df_raw = generate_payment_records(n_workplaces=500, exploitation_ratio=0.2, seed=42)
    df_feat = compute_features(df_raw)

    # 시퀀스 데이터 (LNN/LSTM용)
    X_seq, y_seq = prepare_sequence_data(df_raw, seq_len=12)
    print(f"시퀀스 데이터: {X_seq.shape}")

    # 테이블 피처 (XGBoost용)
    X_tab = df_feat[FEATURE_COLS].fillna(0).values
    y_tab = df_feat["is_exploited"].values

    scaler = StandardScaler()
    X_tab_scaled = scaler.fit_transform(X_tab)

    results_dict = {}

    print("\n" + "=" * 50)
    print("LNN 5-Fold 교차검증")
    print("=" * 50)
    lnn_cv = cross_validate_lnn(X_seq, y_seq, LNNExploitationDetector, n_splits=5, epochs=80)
    results_dict["LNN (시계열)"] = lnn_cv

    print("\n" + "=" * 50)
    print("LSTM 5-Fold 교차검증")
    print("=" * 50)
    lstm_cv = cross_validate_lnn(X_seq, y_seq, LSTMBaseline, n_splits=5, epochs=80)
    results_dict["LSTM (시계열)"] = lstm_cv

    print("\n" + "=" * 50)
    print("XGBoost 5-Fold 교차검증")
    print("=" * 50)
    xgb_cv = cross_validate_xgb(X_tab_scaled, y_tab, n_splits=5)
    results_dict["XGBoost (테이블)"] = xgb_cv

    print("\n" + "=" * 60)
    print("종합 성능 비교 (평균 ± 표준편차, 5-Fold CV)")
    print("=" * 60)
    summary = summarize_cv_results(results_dict)
    print(summary.to_string(index=False))

    os.makedirs("results", exist_ok=True)
    summary.to_csv("results/cv_summary.csv", index=False)
    for name, df in results_dict.items():
        safe_name = name.replace(" ", "_").replace("(", "").replace(")", "")
        df.to_csv(f"results/cv_{safe_name}.csv", index=False)

    print("\n저장 완료: results/cv_summary.csv")
