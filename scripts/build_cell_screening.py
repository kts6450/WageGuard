# -*- coding: utf-8 -*-
"""WageGuard 셀 단위 위험 스크리닝 — 전면 공개 데이터 실증 파이프라인.

입력 (전부 로그인·승인 불필요 공개 데이터):
  - data/public/국민연금공단_국민연금 가입 사업장 내역_*.csv  (약 59만 사업장)
  - data/public/defaulter_list.csv  (고용노동부 임금체불 사업주 공개 명단 789건)
  - data/public/고용노동부_제조업 외국인근로자 근무현황_*.csv  (E-9 중분류 인원)

설계 원칙 (멘토 지적 대응):
  1. 위험 지표는 국민연금 행정데이터만으로 산출 — 체불 명단 정보는 지표에
     일절 사용하지 않는다(순환논리·누수 원천 차단).
  2. 가중치는 임의 상수가 아니라 ① 동일가중 z-합성 + 가중 섭동 민감도,
     ② 과거 차수(≤2024) 체불 명단으로 학습한 로지스틱 계수(데이터 산출)
     두 방식으로 병행하고, 미래 차수(2025~2026)로만 평가한다.
  3. 산출 단위는 시도 × 산업대분류 셀 — 개별 사업장 지목 없음.

출력:
  - results/cell_screening.json   (검증 수치)
  - results/cell_risk_table.csv   (전체 셀 테이블)
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(HERE, "data", "public")
RES = os.path.join(HERE, "results")

# ---------------------------------------------------------------------------
# 코드 매핑
# ---------------------------------------------------------------------------
SIDO_CODE = {
    11: "서울", 26: "부산", 27: "대구", 28: "인천", 29: "광주", 30: "대전",
    31: "울산", 36: "세종", 41: "경기", 42: "강원", 51: "강원", 43: "충북",
    44: "충남", 45: "전북", 52: "전북", 46: "전남", 47: "경북", 48: "경남",
    50: "제주",
}

SIDO_TEXT = {
    "서울특별시": "서울", "서울": "서울", "부산광역시": "부산", "부산": "부산",
    "대구광역시": "대구", "대구": "대구", "인천광역시": "인천", "인천": "인천",
    "광주광역시": "광주", "광주": "광주", "대전광역시": "대전", "대전": "대전",
    "울산광역시": "울산", "울산": "울산", "세종특별자치시": "세종", "세종": "세종",
    "경기도": "경기", "경기": "경기", "강원도": "강원", "강원특별자치도": "강원",
    "강원": "강원", "충청북도": "충북", "충북": "충북", "충청남도": "충남",
    "충남": "충남", "전라북도": "전북", "전북특별자치도": "전북", "전북": "전북",
    "전라남도": "전남", "전남": "전남", "경상북도": "경북", "경북": "경북",
    "경상남도": "경남", "경남": "경남", "제주특별자치도": "제주", "제주": "제주",
    "제주도": "제주",
}

# 국민연금 사업장업종코드는 KSIC 8차(구분류) 기반 — 실데이터로 확인:
# 45-46=건설(공사업), 15-37=제조, 50-52=도소매, 55=숙박음식, 60-63=운수,
# 65-67=금융, 70-71=부동산, 80=교육, 85-86=보건복지, 90-93=기타서비스.
# 10차 대분류(체불 명단 표기)로의 크로스워크. 완전 일치가 아닌 근사임을
# 한계로 명시(출판·방송 등 일부 경계 업종).
DIV2SECTION = {}
for lo, hi, name in [
    (1, 5, "농림어업"), (10, 12, "광업"), (15, 37, "제조업"),
    (40, 41, "전기가스"), (45, 46, "건설업"), (50, 52, "도소매업"),
    (55, 55, "숙박음식점업"), (60, 63, "운수창고업"),
    (64, 64, "정보통신업"), (72, 72, "정보통신업"),
    (65, 67, "금융보험업"), (70, 71, "부동산업"),
    (73, 74, "전문과학기술"), (75, 75, "사업시설관리"),
    (76, 76, "공공행정"), (80, 80, "교육서비스업"),
    (85, 86, "보건사회복지"), (87, 88, "예술스포츠여가"),
    (90, 90, "수도하수폐기물"), (91, 93, "협회수리개인"),
    (95, 99, "기타"),
]:
    for d in range(lo, hi + 1):
        DIV2SECTION[d] = name

DEFAULTER_IND = {
    "건설업": "건설업", "제조업": "제조업", "도매 및 소매업": "도소매업",
    "숙박 및 음식점업": "숙박음식점업", "정보통신업": "정보통신업",
    "전문  과학 및 기술 서비스업": "전문과학기술",
    "사업시설 관리 사업 지원 및 임대 서비스업": "사업시설관리",
    "협회 및 단체  수리 및 기타 개인 서비스업": "협회수리개인",
    "예술  스포츠 및 여가관련 서비스업": "예술스포츠여가",
    "교육 서비스업": "교육서비스업", "보건업 및 사회복지 서비스업": "보건사회복지",
    "부동산업": "부동산업", "운수 및 창고업": "운수창고업",
    "농업  임업 및 어업": "농림어업", "광업": "광업",
    "수도  하수 및 폐기물 처리  원료 재생업": "수도하수폐기물",
    "금융 및 보험업": "금융보험업",
}

TRAIN_ROUNDS = {"2023년 1차", "2023년 2차", "2024년 1차", "2024년 2차"}
TEST_ROUNDS = {"2025년 1차", "2026년 1차"}

MIN_INSURED = int(os.environ.get("WG_MIN_INSURED", "3000"))  # 셀 최소 가입자 수


def zscore(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / (s.std(ddof=0) + 1e-12)


def load_nps() -> pd.DataFrame:
    path = sorted(glob.glob(os.path.join(PUB, "국민연금공단*가입 사업장 내역*.csv")))[-1]
    print("loading:", os.path.basename(path))
    df = pd.read_csv(path, encoding="cp949", low_memory=False)
    df = df.rename(columns={
        "사업장가입상태코드 1 등록 2 탈퇴": "상태",
        "법정동주소광역시도코드": "시도코드",
        "사업장업종코드": "업종코드",
    })
    df["시도"] = pd.to_numeric(df["시도코드"], errors="coerce").map(SIDO_CODE)
    div = pd.to_numeric(df["업종코드"], errors="coerce").fillna(0).astype(int) // 10000
    df["업종대분류"] = div.map(DIV2SECTION)
    df = df[df["상태"] == 1]  # 현재 등록 사업장 기준
    df = df.dropna(subset=["시도", "업종대분류"])
    df = df[df["가입자수"] > 0]
    return df


def build_cells(nps: pd.DataFrame) -> pd.DataFrame:
    g = nps.groupby(["시도", "업종대분류"])
    cells = pd.DataFrame({
        "사업장수": g.size(),
        "가입자수": g["가입자수"].sum(),
        "고지금액": g["당월고지금액"].sum(),
        "신규취득": g["신규취득자수"].sum(),
        "상실": g["상실가입자수"].sum(),
        "영세비중": g["가입자수"].apply(lambda s: float((s < 5).mean())),
    }).reset_index()
    cells = cells[cells["가입자수"] >= MIN_INSURED].copy()
    # 파생 지표 (전부 데이터 실측 기반 — 임의 상수 없음)
    cells["인당보험료"] = cells["고지금액"] / cells["가입자수"]      # 임금 수준 프록시
    cells["이직률"] = (cells["신규취득"] + cells["상실"]) / (2 * cells["가입자수"])
    cells["평균규모"] = cells["가입자수"] / cells["사업장수"]
    # 동일가중 z-합성 위험 지표 (저임금·고이직·영세 ↑ = 위험 ↑)
    z_low_wage = -zscore(np.log(cells["인당보험료"]))
    z_churn = zscore(cells["이직률"])
    z_small = zscore(cells["영세비중"])
    cells["위험점수"] = (z_low_wage + z_churn + z_small) / 3
    cells["_z"] = list(zip(z_low_wage, z_churn, z_small))
    return cells


def load_defaulters() -> pd.DataFrame:
    d = pd.read_csv(os.path.join(PUB, "defaulter_list.csv"), encoding="utf-8-sig")
    # 동일 사업주(성명+사업장)의 다차수 재등재 중복 제거 — 최초 차수만 유지
    d = (d.sort_values("공개차수")
         .drop_duplicates(subset=["성명", "사업장명"], keep="first"))
    d["시도"] = d["소재지_사업장"].astype(str).str.split().str[0].map(SIDO_TEXT)
    d["업종대분류"] = d["업종"].str.strip().map(
        lambda x: DEFAULTER_IND.get(x, DEFAULTER_IND.get(re.sub(r"\s+", " ", str(x)))))
    d["체불액"] = pd.to_numeric(
        d["체불액_원"].astype(str).str.replace(",", ""), errors="coerce")
    n_before = len(d)
    d = d.dropna(subset=["시도", "업종대분류"])
    print(f"defaulters mapped: {len(d)}/{n_before}")
    return d


def capture_metrics(cells: pd.DataFrame, dcnt: pd.Series, label: str,
                    score_col: str = "위험점수") -> dict:
    """위험점수 상위 셀이 (한 번도 보지 않은) 체불 명단을 얼마나 포착하는가."""
    c = cells.copy()
    c["체불"] = c.set_index(["시도", "업종대분류"]).index.map(dcnt).fillna(0).values \
        if False else c.apply(
        lambda r: dcnt.get((r["시도"], r["업종대분류"]), 0), axis=1)
    c = c.sort_values(score_col, ascending=False)
    tot_def = c["체불"].sum()
    tot_ins = c["가입자수"].sum()
    out = {"label": label, "total_defaulters": int(tot_def),
           "n_cells": int(len(c))}
    for frac in (0.1, 0.2, 0.3):
        k = max(1, int(round(len(c) * frac)))
        top = c.head(k)
        cap = top["체불"].sum() / tot_def if tot_def else 0.0
        share = top["가입자수"].sum() / tot_ins
        out[f"top{int(frac*100)}"] = {
            "cells": int(k),
            "capture": round(float(cap), 4),          # 체불 포착률
            "insured_share": round(float(share), 4),  # 고용 비중(공정 기준선)
            "lift": round(float(cap / share) if share else 0.0, 2),
        }
    # 셀 단위 순위 상관 (체불률 = 가입자 10만명당)
    c["체불률"] = c["체불"] / c["가입자수"] * 1e5
    rho = c[score_col].corr(c["체불률"], method="spearman")
    out["spearman_risk_vs_rate"] = round(float(rho), 4)
    return out


def weight_sensitivity(cells: pd.DataFrame, seed: int = 42, n: int = 200) -> dict:
    """가중치 섭동 민감도 — '임의 가중치' 비판에 대한 정량 응답.

    동일가중 대신 디리클레 분포에서 뽑은 무작위 가중 200조합으로 합성해도
    셀 순위가 유지되는지 스피어만 상관으로 확인한다.
    """
    rng = np.random.default_rng(seed)
    z = np.array([list(t) for t in cells["_z"]])
    base = cells["위험점수"].to_numpy()
    rhos = []
    for _ in range(n):
        w = rng.dirichlet([1.0, 1.0, 1.0])
        alt = z @ w
        rhos.append(pd.Series(alt).corr(pd.Series(base), method="spearman"))
    return {"n_perturb": n, "rho_mean": round(float(np.mean(rhos)), 4),
            "rho_min": round(float(np.min(rhos)), 4)}


def supervised_temporal(cells: pd.DataFrame, deft: pd.DataFrame) -> dict:
    """과거 차수(≤2024)로 학습 → 미래 차수(2025~2026)만으로 평가.

    가중치를 사람이 정하지 않고 과거 데이터에서 로지스틱 회귀로 산출.
    """
    from sklearn.linear_model import LogisticRegression

    tr_cnt = deft[deft["공개차수"].isin(TRAIN_ROUNDS)].groupby(
        ["시도", "업종대분류"]).size()
    te_cnt = deft[deft["공개차수"].isin(TEST_ROUNDS)].groupby(
        ["시도", "업종대분류"]).size()

    X = np.array([list(t) for t in cells["_z"]])
    tr_rate = cells.apply(lambda r: tr_cnt.get((r["시도"], r["업종대분류"]), 0),
                          axis=1) / cells["가입자수"] * 1e5
    y_tr = (tr_rate > tr_rate.median()).astype(int)  # 과거 고체불 셀 여부
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X, y_tr)
    cells = cells.copy()
    cells["학습위험"] = clf.decision_function(X)
    m = capture_metrics(cells, te_cnt, "supervised_future_rounds", "학습위험")
    m["coef"] = {k: round(float(v), 3) for k, v in
                 zip(["저임금", "이직률", "영세비중"], clf.coef_[0])}
    return m


def migrant_focus(cells: pd.DataFrame) -> dict:
    """E-9 제조업 중분류 인원(공개 CSV)과 제조업 셀 위험의 결합 — 이주노동자 렌즈."""
    path = sorted(glob.glob(os.path.join(PUB, "*제조업 외국인근로자*.csv")))[-1]
    e9 = pd.read_csv(path, encoding="cp949")
    e9.columns = ["업종_중분류", "E9인원"]
    e9 = e9.sort_values("E9인원", ascending=False)
    top = e9.head(5)
    mfg = cells[cells["업종대분류"] == "제조업"].sort_values(
        "위험점수", ascending=False)
    return {
        "e9_total_mfg": int(e9["E9인원"].sum()),
        "e9_top_subsectors": [
            {"name": r["업종_중분류"].replace("11차_", ""), "workers": int(r["E9인원"])}
            for _, r in top.iterrows()],
        "mfg_top_risk_cells": [
            {"sido": r["시도"], "risk": round(float(r["위험점수"]), 3)}
            for _, r in mfg.head(5).iterrows()],
    }


def main():
    os.makedirs(RES, exist_ok=True)
    nps = load_nps()
    print(f"NPS active workplaces: {len(nps):,} / insured {int(nps['가입자수'].sum()):,}")
    cells = build_cells(nps)
    print(f"cells (>= {MIN_INSURED} insured): {len(cells)}")
    deft = load_defaulters()

    all_cnt = deft.groupby(["시도", "업종대분류"]).size()
    fut_cnt = deft[deft["공개차수"].isin(TEST_ROUNDS)].groupby(
        ["시도", "업종대분류"]).size()

    results = {
        "inputs": {
            "nps_workplaces": int(len(nps)),
            "nps_insured": int(nps["가입자수"].sum()),
            "nps_snapshot": str(nps["자료생성년월"].iloc[0]),
            "defaulters_total": int(len(deft)),
            "defaulters_future_rounds": int(
                deft["공개차수"].isin(TEST_ROUNDS).sum()),
            "n_cells": int(len(cells)),
            "min_insured_per_cell": MIN_INSURED,
        },
        # 1) 비지도 합성 지표 vs 전체 명단 (지표는 명단을 전혀 보지 않음)
        "unsupervised_vs_all": capture_metrics(cells, all_cnt, "unsup_all"),
        # 2) 비지도 합성 지표 vs 미래 차수만
        "unsupervised_vs_future": capture_metrics(cells, fut_cnt, "unsup_future"),
        # 3) 가중치 섭동 민감도
        "weight_sensitivity": weight_sensitivity(cells),
        # 4) 과거 학습 → 미래 평가 (데이터 산출 가중치)
        "supervised_temporal": supervised_temporal(cells, deft),
        # 5) 이주노동자 렌즈
        "migrant_focus": migrant_focus(cells),
    }

    out_cells = cells.drop(columns=["_z"]).copy()
    out_cells["체불_전체"] = out_cells.apply(
        lambda r: all_cnt.get((r["시도"], r["업종대분류"]), 0), axis=1)
    out_cells["체불_2025이후"] = out_cells.apply(
        lambda r: fut_cnt.get((r["시도"], r["업종대분류"]), 0), axis=1)
    out_cells.sort_values("위험점수", ascending=False).to_csv(
        os.path.join(RES, "cell_risk_table.csv"), index=False,
        encoding="utf-8-sig")

    with open(os.path.join(RES, "cell_screening.json"), "w",
              encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("saved -> results/cell_screening.json, results/cell_risk_table.csv")


if __name__ == "__main__":
    main()
