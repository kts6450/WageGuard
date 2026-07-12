# -*- coding: utf-8 -*-
"""셀 스크리닝 실증 결과 그림 3종 (발표용, 전부 실데이터).

  1. fig_cell_capture.png — 누적 포착 곡선 (전체 명단 / 2025~26 미래 차수)
  2. fig_cell_riskmap.png — 시도 × 산업 위험 히트맵 (백분위)
  3. fig_e9_risk.png      — E-9 제조업 중분류 인원 (이주노동자 렌즈)
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(HERE, "results")

NAVY = "#0F2A43"
TEAL = "#14B8A6"
TEAL_D = "#0D9488"
AMBER = "#F59E0B"
INK = "#1E293B"
GRAY = "#64748B"
GRID = "#E2E8F0"
BG = "#FFFFFF"

plt.rcParams.update({
    "font.family": "Malgun Gothic",
    "axes.unicode_minus": False,
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK,
    "xtick.color": GRAY,
    "ytick.color": GRAY,
    "text.color": INK,
    "font.size": 11,
})


def style_ax(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(True, color=GRID, linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)


def fig_capture(cells: pd.DataFrame):
    c = cells.sort_values("위험점수", ascending=False).reset_index(drop=True)
    ins = c["가입자수"].cumsum() / c["가입자수"].sum()
    cap_all = c["체불_전체"].cumsum() / c["체불_전체"].sum()
    cap_fut = c["체불_2025이후"].cumsum() / c["체불_2025이후"].sum()

    fig, ax = plt.subplots(figsize=(7.6, 5.2), dpi=200)
    style_ax(ax)
    n_all = int(c["체불_전체"].sum())
    n_fut = int(c["체불_2025이후"].sum())
    ax.plot([0, 1], [0, 1], ls="--", lw=1.6, color=GRAY,
            label="무작위 점검 (기준선)")
    ax.plot(ins, cap_all, lw=2.4, color=NAVY,
            label=f"전체 명단 (2023~2026, {n_all}명)")
    ax.plot(ins, cap_fut, lw=2.4, color=TEAL,
            label=f"홀드아웃 차수 (2025~2026, {n_fut}명)")

    # 상위 10% 셀 지점 직접 라벨
    n10 = max(1, int(round(len(c) * 0.10)))
    x10, y10, y10f = ins.iloc[n10 - 1], cap_all.iloc[n10 - 1], cap_fut.iloc[n10 - 1]
    ax.scatter([x10, x10], [y10, y10f], s=46, zorder=5,
               color=[NAVY, TEAL], edgecolor=BG, linewidth=1.5)
    ax.annotate(f"상위 10% 셀\n고용 {x10:.0%} → 체불 {y10:.0%} 포착 ({y10/x10:.1f}배)",
                (x10, y10), xytext=(x10 + 0.05, y10 - 0.02),
                fontsize=10.5, fontweight="bold", color=NAVY)
    ax.annotate(f"홀드아웃 차수 {y10f:.0%} ({y10f/x10:.1f}배)",
                (x10, y10f), xytext=(x10 + 0.05, y10f - 0.075),
                fontsize=10, color=TEAL_D)

    ax.set_xlabel("점검 대상 고용 비중 (위험 점수 상위 셀부터 누적)")
    ax.set_ylabel("임금체불 사업주 포착률 (누적)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="lower right", frameon=False, fontsize=10)
    ax.set_title("위험 지표는 체불 명단을 전혀 보지 않고 산출 — 그런데도 명단 밀집 셀을 맞힌다",
                 fontsize=11.5, color=GRAY, pad=12)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "fig_cell_capture.png"))
    plt.close(fig)


def fig_riskmap(cells: pd.DataFrame):
    top_ind = (cells.groupby("업종대분류")["가입자수"].sum()
               .sort_values(ascending=False).head(12).index.tolist())
    sido_order = (cells.groupby("시도")["가입자수"].sum()
                  .sort_values(ascending=False).index.tolist())
    c = cells[cells["업종대분류"].isin(top_ind)].copy()
    c["pct"] = c["위험점수"].rank(pct=True) * 100
    mat = c.pivot_table(index="업종대분류", columns="시도", values="pct")
    mat = mat.reindex(index=top_ind, columns=sido_order)

    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list(
        "teal_seq", ["#F0FDFA", "#99F6E4", "#2DD4BF", "#0D9488", "#134E4A"])

    fig, ax = plt.subplots(figsize=(9.6, 5.4), dpi=200)
    im = ax.imshow(mat.values, cmap=cmap, vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(mat.columns)), mat.columns, fontsize=10)
    ax.set_yticks(range(len(mat.index)), mat.index, fontsize=10)
    for s in ax.spines.values():
        s.set_visible(False)
    # 상위 5% 셀 직접 라벨
    thr = np.nanpercentile(mat.values, 95)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat.values[i, j]
            if not np.isnan(v) and v >= thr:
                ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                        fontsize=8.5, fontweight="bold", color="white")
    cb = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.015)
    cb.set_label("위험 점수 백분위 (100 = 최고위험)", fontsize=9.5, color=GRAY)
    cb.outline.set_visible(False)
    ax.set_title("시도 × 산업 셀 위험 백분위 — 국민연금 행정데이터 실측 "
                 "(저임금·고이직·영세성 합성)", fontsize=11.5, color=GRAY, pad=12)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "fig_cell_riskmap.png"))
    plt.close(fig)


def fig_e9(scr: dict):
    subs = scr["migrant_focus"]["e9_top_subsectors"]
    names = [s["name"].replace(" 제조업; 기계 및 가구 제외", "")
             .replace(" 제조업", "") for s in subs][::-1]
    vals = [s["workers"] for s in subs][::-1]

    fig, ax = plt.subplots(figsize=(7.6, 4.6), dpi=200)
    style_ax(ax)
    ax.grid(axis="y", visible=False)
    bars = ax.barh(names, vals, height=0.62, color=NAVY, zorder=3)
    bars[-1].set_color(TEAL)  # 최대 밀집 중분류 강조
    for b, v in zip(bars, vals):
        ax.text(v + 700, b.get_y() + b.get_height() / 2, f"{v:,}명",
                va="center", fontsize=10.5, color=INK, fontweight="bold")
    ax.set_xlim(0, max(vals) * 1.18)
    ax.set_xlabel("E-9 외국인근로자 수 (제조업 중분류, 2025년 말)")
    total = scr["migrant_focus"]["e9_total_mfg"]
    ax.set_title(f"제조업 E-9 {total:,}명의 중분류 분포 — 위험 셀과 겹치는 곳이 "
                 "우선 보호 대상", fontsize=11.5, color=GRAY, pad=12)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "fig_e9_risk.png"))
    plt.close(fig)


def main():
    cells = pd.read_csv(os.path.join(RES, "cell_risk_table.csv"),
                        encoding="utf-8-sig")
    with open(os.path.join(RES, "cell_screening.json"), encoding="utf-8") as f:
        scr = json.load(f)
    fig_capture(cells)
    fig_riskmap(cells)
    fig_e9(scr)
    print("saved: fig_cell_capture.png, fig_cell_riskmap.png, fig_e9_risk.png")


if __name__ == "__main__":
    main()
