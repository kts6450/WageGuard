"""
통합 학습 파이프라인

두 가지 접근법을 병렬로 학습·비교합니다:
  1. Cross-sectional (실제 데이터) → XGBoost
  2. Time-series (실제 분포로 보정된 합성 데이터) → LNN vs LSTM

결과를 JSON으로 저장하여 대시보드에서 사용합니다.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import torch
import joblib
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import roc_auc_score, f1_score, average_precision_score
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.real_data_processor import load_wage_survey, build_ml_features, get_real_distribution_stats
from utils.data_generator import generate_payment_records, compute_features
from models.lnn_model import (
    LNNExploitationDetector, LSTMBaseline,
    prepare_sequence_data, normalize_sequences, train_model, evaluate_model,
)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


# ────────────────────────────────────────────────
# 1. XGBoost (실제 데이터)
# ────────────────────────────────────────────────

def train_xgboost(df_feat: pd.DataFrame, n_splits: int = 5) -> dict:
    """Stratified K-Fold XGBoost"""
    label_col = "is_exploited"
    feature_cols = [c for c in df_feat.columns if c != label_col]

    X = df_feat[feature_cols].values.astype(np.float32)
    y = df_feat[label_col].values.astype(int)

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    fold_results = []

    for fold, (tr_idx, val_idx) in enumerate(skf.split(X, y)):
        X_tr, X_val = X[tr_idx], X[val_idx]
        y_tr, y_val = y[tr_idx], y[val_idx]

        scale_pos_weight = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
        model = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            scale_pos_weight=scale_pos_weight,
            eval_metric="auc",
            random_state=42,
            verbosity=0,
            use_label_encoder=False,
        )
        model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

        proba = model.predict_proba(X_val)[:, 1]
        pred = (proba >= 0.5).astype(int)

        fold_results.append({
            "fold": fold + 1,
            "auroc": roc_auc_score(y_val, proba),
            "f1": f1_score(y_val, pred, zero_division=0),
            "ap": average_precision_score(y_val, proba),
        })
        print(f"  XGB Fold {fold+1}: AUROC={fold_results[-1]['auroc']:.4f}  F1={fold_results[-1]['f1']:.4f}")

    # 마지막 fold 모델로 피처 중요도
    importance = dict(zip(feature_cols, model.feature_importances_))
    importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:15])

    summary = {
        "auroc_mean": np.mean([r["auroc"] for r in fold_results]),
        "auroc_std": np.std([r["auroc"] for r in fold_results]),
        "f1_mean": np.mean([r["f1"] for r in fold_results]),
        "f1_std": np.std([r["f1"] for r in fold_results]),
        "ap_mean": np.mean([r["ap"] for r in fold_results]),
        "folds": fold_results,
        "feature_importance": importance,
    }

    joblib.dump(model, os.path.join(RESULTS_DIR, "xgb_model.pkl"))
    print(f"\n  XGB 평균 AUROC: {summary['auroc_mean']:.4f} ± {summary['auroc_std']:.4f}")
    return summary


# ────────────────────────────────────────────────
# 2. LNN / LSTM (합성 시계열 데이터 - 실제 분포 보정)
# ────────────────────────────────────────────────

def train_sequence_models(real_stats: dict, n_workplaces: int = 2000, seq_len: int = 12) -> dict:
    """
    실제 분포로 보정된 합성 시계열 데이터로 LNN & LSTM 학습
    """
    print("\n합성 시계열 데이터 생성 중 (실제 분포 보정)...")

    # 실제 착취 비율로 exploitation_ratio 보정
    exploitation_ratio = min(real_stats.get("total_exploitation_rate", 0.2) * 3, 0.4)

    df_raw = generate_payment_records(
        n_workplaces=n_workplaces,
        exploitation_ratio=exploitation_ratio,
        seed=42,
    )
    print(f"  생성 완료: {len(df_raw):,}건 | 사업장: {n_workplaces}")

    X, y = prepare_sequence_data(df_raw, seq_len=seq_len)
    print(f"  시퀀스: {X.shape} | 착취 비율: {y.mean()*100:.1f}%")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train, y_train, test_size=0.2, stratify=y_train, random_state=42
    )
    X_train, X_val, X_test, scaler = normalize_sequences(X_train, X_val, X_test)
    joblib.dump(scaler, os.path.join(RESULTS_DIR, "scaler.pkl"))

    input_size = X.shape[2]
    results = {}

    for model_name, ModelClass in [("LNN", LNNExploitationDetector), ("LSTM", LSTMBaseline)]:
        print(f"\n{model_name} 학습 중...")
        model = ModelClass(input_size=input_size, hidden_size=64)
        train_model(model, X_train, y_train, X_val, y_val, epochs=100)
        metrics = evaluate_model(model, X_test, y_test)

        results[model_name] = {
            "auroc": float(metrics["auc"]),
            "f1": float(metrics["f1"]),
            "ap": float(average_precision_score(y_test, metrics["preds_prob"])),
        }

        torch.save(model.state_dict(), os.path.join(RESULTS_DIR, f"{model_name.lower()}_model.pt"))

    return results


# ────────────────────────────────────────────────
# 메인 파이프라인
# ────────────────────────────────────────────────

def run_pipeline(sample_frac: float = 0.05, quick: bool = False):
    """
    sample_frac: 고용형태별근로실태조사 샘플링 비율
    quick: True면 빠른 테스트 (소규모 합성 데이터)
    """
    print("=" * 60)
    print("임금 착취 탐지 통합 학습 파이프라인")
    print("=" * 60)

    # ── Step 1: 실제 데이터 로드 ──
    print("\n[Step 1] 실제 데이터 로드 중...")
    df_wage = load_wage_survey(sample_frac=sample_frac)
    real_stats = get_real_distribution_stats(df_wage)

    # ── Step 2: XGBoost (실제 데이터) ──
    print("\n[Step 2] XGBoost 학습 (실제 데이터)")
    df_feat = build_ml_features(df_wage, sample_size=30_000 if quick else 100_000)
    feat_cols = [c for c in df_feat.columns if c != "is_exploited"]
    xgb_results = train_xgboost(df_feat)

    # ── Step 3: LNN / LSTM (합성 시계열) ──
    print("\n[Step 3] LNN / LSTM 학습 (합성 시계열)")
    n_workplaces = 1000 if quick else 3000
    seq_results = train_sequence_models(real_stats, n_workplaces=n_workplaces)

    # ── Step 4: 결과 통합 저장 ──
    final_results = {
        "real_data_stats": {
            "total_records": int(len(df_wage)),
            "exploitation_rate": float(real_stats["total_exploitation_rate"]),
            "insurance_violation_rate": float(real_stats["insurance_violation_rate"]),
            "wage_violation_rate": float(real_stats["wage_violation_rate"]),
            "overtime_exploitation_rate": float(real_stats["overtime_exploitation_rate"]),
            "wage_mean": float(real_stats["wage_mean"]),
            "wage_p50": float(real_stats["wage_p50"]),
        },
        "model_performance": {
            "XGBoost (실제 데이터)": {
                "auroc": xgb_results["auroc_mean"],
                "auroc_std": xgb_results["auroc_std"],
                "f1": xgb_results["f1_mean"],
                "f1_std": xgb_results["f1_std"],
                "ap": xgb_results["ap_mean"],
                "data_type": "real",
            },
            "LNN (합성 시계열)": {
                "auroc": seq_results["LNN"]["auroc"],
                "f1": seq_results["LNN"]["f1"],
                "ap": seq_results["LNN"]["ap"],
                "data_type": "synthetic_calibrated",
            },
            "LSTM (합성 시계열)": {
                "auroc": seq_results["LSTM"]["auroc"],
                "f1": seq_results["LSTM"]["f1"],
                "ap": seq_results["LSTM"]["ap"],
                "data_type": "synthetic_calibrated",
            },
        },
        "feature_importance": xgb_results["feature_importance"],
    }

    def _to_python(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, dict): return {k: _to_python(v) for k, v in obj.items()}
        if isinstance(obj, list): return [_to_python(i) for i in obj]
        return obj

    final_results = _to_python(final_results)
    result_path = os.path.join(RESULTS_DIR, "pipeline_results.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("최종 모델 성능 비교")
    print("=" * 60)
    print(f"{'모델':<25} {'AUROC':>8} {'F1':>8} {'AP':>8}")
    print("-" * 55)
    for name, m in final_results["model_performance"].items():
        std = f"±{m['auroc_std']:.3f}" if "auroc_std" in m else ""
        print(f"{name:<25} {m['auroc']:>7.4f}{std:>7}  {m['f1']:>6.4f}  {m['ap']:>6.4f}")

    print(f"\n결과 저장: {result_path}")
    return final_results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="빠른 테스트 모드")
    parser.add_argument("--sample", type=float, default=0.05, help="데이터 샘플링 비율")
    args = parser.parse_args()

    run_pipeline(sample_frac=args.sample, quick=args.quick)
