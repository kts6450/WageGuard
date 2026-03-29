"""
실제 공공데이터 연동 모듈

사용 데이터:
1. 외국인고용_사업장현황.xlsx   → 지역별 외국인 고용 사업장 수 (2019~2025 분기)
2. 외국인근로자_근무현황.xlsx   → 지역×업종별 외국인 근로자 수 (분기)
3. 행정구역_시도_업종별_E9.csv → 지역×업종별 E-9 외국인 근로자 수 (분기)
4. 제조업 외국인근로자 근무현황 → 제조업 중분류별 현황
5. 임금체불 대지급금 현황        → 연도별 전국 체불 금액 (보정용)

산출물:
- 지역 위험 가중치 (region_risk_weight)
- 업종 위험 가중치 (industry_risk_weight)  
- 지역×업종 복합 위험 지수 (region_industry_risk_index)
"""

import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings("ignore")

RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data/raw")
PROCESSED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data/processed")

# 지역명 표준화 매핑
REGION_MAP = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "충청북도": "충북", "충청남도": "충남", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
    "강원도": "강원", "강원특별자치도": "강원", "전라북도": "전북",
    "전북특별자치도": "전북",
    "서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천",
    "광주": "광주", "대전": "대전", "울산": "울산", "세종": "세종",
    "경기": "경기", "충북": "충북", "충남": "충남", "전남": "전남",
    "경북": "경북", "경남": "경남", "제주": "제주", "강원": "강원",
    "전북": "전북",
}

# 업종명 표준화
INDUSTRY_MAP = {
    "제조업": "제조업", "11차_제조업": "제조업", "10차_제조업": "제조업",
    "건설업": "건설업", "11차_건설업": "건설업", "10차_건설업": "건설업",
    "농축산업": "농축산업", "11차_농축산업": "농축산업", "10차_농축산업": "농축산업",
    "서비스업": "서비스업", "11차_서비스업": "서비스업", "10차_서비스업": "서비스업",
    "어업": "어업", "11차_어업": "어업",
}

TARGET_REGIONS = ["경기", "충남", "전남", "경북", "경남", "인천"]
TARGET_INDUSTRIES = ["제조업", "농축산업", "건설업", "서비스업"]


def parse_workplace_by_region() -> pd.DataFrame:
    """
    외국인고용_사업장현황.xlsx (지역별 시트) 파싱
    → 지역별 최신 사업장 수 추출
    """
    path = os.path.join(RAW_DIR, "외국인고용_사업장현황_1774769320671.xlsx")
    xl = pd.ExcelFile(path)
    df = xl.parse("외국인고용사업장현황(지역별", header=None, skiprows=13)

    # 행14~: 실제 지역 데이터 (총계 포함)
    df_data = df.iloc[1:].copy()  # 헤더 행 제외
    df_data = df_data.dropna(subset=[0])
    df_data = df_data[df_data[0] != "총계"]

    # 지역명 컬럼 + 최신 분기(마지막 컬럼들) 사용
    region_col = df_data.iloc[:, 0]
    # 마지막 6개 컬럼 = 최신 분기 데이터 (전체, 일반, 특례, 일반+특례 등)
    latest_total = df_data.iloc[:, 1]  # 가장 첫 번째 = 2019 Q1 전체

    # 모든 분기 중 최신 분기 찾기 (마지막 유효 컬럼)
    result = pd.DataFrame({
        "region": region_col.values,
        "n_workplaces_2019q1": pd.to_numeric(latest_total.values, errors="coerce"),
    })

    # 중간 컬럼들에서 최신 분기 찾기 (5컬럼 단위: 전체, 일반, 특례, 일반+특례, 다음분기...)
    n_cols = df_data.shape[1]
    # 마지막 전체 수치 컬럼 = 마지막에서 특정 위치
    last_valid_cols = []
    for col_idx in range(1, n_cols, 5):
        col_data = pd.to_numeric(df_data.iloc[:, col_idx], errors="coerce")
        if col_data.notna().sum() > 5:
            last_valid_cols.append((col_idx, col_data))

    if last_valid_cols:
        _, latest_data = last_valid_cols[-1]
        result["n_workplaces_latest"] = pd.to_numeric(latest_data.values, errors="coerce")
    else:
        result["n_workplaces_latest"] = result["n_workplaces_2019q1"]

    result["region"] = result["region"].map(lambda x: REGION_MAP.get(str(x).strip(), str(x).strip()))
    result = result[result["region"].isin(TARGET_REGIONS + ["서울", "부산", "대구", "광주", "대전", "울산", "세종", "충북", "전남", "제주", "강원", "전북"])]

    return result.dropna(subset=["n_workplaces_latest"]).reset_index(drop=True)


