"""
Liquid Neural Network 모델
ncps 라이브러리의 CfC(Closed-form Continuous-time) 셀을 사용합니다.
불규칙한 시간 간격의 임금 지급 데이터를 그대로 처리합니다.
"""

import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from ncps.torch import CfC
from ncps.wirings import AutoNCP
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report,
    roc_auc_score,
    f1_score,
    confusion_matrix,
)
import os
import joblib


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
    "mean_time_gap",
    "std_time_gap",
    "n_months",
    "n_workers",
]


class LNNExploitationDetector(nn.Module):
    """
    Liquid Neural Network 기반 임금 착취 탐지 모델
    CfC(Closed-form Continuous-time) 셀을 사용합니다.
    불규칙 시간 간격은 추가 피처로 통합되어 입력됩니다.
    (time_gap 피처가 X의 마지막 열로 포함된다고 가정)
    BCEWithLogitsLoss 사용을 위해 sigmoid를 제거하고 logit을 반환합니다.
    """

    def __init__(self, input_size: int, hidden_size: int = 64, output_size: int = 1):
        super().__init__()

        wiring = AutoNCP(hidden_size, output_size)
        self.lnn = CfC(input_size, wiring, batch_first=True)

    def forward(self, x, timespans=None):
        # x: (batch, seq_len, features)
        output, _ = self.lnn(x)
        return output[:, -1, :]  # logit 반환 (sigmoid 없음)


class LSTMBaseline(nn.Module):
    """비교용 LSTM 베이스라인 모델 (logit 반환)"""

    def __init__(self, input_size: int, hidden_size: int = 64):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x, timespans=None):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


def normalize_sequences(X_train, X_val, X_test):
    """시퀀스 데이터 정규화 (피처별 StandardScaler 적용)"""
    n_train, seq_len, n_feat = X_train.shape
    scaler = StandardScaler()

    X_train_2d = X_train.reshape(-1, n_feat)
    X_val_2d = X_val.reshape(-1, n_feat)
    X_test_2d = X_test.reshape(-1, n_feat)

    X_train_scaled = scaler.fit_transform(X_train_2d).reshape(n_train, seq_len, n_feat)
    X_val_scaled = scaler.transform(X_val_2d).reshape(X_val.shape)
    X_test_scaled = scaler.transform(X_test_2d).reshape(X_test.shape)

    return X_train_scaled.astype(np.float32), X_val_scaled.astype(np.float32), X_test_scaled.astype(np.float32), scaler


def prepare_sequence_data(df_raw: pd.DataFrame, seq_len: int = 12):
    """
    원시 지급 기록을 시퀀스 형태로 변환
    불규칙 시간 간격(time_gap)을 피처로 포함시켜 LNN에 입력합니다.
    """
    sequences = []
    labels = []

    seq_features = [
        "payment_delay_days",
        "actual_wage",
        "contracted_wage",
        "deduction_amount",
        "overtime_hours",
        "actual_overtime_pay",
        "expected_overtime_pay",
    ]

    for wid, group in df_raw.groupby("workplace_id"):
        group = group.sort_values("payment_date").reset_index(drop=True)

        if len(group) < seq_len:
            continue

        feat = group[seq_features].values.astype(np.float32)

        # 불규칙 시간 간격을 피처로 통합 (LNN의 핵심 강점)
        timestamps = pd.to_datetime(group["payment_date"])
        time_gaps = timestamps.diff().dt.total_seconds().fillna(86400 * 30).values
        time_gaps = (time_gaps / (86400 * 30)).reshape(-1, 1).astype(np.float32)

        combined = np.concatenate([feat, time_gaps], axis=1)

        sequences.append(combined[:seq_len])
        labels.append(group["is_exploited"].iloc[0])

    X = np.array(sequences)
    y = np.array(labels)

    return X, y


