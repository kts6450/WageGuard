# -*- coding: utf-8 -*-
"""검증의 검증 — 발표 수치에 대한 적대적 감사.

점검 항목:
  A. 체불 명단 중복(동일 사업주 다차수 등재) 여부
  B. 기준선 교체: 가입자 비중 vs 사업장수 비중 기준 lift 비교
  C. 건설업 제외 강건성 (업종 몰빵 반박)
  D. 순열검정: 무작위 셀 순위 10,000회 대비 관측 포착률의 p-value
  E. 단순 대안 기준선: '큰 셀부터'(사업장수 순) 점검 대비 우위 여부
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(HERE, "results")
PUB = os.path.join(HERE, "data", "public")


def capture_at(c: pd.DataFrame, order_col: str, frac: float,
               base_col: str, def_col: str = "체불_전체",
               ascending: bool = False) -> dict:
    s = c.sort_values(order_col, ascending=ascending)
    k = max(1, int(round(len(s) * frac)))
    top = s.head(k)
    cap = top[def_col].sum() / max(s[def_col].sum(), 1)
    share = top[base_col].sum() / s[base_col].sum()
    return {"capture": round(float(cap), 4), "share": round(float(share), 4),
            "lift": round(float(cap / share) if share else 0, 2)}


def main():
    cells = pd.read_csv(os.path.join(RES, "cell_risk_table.csv"),
                        encoding="utf-8-sig")
    deft = pd.read_csv(os.path.join(PUB, "defaulter_list.csv"),
                       encoding="utf-8-sig")
    out = {}

    # A. 명단 중복 점검 -----------------------------------------------------
    dup_keys = deft.duplicated(subset=["성명", "사업장명"], keep=False)
    out["A_중복"] = {
        "동일 성명+사업장 중복행": int(dup_keys.sum()),
        "고유 사업주(성명+사업장)": int(
            deft[["성명", "사업장명"]].drop_duplicates().shape[0]),
        "전체 행": int(len(deft)),
    }

    # B. 기준선 교체 --------------------------------------------------------
    out["B_기준선"] = {
        "top10_고용기준": capture_at(cells, "위험점수", 0.10, "가입자수"),
        "top10_사업장수기준": capture_at(cells, "위험점수", 0.10, "사업장수"),
        "top20_고용기준": capture_at(cells, "위험점수", 0.20, "가입자수"),
        "top20_사업장수기준": capture_at(cells, "위험점수", 0.20, "사업장수"),
    }

    # C. 건설업 제외 --------------------------------------------------------
    noc = cells[cells["업종대분류"] != "건설업"].copy()
    out["C_건설업제외"] = {
        "잔여 체불(검증 표본)": int(noc["체불_전체"].sum()),
        "top10_고용기준": capture_at(noc, "위험점수", 0.10, "가입자수"),
        "top20_고용기준": capture_at(noc, "위험점수", 0.20, "가입자수"),
        "top10_사업장수기준": capture_at(noc, "위험점수", 0.10, "사업장수"),
    }

    # D. 순열검정 -----------------------------------------------------------
    rng = np.random.default_rng(7)
    n = len(cells)
    k10 = max(1, int(round(n * 0.10)))
    obs = (cells.sort_values("위험점수", ascending=False)
           .head(k10)["체불_전체"].sum())
    tot = cells["체불_전체"].sum()
    vals = cells["체불_전체"].to_numpy()
    sims = np.array([vals[rng.permutation(n)[:k10]].sum()
                     for _ in range(10000)])
    out["D_순열검정"] = {
        "관측 top10% 포착(건)": int(obs),
        "무작위 평균(건)": round(float(sims.mean()), 1),
        "p_value(관측 이상 확률)": round(float((sims >= obs).mean()), 5),
    }

    # E. '큰 셀부터' 대안 기준선 ---------------------------------------------
    out["E_대안기준선"] = {
        "위험점수순_top10_포착": capture_at(cells, "위험점수", 0.10,
                                     "가입자수")["capture"],
        "사업장수순_top10_포착": capture_at(cells, "사업장수", 0.10,
                                      "가입자수")["capture"],
        "가입자수순_top10_포착": capture_at(cells, "가입자수", 0.10,
                                      "가입자수")["capture"],
    }

    with open(os.path.join(RES, "validation_audit.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