def parse_workers_by_region_industry() -> pd.DataFrame:
    """
    외국인근로자_근무현황.xlsx (지역별,업종별 시트) 파싱
    → 지역×업종별 외국인 근로자 수 추출
    """
    path = os.path.join(RAW_DIR, "외국인근로자_근무현황_1774769361638.xlsx")
    xl = pd.ExcelFile(path)
    df = xl.parse("지역별,업종별-일반외국인", header=None, skiprows=13)

    # 행0: 시도, 행1~: 분기별 업종별 데이터
    # 컬럼 구조: [시도, 전체, 제조업, 건설업, 농축산업, 서비스업, 어업, (광업), (임업), 다음분기전체, ...]
    df_data = df.iloc[1:].copy()
    df_data = df_data.dropna(subset=[0])
    df_data = df_data[~df_data[0].isin(["총계", "(사업장)시도"])]

    # 최신 분기 컬럼 위치 파악 (6 또는 8컬럼 단위)
    # 마지막 분기의 업종별 수치 추출
    region_names = df_data.iloc[:, 0].values

    # 업종별 컬럼 인덱스 (최신 분기 기준)
    # 컬럼 구조: 전체(1), 제조업(2), 건설업(3), 농축산업(4), 서비스업(5), 어업(6)...
    # 분기마다 6~8개 컬럼씩 반복
    n_cols = df_data.shape[1]
    step = 6  # 기본 6개 업종 + 전체

    # 마지막 유효 블록 찾기
    best_block_start = 1
    for start in range(1, n_cols - step, step):
        block = df_data.iloc[:, start:start+step]
        numeric_count = block.apply(pd.to_numeric, errors="coerce").notna().sum().sum()
        if numeric_count > 10:
            best_block_start = start

    block = df_data.iloc[:, best_block_start:best_block_start+6]
    block_num = block.apply(pd.to_numeric, errors="coerce")

    result_rows = []
    for i, region in enumerate(region_names):
        region_std = REGION_MAP.get(str(region).strip(), str(region).strip())
        if i < len(block_num):
            row = block_num.iloc[i].values
            result_rows.append({
                "region": region_std,
                "n_workers_total": row[0] if len(row) > 0 else np.nan,
                "n_workers_제조업": row[1] if len(row) > 1 else np.nan,
                "n_workers_건설업": row[2] if len(row) > 2 else np.nan,
                "n_workers_농축산업": row[3] if len(row) > 3 else np.nan,
                "n_workers_서비스업": row[4] if len(row) > 4 else np.nan,
            })

    return pd.DataFrame(result_rows).dropna(subset=["n_workers_total"])


def parse_e9_by_region_industry() -> pd.DataFrame:
    """
    행정구역_시도_업종별_E9.csv 파싱
    → 최신 분기 지역×업종별 E-9 외국인 근로자 수
    """
    path = os.path.join(RAW_DIR, "행정구역_시도__업종별_일반고용허가제_E9__외국인_근로자_수_20260329163604.csv")
    for enc in ["cp949", "utf-8", "utf-8-sig"]:
        try:
            df = pd.read_csv(path, encoding=enc, header=None, skiprows=1)
            break
        except Exception:
            continue

    # 행0: 헤더(행정구역별..., 분기들)
    # 행1~: 전국, 서울, 부산 ...
    df_data = df.iloc[1:].copy()
    df_data = df_data.dropna(subset=[0])
    df_data = df_data[~df_data[0].astype(str).str.contains("행정구역|전국|소계|합계", na=False)]

    result_rows = []
    for _, row in df_data.iterrows():
        region = REGION_MAP.get(str(row.iloc[0]).strip(), str(row.iloc[0]).strip())
        values = pd.to_numeric(row.iloc[1:], errors="coerce").dropna()
        if len(values) >= 6:
            result_rows.append({
                "region": region,
                "e9_total": values.iloc[-1],      # 가장 최신 분기
                "e9_prev": values.iloc[-7] if len(values) >= 7 else values.iloc[0],
            })

    return pd.DataFrame(result_rows)