def train_model(
    model: nn.Module,
    X_train, y_train,
    X_val, y_val,
    epochs: int = 100,
    lr: float = 1e-3,
):
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)

    # 클래스 불균형 보정: 착취 샘플에 가중치 부여
    pos_weight = torch.tensor([(y_train == 0).sum() / (y_train == 1).sum()], dtype=torch.float32)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    X_tr = torch.tensor(X_train, dtype=torch.float32)
    y_tr = torch.tensor(y_train, dtype=torch.float32).unsqueeze(-1)
    X_v = torch.tensor(X_val, dtype=torch.float32)
    y_v = torch.tensor(y_val, dtype=torch.float32).unsqueeze(-1)

    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    history = {"train_loss": [], "val_loss": [], "val_auc": []}

    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        preds = model(X_tr)
        loss = criterion(preds, y_tr)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        model.eval()
        with torch.no_grad():
            val_logits = model(X_v)
            val_loss = criterion(val_logits, y_v).item()
            val_prob = torch.sigmoid(val_logits).numpy().flatten()
            val_auc = roc_auc_score(y_val, val_prob)

        scheduler.step(val_loss)
        history["train_loss"].append(loss.item())
        history["val_loss"].append(val_loss)
        history["val_auc"].append(val_auc)

        if (epoch + 1) % 20 == 0:
            print(f"Epoch {epoch+1:3d} | train_loss={loss.item():.4f} | val_loss={val_loss:.4f} | val_AUC={val_auc:.4f}")

    return history


def evaluate_model(model: nn.Module, X_test, y_test, threshold: float = 0.5):
    model.eval()
    X_t = torch.tensor(X_test, dtype=torch.float32)

    with torch.no_grad():
        logits = model(X_t)
        preds_prob = torch.sigmoid(logits).numpy().flatten()

    preds_label = (preds_prob >= threshold).astype(int)
    auc = roc_auc_score(y_test, preds_prob)
    f1 = f1_score(y_test, preds_label, zero_division=0)

    print("\n분류 리포트:")
    print(classification_report(y_test, preds_label, target_names=["정상", "착취"], zero_division=0))
    print(f"AUROC: {auc:.4f}")
    print(f"F1-score (착취): {f1:.4f}")

    return {"auc": auc, "f1": f1, "preds_prob": preds_prob, "preds_label": preds_label}


if __name__ == "__main__":
    print("=" * 50)
    print("데이터 로드 중...")
    df_raw = pd.read_csv("data/synthetic/payment_records.csv", parse_dates=["payment_date"])
    print(f"총 {len(df_raw)}행 로드 완료")

    print("\n시퀀스 데이터 준비 중...")
    X, y = prepare_sequence_data(df_raw, seq_len=12)
    print(f"시퀀스 형태: {X.shape}, 레이블: {y.shape}")
    print(f"착취 비율: {y.mean()*100:.1f}%")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train, y_train, test_size=0.2, stratify=y_train, random_state=42
    )

    # 피처 정규화
    X_train, X_val, X_test, scaler = normalize_sequences(X_train, X_val, X_test)

    input_size = X.shape[2]

    print("\n" + "=" * 50)
    print("LNN 모델 학습 시작")
    print("=" * 50)
    lnn = LNNExploitationDetector(input_size=input_size, hidden_size=64)
    lnn_history = train_model(lnn, X_train, y_train, X_val, y_val, epochs=100)
    lnn_results = evaluate_model(lnn, X_test, y_test)

    print("\n" + "=" * 50)
    print("LSTM 베이스라인 학습 시작")
    print("=" * 50)
    lstm = LSTMBaseline(input_size=input_size, hidden_size=64)
    lstm_history = train_model(lstm, X_train, y_train, X_val, y_val, epochs=100)
    lstm_results = evaluate_model(lstm, X_test, y_test)

    print("\n" + "=" * 50)
    print("최종 성능 비교")
    print("=" * 50)
    print(f"{'모델':<10} {'AUROC':>8} {'F1-score':>10}")
    print("-" * 30)
    print(f"{'LNN':<10} {lnn_results['auc']:>8.4f} {lnn_results['f1']:>10.4f}")
    print(f"{'LSTM':<10} {lstm_results['auc']:>8.4f} {lstm_results['f1']:>10.4f}")

    os.makedirs("results", exist_ok=True)
    torch.save(lnn.state_dict(), "results/lnn_model.pt")
    joblib.dump(scaler, "results/scaler.pkl")
    print("\n모델 저장 완료: results/lnn_model.pt")
