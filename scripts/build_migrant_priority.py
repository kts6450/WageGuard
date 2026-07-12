# -*- coding: utf-8 -*-
"""이주노동자(E-9) 노출-가중 우선순위 — WageGuard의 이주노동자 결합 완성.

원리: 셀 위험(국민연금 실측) × 그 셀의 E-9 근로자 수(KOSIS 실측)
  = '고위험 환경에 노출된 이주노동자 규모' 지수.
  위험이 같아도 E-9가 많은 셀이 먼저 — 통역 동반 점검·사전 안내 배정 순서.

출력: results/migrant_priority.csv, results/fig_migrant_priority.png
"""
from __future__ import annotations

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(HERE, "results")
PUB = os.path.join(HERE, "data", "public")

NAVY, TEAL, AMBER, CORAL = "#0F2A43", "#14B8A6", "#F59E0B", "#EF4B4B"
GRAY, GRID, INK = "#64748B", "#E2E8F0", "#1E293B"

SIDO_TEXT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북",
    "경상남도": "경남", "제주특별자치도": "제주",
}


def load_e9() -> pd.DataFrame:
    raw = pd.read_csv(os.path.join(PUB, "kosis_e9_sido_industry.csv"),
                      header=[0, 1], encoding="utf-8-sig")
    # 최신 분기 열 사용
    quarters = sorted({c[0] for c in raw.columns if "/" in str(c[0])})
    latest = quarters[-1]
    sido_col = raw.columns[0]
    rows = []
    for _, r in raw.iterrows():
        sido = SIDO_TEXT.get(str(r[sido_col]).strip())
        if not sido:
            continue
        mfg = r.get((latest, "제조업"), 0) or 0
        con = r.get((latest, "건설업"), 0) or 0
        agr = sum(float(r.get((latest, k), 0) or 0)
                  for k in ("농축산업", "어업", "임업"))
        rows.append({"시도": sido, "제조업": float(mfg),
                     "건설업": float(con), "농림어업": agr})
    df = pd.DataFrame(rows)
    long = df.melt(id_vars="시도", var_name="업종대분류", value_name="E9인원")
    long.attrs["quarter"] = latest
    return long


def main():
    cells = pd.read_csv(os.path.join(RES, "cell_risk_table.csv"),
                        encoding="utf-8-sig")
    e9 = load_e9()
    quarter = e9.attrs["quarter"]
    m = cells.merge(e9, on=["시도", "업종대분류"], how="inner")
    m["위험백분위"] = cells["위험점수"].rank(pct=True).reindex(m.index)
    # 전체 셀 기준 백분위 재계산 (merge 후 인덱스 정합)
    pct_map = cells.assign(pct=cells["위험점수"].rank(pct=True) * 100) \
        .set_index(["시도", "업종대분류"])["pct"]
    m["위험백분위"] = m.apply(
        lambda r: pct_map.get((r["시도"], r["업종대분류"])), axis=1)
    m = m.dropna(subset=["위험백분위"])
    m["노출가중지수"] = (m["E9인원"] * m["위험백분위"] / 100).round(0)
    m = m.sort_values("노출가중지수", ascending=False)

    out_cols = ["시도", "업종대분류", "E9인원", "위험백분위", "노출가중지수",
                "체불_전체"]
    m[out_cols].to_csv(os.path.join(RES, "migrant_priority.csv"),
                       index=False, encoding="utf-8-sig")
    print(f"E-9 분기: {quarter} · 매칭 셀 {len(m)}개 · "
          f"E-9 합계 {int(m['E9인원'].sum()):,}명")
    print(m[out_cols].head(12).to_string(index=False))

    # 그림 — 상위 10 셀
    top = m.head(10).iloc[::-1]
    labels = top["시도"] + " · " + top["업종대분류"]
    plt.rcParams.update({"font.family": "Malgun Gothic",
                         "axes.unicode_minus": False, "font.size": 11})
    fig, ax = plt.subplots(figsize=(7.8, 5.0), dpi=200)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    colors = [CORAL if p >= 80 else (AMBER if p >= 60 else NAVY)
              for p in top["위험백분위"]]
    bars = ax.barh(labels, top["노출가중지수"], height=0.62, color=colors,
                   zorder=3)
    for b, (_, r) in zip(bars, top.iterrows()):
        ax.text(b.get_width() + top["노출가중지수"].max() * 0.012,
                b.get_y() + b.get_height() / 2,
                f"E-9 {int(r['E9인원']):,}명 · 위험 {r['위험백분위']:.0f}p",
                va="center", fontsize=9.5, color=INK)
    ax.set_xlim(0, top["노출가중지수"].max() * 1.42)
    ax.set_xlabel("이주노동자 노출-가중 위험 지수  (E-9 인원 × 위험 백분위/100)")
    ax.set_title(f"통역 동반 점검·사전 안내 우선순위 상위 10 셀 "
                 f"(KOSIS {quarter} 실측)", fontsize=11.5, color=GRAY, pad=12)
    ax.grid(axis="x", color=GRID, linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "fig_migrant_priority.png"))
    print("saved: results/migrant_priority.csv, results/fig_migrant_priority.png")


if __name__ == "__main__":
    main()