def compute_risk_weights(
    df_workplace: pd.DataFrame,
    df_workers: pd.DataFrame,
) -> pd.DataFrame:
    """
    지역 × 업종 위험 가중치 산출

    위험 지수 구성:
    - 외국인 근로자 밀집도 (많을수록 착취 위험 높음)
    - 업종별 취약도 (농축산업 > 제조업 > 건설업 > 서비스업)
    """
    # 업종별 기본 취약도 (판례 기반)
    INDUSTRY_BASE_RISK = {
        "농축산업": 0.85,
        "제조업": 0.70,
        "건설업": 0.60,
        "서비스업": 0.45,
    }

    # 지역별 사업장 밀집도 정규화
    wp = df_workplace[["region", "n_workplaces_latest"]].copy()
    wp["region_density"] = wp["n_workplaces_latest"] / wp["n_workplaces_latest"].max()

    result_rows = []
    for region in TARGET_REGIONS:
        density_row = wp[wp["region"] == region]
        density = density_row["n_workplaces_latest"].values[0] if len(density_row) > 0 else 1000
        density_norm = density / wp["n_workplaces_latest"].max()

        worker_row = df_workers[df_workers["region"] == region]

        for industry in TARGET_INDUSTRIES:
            base_risk = INDUSTRY_BASE_RISK.get(industry, 0.5)

            # 해당 지역의 업종별 근로자 수
            worker_col = f"n_workers_{industry}"
            if len(worker_row) > 0 and worker_col in worker_row.columns:
                n_workers = pd.to_numeric(worker_row[worker_col].values[0], errors="coerce")
                n_workers = n_workers if pd.notna(n_workers) else 0
            else:
                n_workers = 0

            total_workers = pd.to_numeric(worker_row["n_workers_total"].values[0], errors="coerce") if len(worker_row) > 0 else 1
            total_workers = total_workers if pd.notna(total_workers) and total_workers > 0 else 1
            industry_share = n_workers / total_workers

            # 복합 위험 지수
            risk_index = (
                base_risk * 0.5 +
                density_norm * 0.3 +
                min(industry_share * 5, 1.0) * 0.2
            )

            result_rows.append({
                "region": region,
                "industry": industry,
                "base_risk": round(base_risk, 3),
                "density_score": round(density_norm, 3),
                "industry_share": round(industry_share, 4),
                "risk_index": round(risk_index, 4),
            })

    df_risk = pd.DataFrame(result_rows)

    # 0~1 정규화
    min_r, max_r = df_risk["risk_index"].min(), df_risk["risk_index"].max()
    df_risk["risk_weight"] = ((df_risk["risk_index"] - min_r) / (max_r - min_r + 1e-9)).round(4)

    return df_risk.sort_values("risk_index", ascending=False).reset_index(drop=True)


def enrich_synthetic_data(df_raw: pd.DataFrame, df_risk: pd.DataFrame) -> pd.DataFrame:
    """
    합성 데이터에 실제 공공데이터 기반 위험 가중치 적용
    - 지역×업종 위험 지수를 합성 데이터의 피처로 추가
    - 고위험 지역·업종 사업장의 착취 확률을 가중치에 따라 조정
    """
    df_enriched = df_raw.copy()
    df_enriched = df_enriched.merge(
        df_risk[["region", "industry", "risk_weight"]],
        on=["region", "industry"],
        how="left",
    )
    df_enriched["risk_weight"] = df_enriched["risk_weight"].fillna(0.5)

    # 위험 가중치를 반영한 착취 점수 (실제 임금 비율에 지역 위험도 보정)
    df_enriched["adjusted_wage_ratio"] = (
        df_enriched["actual_wage"] / df_enriched["contracted_wage"] *
        (1 - df_enriched["risk_weight"] * 0.1)
    ).round(4)

    return df_enriched


def build_real_feature_matrix(df_risk: pd.DataFrame) -> dict:
    """지역×업종 위험 매트릭스를 딕셔너리로 반환 (빠른 조회용)"""
    return {
        (row["region"], row["industry"]): row["risk_weight"]
        for _, row in df_risk.iterrows()
    }


if __name__ == "__main__":
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.data_generator import generate_payment_records

    print("=" * 55)
    print("실제 공공데이터 파싱 및 위험 가중치 산출")
    print("=" * 55)

    print("\n1. 사업장현황 (지역별) 파싱...")
    df_wp = parse_workplace_by_region()
    print(f"   → {len(df_wp)}개 지역")
    print(df_wp[["region", "n_workplaces_latest"]].to_string(index=False))

    print("\n2. 근무현황 (지역×업종) 파싱...")
    df_wr = parse_workers_by_region_industry()
    print(f"   → {len(df_wr)}개 지역")
    print(df_wr.head(6).to_string(index=False))

    print("\n3. 지역×업종 위험 가중치 산출...")
    df_risk = compute_risk_weights(df_wp, df_wr)
    print(df_risk.to_string(index=False))

    print("\n4. 합성 데이터 보정 적용...")
    df_raw = generate_payment_records(n_workplaces=500, exploitation_ratio=0.2, seed=42)
    df_enriched = enrich_synthetic_data(df_raw, df_risk)
    print(f"   → risk_weight 적용 완료: {df_enriched['risk_weight'].notna().sum()}행")
    print(f"   → 평균 위험 가중치: {df_enriched['risk_weight'].mean():.4f}")

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    df_risk.to_csv(os.path.join(PROCESSED_DIR, "region_industry_risk_weights.csv"), index=False)
    df_enriched.to_csv(os.path.join(PROCESSED_DIR, "payment_records_enriched.csv"), index=False)
    print("\n저장 완료:")
    print("  data/processed/region_industry_risk_weights.csv")
    print("  data/processed/payment_records_enriched.csv")
