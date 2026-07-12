# -*- coding: utf-8 -*-
"""WageGuard 운영 파이프라인 — 시군구 × 업종 셀 위험 지표 (실사용 해상도).

감독관 관할 단위(시군구)로 위험 셀을 산출한다.
  - 신호: 국민연금 실측 3종 (저임금 · 고용 불안정 · 영세성)
  - 검증: 임금체불 공개 명단 시군구 매칭 (지표 산출에는 미사용)
  - 이력: 매 실행 시 스냅샷 요약을 results/ops/history.csv 에 적재
          → 다음 달 갱신부터 전월 대비 변화 추적 가능

출력: results/ops/cell_risk_sigungu.csv
      results/ops/ops_summary.json
      results/ops/history.csv (append)
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(HERE, "data", "public")
OPS = os.path.join(HERE, "results", "ops")

MIN_INSURED = int(os.environ.get("WG_OPS_MIN_INSURED", "500"))

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

# 국민연금 업종코드(KSIC 8차 기반) 중분류 → 현행 대분류 명칭 크로스워크
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

TEST_ROUNDS = {"2025년 1차", "2026년 1차"}


def parse_region(addr: str):
    """주소 문자열 → (시도, 시군구). 시군구는 1단계(시·군·구)로 정규화."""
    toks = str(addr).split()
    if not toks:
        return None, None
    sido = SIDO_TEXT.get(toks[0])
    if sido is None:
        return None, None
    if sido == "세종":
        return sido, "세종시"
    if len(toks) < 2:
        return sido, None
    sgg = toks[1]
    if not re.search(r"[시군구]$", sgg):
        return sido, None
    return sido, sgg


def zscore(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / (s.std(ddof=0) + 1e-12)


def load_nps() -> pd.DataFrame:
    path = sorted(glob.glob(os.path.join(PUB, "국민연금공단*가입 사업장 내역*.csv")))[-1]
    df = pd.read_csv(path, encoding="cp949", low_memory=False)
    df = df.rename(columns={
        "사업장가입상태코드 1 등록 2 탈퇴": "상태",
        "사업장업종코드": "업종코드",
    })
    df = df[df["상태"] == 1]
    addr = df["사업장지번상세주소"].fillna(df["사업장도로명상세주소"])
    reg = addr.map(parse_region)
    df["시도"] = reg.str[0]
    df["시군구"] = reg.str[1]
    div = pd.to_numeric(df["업종코드"], errors="coerce").fillna(0).astype(int) // 10000
    df["업종대분류"] = div.map(DIV2SECTION)
    df = df.dropna(subset=["시도", "시군구", "업종대분류"])
    df = df[df["가입자수"] > 0]
    return df


def build_cells(nps: pd.DataFrame) -> pd.DataFrame:
    g = nps.groupby(["시도", "시군구", "업종대분류"])
    cells = pd.DataFrame({
        "사업장수": g.size(),
        "가입자수": g["가입자수"].sum(),
        "고지금액": g["당월고지금액"].sum(),
        "신규취득": g["신규취득자수"].sum(),
        "상실": g["상실가입자수"].sum(),
        "영세비중": g["가입자수"].apply(lambda s: float((s < 5).mean())),
    }).reset_index()
    cells = cells[cells["가입자수"] >= MIN_INSURED].copy()
    cells["인당보험료"] = cells["고지금액"] / cells["가입자수"]
    cells["이직률"] = (cells["신규취득"] + cells["상실"]) / (2 * cells["가입자수"])
    cells["평균규모"] = cells["가입자수"] / cells["사업장수"]
    z_low_wage = -zscore(np.log(cells["인당보험료"]))
    z_churn = zscore(cells["이직률"])
    z_small = zscore(cells["영세비중"])
    cells["신호_저임금"] = z_low_wage.round(3)
    cells["신호_이직률"] = z_churn.round(3)
    cells["신호_영세성"] = z_small.round(3)
    cells["위험점수"] = ((z_low_wage + z_churn + z_small) / 3).round(4)
    cells["위험백분위"] = (cells["위험점수"].rank(pct=True) * 100).round(1)
    return cells


def load_defaulters() -> pd.DataFrame:
    d = pd.read_csv(os.path.join(PUB, "defaulter_list.csv"), encoding="utf-8-sig")
    # 동일 사업주(성명+사업장)의 다차수 재등재 중복 제거 — 최초 차수만 유지
    d = (d.sort_values("공개차수")
         .drop_duplicates(subset=["성명", "사업장명"], keep="first"))
    reg = d["소재지_사업장"].map(parse_region)
    d["시도"] = reg.str[0]
    d["시군구"] = reg.str[1]
    d["업종대분류"] = d["업종"].str.strip().map(
        lambda x: DEFAULTER_IND.get(x, DEFAULTER_IND.get(re.sub(r"\s+", " ", str(x)))))
    return d.dropna(subset=["시도", "시군구", "업종대분류"])


def capture(cells: pd.DataFrame, dcnt: pd.Series) -> dict:
    c = cells.copy()
    c["체불"] = c.apply(
        lambda r: dcnt.get((r["시도"], r["시군구"], r["업종대분류"]), 0), axis=1)
    c = c.sort_values("위험점수", ascending=False)
    tot_def, tot_ins = c["체불"].sum(), c["가입자수"].sum()
    out = {"covered_defaulters": int(tot_def)}
    for frac in (0.1, 0.2):
        k = max(1, int(round(len(c) * frac)))
        top = c.head(k)
        cap = top["체불"].sum() / tot_def if tot_def else 0.0
        share = top["가입자수"].sum() / tot_ins
        out[f"top{int(frac*100)}"] = {
            "cells": int(k), "capture": round(float(cap), 4),
            "insured_share": round(float(share), 4),
            "lift": round(float(cap / share) if share else 0.0, 2)}
    return out


def main():
    os.makedirs(OPS, exist_ok=True)
    nps = load_nps()
    snapshot = str(nps["자료생성년월"].iloc[0])
    cells = build_cells(nps)
    deft = load_defaulters()

    all_cnt = deft.groupby(["시도", "시군구", "업종대분류"]).size()
    fut_cnt = deft[deft["공개차수"].isin(TEST_ROUNDS)].groupby(
        ["시도", "시군구", "업종대분류"]).size()
    cells["체불_전체"] = cells.apply(
        lambda r: all_cnt.get((r["시도"], r["시군구"], r["업종대분류"]), 0), axis=1)
    cells["체불_2025이후"] = cells.apply(
        lambda r: fut_cnt.get((r["시도"], r["시군구"], r["업종대분류"]), 0), axis=1)

    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "nps_snapshot": snapshot,
        "workplaces": int(len(nps)),
        "insured": int(nps["가입자수"].sum()),
        "n_cells": int(len(cells)),
        "min_insured_per_cell": MIN_INSURED,
        "defaulters_mapped": int(len(deft)),
        "validation_all": capture(cells, all_cnt),
        "validation_future": capture(cells, fut_cnt),
    }

    out_csv = os.path.join(OPS, "cell_risk_sigungu.csv")
    cells.sort_values("위험점수", ascending=False).to_csv(
        out_csv, index=False, encoding="utf-8-sig")
    with open(os.path.join(OPS, "ops_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 스냅샷 이력 적재 (전월 대비 추적용) — 셀별 핵심 수치 축적
    hist_path = os.path.join(OPS, "history.csv")
    hist_cols = ["스냅샷", "시도", "시군구", "업종대분류", "가입자수",
                 "위험점수", "위험백분위", "이직률", "인당보험료"]
    h = cells[["시도", "시군구", "업종대분류", "가입자수", "위험점수",
               "위험백분위", "이직률", "인당보험료"]].copy()
    h.insert(0, "스냅샷", snapshot)
    if os.path.exists(hist_path):
        prev = pd.read_csv(hist_path, encoding="utf-8-sig")
        prev = prev[prev["스냅샷"] != snapshot]  # 같은 달 재실행 시 교체
        h = pd.concat([prev, h[hist_cols]], ignore_index=True)
    h.to_csv(hist_path, index=False, encoding="utf-8-sig")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("saved ->", out_csv)


if __name__ == "__main__":
    main()
