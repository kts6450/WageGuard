"""
LNN vs LSTM 조기 탐지 비교 실험

핵심 주장: LNN(CfC)은 불규칙 시간 간격 데이터에서
           LSTM 대비 더 빠르게 수렴하고 더 일찍 착취를 탐지한다.

실험 설계:
  1. 규칙적 시간 간격 vs 불규칙 시간 간격 데이터셋 비교
  2. 에포크별 수렴 속도 (val_AUC 곡선)
  3. 조기 탐지: 시퀀스 길이를 줄여가며 탐지 성능 비교
  4. 불규칙도(irregularity) 수준별 성능 변화
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from models.lnn_model import (
    LNNExploitationDetector, LSTMBaseline,
    normalize_sequences, train_model,
)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

plt.style.use("dark_background")
sns.set_palette("husl")

# 한글 폰트 설정 (macOS)
import platform
if platform.system() == "Darwin":
    plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False


# ────────────────────────────────────────────────
# 불규칙 시계열 합성 데이터 생성
# ────────────────────────────────────────────────

def generate_irregular_sequences(
    n_samples: int = 1000,
    seq_len: int = 12,
    irregularity: float = 0.5,
    exploitation_ratio: float = 0.25,
    seed: int = 42,
):
    """
    핵심 설계 원칙:
    - 착취 신호는 '시간 간격이 점점 늘어나는 추세' + '임금이 미세하게 감소'
    - 정상 패턴과 착취 패턴은 절댓값이 비슷하지만 '추세'가 다름
    - irregularity가 높을수록 랜덤 노이즈가 강해짐
      → LSTM: 등간격 가정 → 노이즈와 신호 혼용 → 탐지 저하
      → LNN:  시간 간격을 시간상수로 처리 → 추세를 더 잘 보존
    """
    np.random.seed(seed)
    X, y = [], []

    for i in range(n_samples):
        is_exploited = i < int(n_samples * exploitation_ratio)

        # ── 시간 간격 생성 ──────────────────────────────────────
        base_gap = 30.0
        if is_exploited:
            # 착취: 지급이 점점 늦어지는 '추세 + 불규칙 노이즈'
            trend = np.linspace(0, irregularity * 35, seq_len)  # 0→최대 35일 지연 추세
            noise = np.random.normal(0, irregularity * 12, seq_len)
            gaps = np.clip(base_gap + trend + noise, 7, 120)
        else:
            # 정상: 규칙적 + 동일 수준 불규칙 노이즈 (추세 없음)
            noise = np.random.normal(0, irregularity * 12, seq_len)
            gaps = np.clip(base_gap + noise, 10, 90)

        # ── 임금 비율 ────────────────────────────────────────────
        if is_exploited:
            # 착취: 0.92에서 시작해 점진적 감소 + 노이즈
            trend = np.linspace(0.92, 0.72, seq_len)
            noise = np.random.normal(0, 0.04 + irregularity * 0.03, seq_len)
            wage_ratio = np.clip(trend + noise, 0.3, 1.2)
        else:
            # 정상: 1.0 주변 + 노이즈 (추세 없음)
            noise = np.random.normal(0, 0.04 + irregularity * 0.03, seq_len)
            wage_ratio = np.clip(1.0 + noise, 0.6, 1.4)

        # ── 지급 지연일 ──────────────────────────────────────────
        if is_exploited:
            delay_trend = np.linspace(0, 8, seq_len)
            delay = np.clip(delay_trend + np.random.normal(0, 2 + irregularity * 3, seq_len), 0, 30)
        else:
            delay = np.clip(np.random.normal(0, 1 + irregularity * 2, seq_len), 0, 15)

        # ── 초과근무 착취 ────────────────────────────────────────
        overtime_exploit = np.zeros(seq_len)
        if is_exploited and np.random.rand() < 0.4:
            overtime_exploit = np.random.uniform(0.3, 0.8, seq_len)

        # 피처: [wage_ratio, delay, overtime_exploit, gap_normalized]
        gap_norm = (gaps - 30) / 30
        seq = np.stack([wage_ratio, delay, overtime_exploit, gap_norm], axis=1)
        X.append(seq)
        y.append(int(is_exploited))

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int64)


def train_with_history(model, X_train, y_train, X_val, y_val, epochs=100, lr=1e-3):
    """에포크별 val_AUC 기록"""
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    pos_weight = torch.tensor([(y_train == 0).sum() / max((y_train == 1).sum(), 1)], dtype=torch.float32)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)

    X_tr = torch.tensor(X_train, dtype=torch.float32)
    y_tr = torch.tensor(y_train, dtype=torch.float32).unsqueeze(-1)
    X_v = torch.tensor(X_val, dtype=torch.float32)
    y_v = torch.tensor(y_val, dtype=torch.float32)

    val_aucs, train_losses = [], []

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
            logits = model(X_v).squeeze()
            val_prob = torch.sigmoid(logits).numpy()
            val_loss = criterion(model(X_v), y_v.unsqueeze(-1)).item()

        try:
            auc = roc_auc_score(y_val, val_prob)
        except Exception:
            auc = 0.5
        val_aucs.append(auc)
        train_losses.append(loss.item())
        scheduler.step(val_loss)

    return val_aucs, train_losses


# ────────────────────────────────────────────────
# 실험 1: 수렴 속도 비교
# ────────────────────────────────────────────────

def experiment_convergence(irregularity: float = 0.7, n_runs: int = 3):
    print(f"\n[실험 1] 수렴 속도 비교 (불규칙도={irregularity})")
    X, y = generate_irregular_sequences(n_samples=1200, irregularity=irregularity)
    X_tr, X_test, y_tr, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    X_tr, X_val, y_tr, y_val = train_test_split(X_tr, y_tr, test_size=0.2, stratify=y_tr, random_state=42)

    n, s, f = X_tr.shape
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler()
    X_tr_s = sc.fit_transform(X_tr.reshape(-1, f)).reshape(n, s, f).astype(np.float32)
    X_val_s = sc.transform(X_val.reshape(-1, f)).reshape(X_val.shape[0], s, f).astype(np.float32)

    input_size = X.shape[2]
    results = {"LNN": [], "LSTM": []}

    for run in range(n_runs):
        for name, ModelClass in [("LNN", LNNExploitationDetector), ("LSTM", LSTMBaseline)]:
            model = ModelClass(input_size=input_size, hidden_size=64)
            aucs, _ = train_with_history(model, X_tr_s, y_tr, X_val_s, y_val, epochs=80)
            results[name].append(aucs)
        print(f"  run {run+1}/{n_runs} 완료")

    return results


# ────────────────────────────────────────────────
# 실험 2: 조기 탐지 (짧은 시퀀스)
# ────────────────────────────────────────────────

def experiment_early_detection(irregularity: float = 0.7):
    print(f"\n[실험 2] 조기 탐지 실험 (불규칙도={irregularity})")
    seq_lengths = [3, 4, 5, 6, 8, 10, 12]
    results = {"seq_len": seq_lengths, "LNN_auc": [], "LSTM_auc": []}

    for seq_len in seq_lengths:
        X, y = generate_irregular_sequences(
            n_samples=1000, seq_len=seq_len, irregularity=irregularity
        )
        X_tr, X_test, y_tr, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
        X_tr2, X_val, y_tr2, y_val = train_test_split(X_tr, y_tr, test_size=0.2, stratify=y_tr, random_state=42)

        n, s, f = X_tr2.shape
        from sklearn.preprocessing import StandardScaler
        sc = StandardScaler()
        X_tr_s = sc.fit_transform(X_tr2.reshape(-1, f)).reshape(n, s, f).astype(np.float32)
        X_val_s = sc.transform(X_val.reshape(-1, f)).reshape(X_val.shape[0], s, f).astype(np.float32)
        X_test_s = sc.transform(X_test.reshape(-1, f)).reshape(X_test.shape[0], s, f).astype(np.float32)

        input_size = f
        fold_aucs = {"LNN": [], "LSTM": []}

        for name, ModelClass in [("LNN", LNNExploitationDetector), ("LSTM", LSTMBaseline)]:
            model = ModelClass(input_size=input_size, hidden_size=64)
            train_with_history(model, X_tr_s, y_tr2, X_val_s, y_val, epochs=80)
            model.eval()
            with torch.no_grad():
                prob = torch.sigmoid(model(torch.tensor(X_test_s))).numpy().flatten()
            try:
                auc = roc_auc_score(y_test, prob)
            except Exception:
                auc = 0.5
            fold_aucs[name].append(auc)

        results["LNN_auc"].append(float(np.mean(fold_aucs["LNN"])))
        results["LSTM_auc"].append(float(np.mean(fold_aucs["LSTM"])))
        print(f"  seq_len={seq_len:2d} | LNN={results['LNN_auc'][-1]:.4f} | LSTM={results['LSTM_auc'][-1]:.4f}")

    return results


# ────────────────────────────────────────────────
# 실험 3: 불규칙도 수준별 성능
# ────────────────────────────────────────────────

def experiment_irregularity_level():
    print("\n[실험 3] 불규칙도 수준별 성능 비교")
    irregularities = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    results = {"irregularity": irregularities, "LNN_auc": [], "LSTM_auc": []}

    for irr in irregularities:
        X, y = generate_irregular_sequences(n_samples=800, seq_len=12, irregularity=irr)
        X_tr, X_test, y_tr, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
        X_tr2, X_val, y_tr2, y_val = train_test_split(X_tr, y_tr, test_size=0.2, stratify=y_tr, random_state=42)

        n, s, f = X_tr2.shape
        from sklearn.preprocessing import StandardScaler
        sc = StandardScaler()
        X_tr_s = sc.fit_transform(X_tr2.reshape(-1, f)).reshape(n, s, f).astype(np.float32)
        X_val_s = sc.transform(X_val.reshape(-1, f)).reshape(X_val.shape[0], s, f).astype(np.float32)
        X_test_s = sc.transform(X_test.reshape(-1, f)).reshape(X_test.shape[0], s, f).astype(np.float32)

        aucs = {}
        for name, ModelClass in [("LNN", LNNExploitationDetector), ("LSTM", LSTMBaseline)]:
            model = ModelClass(input_size=f, hidden_size=64)
            train_with_history(model, X_tr_s, y_tr2, X_val_s, y_val, epochs=60)
            model.eval()
            with torch.no_grad():
                prob = torch.sigmoid(model(torch.tensor(X_test_s))).numpy().flatten()
            try:
                aucs[name] = roc_auc_score(y_test, prob)
            except Exception:
                aucs[name] = 0.5

        results["LNN_auc"].append(float(aucs["LNN"]))
        results["LSTM_auc"].append(float(aucs["LSTM"]))
        print(f"  irr={irr:.1f} | LNN={aucs['LNN']:.4f} | LSTM={aucs['LSTM']:.4f}")

    return results


# ────────────────────────────────────────────────
# 시각화
# ────────────────────────────────────────────────

def plot_results(conv_results, early_results, irr_results):
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("LNN vs LSTM: Irregular Time-Series Wage Exploitation Detection", fontsize=14, color="white")

    # 1. Convergence Speed
    ax = axes[0]
    for name, color in [("LNN", "#4CAF50"), ("LSTM", "#F44336")]:
        runs = conv_results[name]
        mean_auc = np.mean(runs, axis=0)
        std_auc = np.std(runs, axis=0)
        x = range(1, len(mean_auc) + 1)
        ax.plot(x, mean_auc, label=name, color=color, linewidth=2)
        ax.fill_between(x, mean_auc - std_auc, mean_auc + std_auc, alpha=0.2, color=color)
    ax.set_title("Convergence Speed (Val AUROC per Epoch)", color="white")
    ax.set_xlabel("Epoch", color="white")
    ax.set_ylabel("Val AUROC", color="white")
    ax.legend()
    ax.set_ylim(0.4, 1.05)
    ax.grid(alpha=0.3)

    # 2. Early Detection
    ax = axes[1]
    ax.plot(early_results["seq_len"], early_results["LNN_auc"],
            "o-", label="LNN", color="#4CAF50", linewidth=2, markersize=8)
    ax.plot(early_results["seq_len"], early_results["LSTM_auc"],
            "s-", label="LSTM", color="#F44336", linewidth=2, markersize=8)
    ax.axvline(x=6, color="yellow", linestyle="--", alpha=0.7, label="6-Month Baseline")
    ax.set_title("Early Detection: AUROC by Sequence Length", color="white")
    ax.set_xlabel("Observation Months", color="white")
    ax.set_ylabel("Test AUROC", color="white")
    ax.legend()
    ax.set_ylim(0.4, 1.05)
    ax.grid(alpha=0.3)

    # 3. Irregularity Level
    ax = axes[2]
    ax.plot(irr_results["irregularity"], irr_results["LNN_auc"],
            "o-", label="LNN", color="#4CAF50", linewidth=2, markersize=8)
    ax.plot(irr_results["irregularity"], irr_results["LSTM_auc"],
            "s-", label="LSTM", color="#F44336", linewidth=2, markersize=8)
    diff = np.array(irr_results["LNN_auc"]) - np.array(irr_results["LSTM_auc"])
    ax2 = ax.twinx()
    ax2.bar(irr_results["irregularity"], diff, alpha=0.3, color="#2196F3", width=0.1, label="LNN Advantage")
    ax2.set_ylabel("LNN - LSTM AUROC", color="#2196F3")
    ax.set_title("LNN Advantage at High Irregularity", color="white")
    ax.set_xlabel("Irregularity (0=Regular, 1=Fully Irregular)", color="white")
    ax.set_ylabel("Test AUROC", color="white")
    ax.legend(loc="lower left")
    ax.set_ylim(0.4, 1.05)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    out_path = os.path.join(RESULTS_DIR, "lnn_vs_lstm_experiment.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="#0e1117")
    print(f"\n그래프 저장: {out_path}")
    return out_path


# ────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("LNN vs LSTM 비교 실험")
    print("=" * 60)

    conv_results = experiment_convergence(irregularity=0.7, n_runs=3)
    early_results = experiment_early_detection(irregularity=0.7)
    irr_results = experiment_irregularity_level()

    plot_results(conv_results, early_results, irr_results)

    # 결과 저장
    def _get_auc_at(results, seq_len):
        if seq_len in results["seq_len"]:
            idx = results["seq_len"].index(seq_len)
            return results["LNN_auc"][idx], results["LSTM_auc"][idx]
        return None, None

    lnn_3, lstm_3 = _get_auc_at(early_results, 3)
    lnn_6, lstm_6 = _get_auc_at(early_results, 6)

    summary = {
        "convergence": {
            "LNN_final_auc_mean": float(np.mean([r[-1] for r in conv_results["LNN"]])),
            "LSTM_final_auc_mean": float(np.mean([r[-1] for r in conv_results["LSTM"]])),
            "LNN_epoch_to_90pct": next(
                (i+1 for aucs in [np.mean(conv_results["LNN"], axis=0)]
                 for i, a in enumerate(aucs) if a >= 0.9), 80
            ),
            "LSTM_epoch_to_90pct": next(
                (i+1 for aucs in [np.mean(conv_results["LSTM"], axis=0)]
                 for i, a in enumerate(aucs) if a >= 0.9), 80
            ),
        },
        "early_detection": {
            "seq_3_LNN": lnn_3,
            "seq_3_LSTM": lstm_3,
            "seq_6_LNN": lnn_6,
            "seq_6_LSTM": lstm_6,
        },
        "irregularity": {
            "high_irr_LNN": irr_results["LNN_auc"][-1],
            "high_irr_LSTM": irr_results["LSTM_auc"][-1],
            "advantage_at_high_irr": irr_results["LNN_auc"][-1] - irr_results["LSTM_auc"][-1],
        },
    }

    with open(os.path.join(RESULTS_DIR, "lnn_experiment_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("실험 요약")
    print("=" * 60)
    print(f"수렴 속도: LNN {summary['convergence']['LNN_epoch_to_90pct']}에포크 vs LSTM {summary['convergence']['LSTM_epoch_to_90pct']}에포크 (AUROC 0.9 도달)")
    early = summary["early_detection"]
    if early["seq_6_LNN"] and early["seq_6_LSTM"]:
        print(f"6개월 조기탐지: LNN {early['seq_6_LNN']:.4f} vs LSTM {early['seq_6_LSTM']:.4f}")
    print(f"고불규칙도 환경: LNN {summary['irregularity']['high_irr_LNN']:.4f} vs LSTM {summary['irregularity']['high_irr_LSTM']:.4f}")
    print(f"LNN 우위: +{summary['irregularity']['advantage_at_high_irr']:.4f}")
