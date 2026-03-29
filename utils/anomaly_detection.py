"""
PyOD 기반 비지도 이상 탐지 앙상블 모듈

접근 방식:
- 비지도 학습: 착취 레이블 없이 이상 패턴을 탐지
- 앙상블: IsolationForest + LOF + COPOD + ECOD 조합
- 실제 현장에서는 레이블이 없으므로, 비지도 탐지가 핵심

사용 목적:
- LNN(지도학습)의 보조 탐지기로 활용
- 레이블 없는 새로운 사업장에 대한 이상 탐지
"""

import numpy as np
import pandas as pd
from pyod.models.iforest import IForest
from pyod.models.lof import LOF
from pyod.models.copod import COPOD
from pyod.models.ecod import ECOD
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, f1_score, classification_report
import warnings
warnings.filterwarnings("ignore")


FEATURE_COLS = [
    "mean_delay",
    "std_delay",
    "delay_trend",
    "mean_wage_ratio",
    "min_wage_ratio",
    "wage_trend",
    "mean_deduction_ratio",
    "max_deduction_ratio",
    "mean_overtime_ratio",
    "min_overtime_ratio",
    "n_months",
    "n_workers",
]


def prepare_features(df_feat: pd.DataFrame) -> tuple:
    """피처 정규화 및 준비"""
    X = df_feat[FEATURE_COLS].fillna(0).values
    y = df_feat["is_exploited"].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    return X_scaled, y, scaler


def build_ensemble(contamination: float = 0.2) -> dict:
    """
    4개 모델 앙상블 구성
    contamination: 예상 이상치 비율 (착취 사업장 비율과 동일하게 설정)
    """
    return {
        "IsolationForest": IForest(contamination=contamination, random_state=42, n_estimators=200),
        "LOF": LOF(contamination=contamination, n_neighbors=20),
        "COPOD": COPOD(contamination=contamination),
        "ECOD": ECOD(contamination=contamination),
    }


def run_ensemble(X: np.ndarray, y: np.ndarray, contamination: float = 0.2) -> pd.DataFrame:
    """
    앙상블 실행 및 결과 집계
    소프트 보팅: 각 모델의 이상 점수 평균
    """
    models = build_ensemble(contamination)
    scores = {}
    labels = {}
    results = []

    for name, model in models.items():
        model.fit(X)
        score = model.decision_scores_     # 높을수록 이상
        score_norm = (score - score.min()) / (score.max() - score.min() + 1e-9)
        pred = model.labels_               # 0: 정상, 1: 이상

        scores[name] = score_norm
        labels[name] = pred

        auc = roc_auc_score(y, score_norm)
        f1 = f1_score(y, pred, zero_division=0)
        results.append({"model": name, "auroc": round(auc, 4), "f1": round(f1, 4)})
        print(f"  {name:<20} AUROC={auc:.4f}  F1={f1:.4f}")

    # 앙상블: 4개 모델 점수 평균
    ensemble_score = np.mean(list(scores.values()), axis=0)
    threshold = np.percentile(ensemble_score, (1 - contamination) * 100)
    ensemble_pred = (ensemble_score >= threshold).astype(int)

    auc = roc_auc_score(y, ensemble_score)
    f1 = f1_score(y, ensemble_pred, zero_division=0)
    results.append({"model": "Ensemble (평균)", "auroc": round(auc, 4), "f1": round(f1, 4)})
    print(f"  {'Ensemble':<20} AUROC={auc:.4f}  F1={f1:.4f}")

    scores_df = pd.DataFrame(scores)
    scores_df["ensemble_score"] = ensemble_score
    scores_df["ensemble_pred"] = ensemble_pred
    scores_df["true_label"] = y

    return scores_df, pd.DataFrame(results)


def compare_with_supervised(
    supervised_scores: np.ndarray,
    unsupervised_scores: np.ndarray,
    y: np.ndarray,
) -> pd.DataFrame:
    """지도학습(LNN) vs 비지도학습(앙상블) 성능 비교"""
    results = []
    for name, scores in [("LNN (지도)", supervised_scores), ("PyOD Ensemble (비지도)", unsupervised_scores)]:
        auc = roc_auc_score(y, scores)
        pred = (scores >= np.percentile(scores, 80)).astype(int)
        f1 = f1_score(y, pred, zero_division=0)
        results.append({"방법": name, "AUROC": round(auc, 4), "F1": round(f1, 4), "레이블 필요": "O" if "LNN" in name else "X"})
    return pd.DataFrame(results)


if __name__ == "__main__":
    import sys, os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.data_generator import generate_payment_records, compute_features

    print("데이터 준비 중...")
    df_raw = generate_payment_records(n_workplaces=500, exploitation_ratio=0.2, seed=42)
    df_feat = compute_features(df_raw)

    X, y, scaler = prepare_features(df_feat)
    print(f"피처 형태: {X.shape}, 착취 비율: {y.mean()*100:.1f}%\n")

    print("=" * 50)
    print("PyOD 앙상블 이상 탐지 실행")
    print("=" * 50)
    scores_df, results_df = run_ensemble(X, y, contamination=0.2)

    print("\n최종 결과:")
    print(results_df.to_string(index=False))

    os.makedirs("data/processed", exist_ok=True)
    scores_df.to_csv("data/processed/anomaly_scores.csv", index=False)
    results_df.to_csv("results/pyod_results.csv", index=False)
    print("\n저장 완료")
