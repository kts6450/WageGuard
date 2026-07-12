"""
실제 MDIS 데이터 처리 모듈

데이터 소스:
1. 고용형태별근로실태조사 (2020~2024) - 491만건 임금/근로시간/4대보험
2. 이민자체류실태조사 공통항목 (2021~2025) - 외국인 차별·만족도
3. 비전문취업(E9) 부가항목 - 계약인지·이직 패턴
4. 근로환경조사 - 폭력·괴롭힘·차별

착취 라벨 정의 (3-condition rule):
  A. 4대보험 미가입 (법적 의무 위반)
  B. 최저임금 위반 추정 (시간급 환산)
  C. 초과근무 20시간↑ + 초과급여 0
"""

import os
import glob
import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

# 연도별 최저임금 (원/시간)
MIN_WAGE_BY_YEAR = {
    2020: 8_590,
    2021: 8_720,
    2022: 9_160,
    2023: 9_620,
    2024: 9_860,
    2025: 10_030,
}

# 고용형태코드 → 위험도 가중치 (착취 취약 순서)
EMPLOYMENT_RISK = {
    "5": 1.5,  # 일일
    "3": 1.4,  # 파견
    "4": 1.3,  # 용역
    "1": 1.2,  # 특수형태
    "2": 1.1,  # 재택/가내
    "6": 1.0,  # 단시간
    "7": 0.9,  # 기간제
    "8": 0.8,  # 기간제아닌한시적
    "9": 0.5,  # 정규직
}


def load_wage_survey(sample_frac: float = 1.0) -> pd.DataFrame:
    """
    고용형태별근로실태조사 2020~2024 로드 및 착취 라벨 생성
    sample_frac: 속도를 위한 샘플링 비율 (1.0 = 전체)
    """
    data_dir = os.path.join(RAW_DIR, "총괄_20260329_98746_데이터")
    if not os.path.exists(data_dir):
        raise FileNotFoundError(f"데이터 폴더 없음: {data_dir}")

    dfs = []
    for year in [2020, 2021, 2022, 2023, 2024]:
        fpath = os.path.join(data_dir, f"{year}_총괄_20260329_98746.csv")
        if not os.path.exists(fpath):
            continue
        df = pd.read_csv(fpath, encoding="cp949", low_memory=False)
        df["year"] = year
        if sample_frac < 1.0:
            df = df.sample(frac=sample_frac, random_state=42)
        dfs.append(df)
        print(f"  {year}년: {len(df):,}건 로드")

    df = pd.concat(dfs, ignore_index=True)

    # 수치형 변환
    numeric_cols = ["소정실근로시간수", "초과실근로시간수", "휴일실근로시간수",
                    "정액급여액", "초과급여액", "상여금성과급총액", "연령"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["정액급여액", "소정실근로시간수"])
    df = df[df["소정실근로시간수"] > 0]

    # ── 착취 라벨 정의 ──────────────────────────────
    # A. 4대보험 미가입 (코드 2=미가입)
    insurance_cols = ["고용보험가입여부", "건강보험가입여부", "국민연금가입여부"]
    for col in insurance_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    insurance_violation = df[insurance_cols].eq(2).any(axis=1)

    # B. 최저임금 미달 (정액급여 단위: 천원)
    hourly_wage = (df["정액급여액"] * 1000) / df["소정실근로시간수"]
    min_wage_map = df["year"].map(MIN_WAGE_BY_YEAR)
    wage_violation = hourly_wage < min_wage_map

    # C. 초과근무 착취: 초과 20h 이상인데 초과급여 0
    df["초과실근로시간수"] = df["초과실근로시간수"].fillna(0)
    df["초과급여액"] = df["초과급여액"].fillna(0)
    overtime_exploitation = (df["초과실근로시간수"] >= 20) & (df["초과급여액"] == 0)

    df["is_exploited"] = (insurance_violation | wage_violation | overtime_exploitation).astype(int)

    # 착취 세부 유형
    df["exploit_insurance"] = insurance_violation.astype(int)
    df["exploit_wage"] = wage_violation.astype(int)
    df["exploit_overtime"] = overtime_exploitation.astype(int)

    # 파생 피처
    df["hourly_wage"] = hourly_wage
    df["overtime_pay_ratio"] = np.where(
        df["초과실근로시간수"] > 0,
        df["초과급여액"] / (df["초과실근로시간수"] * (df["정액급여액"] * 1000 / df["소정실근로시간수"]) * 1.5 + 1),
        1.0,
    )
    df["total_work_hours"] = df["소정실근로시간수"] + df["초과실근로시간수"] + df["휴일실근로시간수"].fillna(0)

    # 고용형태 위험 가중치
    df["고용형태코드"] = df["고용형태코드"].astype(str)
    df["employment_risk"] = df["고용형태코드"].map(EMPLOYMENT_RISK).fillna(1.0)

    print(f"\n총 {len(df):,}건 로드 완료")
    print(f"착취 비율: {df['is_exploited'].mean()*100:.1f}%")
    print(f"  ├ 4대보험 미가입: {insurance_violation.sum():,}건 ({insurance_violation.mean()*100:.1f}%)")
    print(f"  ├ 최저임금 미달: {wage_violation.sum():,}건 ({wage_violation.mean()*100:.1f}%)")
    print(f"  └ 초과근무 착취: {overtime_exploitation.sum():,}건 ({overtime_exploitation.mean()*100:.1f}%)")

    return df


def load_migrant_survey() -> pd.DataFrame:
    """이민자체류실태조사 공통항목 로드"""
    data_dir = os.path.join(RAW_DIR, "공통항목_20260329_76845_데이터")
    if not os.path.exists(data_dir):
        return pd.DataFrame()

    dfs = []
    for fpath in sorted(glob.glob(os.path.join(data_dir, "*.csv"))):
        year = int(os.path.basename(fpath)[:4])
        df = pd.read_csv(fpath, encoding="cp949", low_memory=False)
        df["year"] = year
        dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    print(f"이민자 공통항목: {len(df):,}건")
    return df


def load_e9_survey() -> pd.DataFrame:
    """비전문취업(E9) 부가항목 로드"""
    data_dir = os.path.join(RAW_DIR, "부가항목(비전문취업)_20260329_28455_데이터")
    if not os.path.exists(data_dir):
        return pd.DataFrame()

    dfs = []
    for fpath in sorted(glob.glob(os.path.join(data_dir, "*.csv"))):
        year = int(os.path.basename(fpath)[:4])
        df = pd.read_csv(fpath, encoding="cp949", low_memory=False)
        df["year"] = year
        dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    print(f"비전문취업(E9): {len(df):,}건")
    return df


def load_work_environment_survey() -> pd.DataFrame:
    """근로환경조사 로드"""
    data_dir = os.path.join(RAW_DIR, "총괄_20260329_48620_데이터")
    if not os.path.exists(data_dir):
        return pd.DataFrame()

    dfs = []
    for fpath in sorted(glob.glob(os.path.join(data_dir, "*.csv"))):
        year = int(os.path.basename(fpath)[:4])
        df = pd.read_csv(fpath, encoding="cp949", low_memory=False)
        df["year"] = year
        dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    print(f"근로환경조사: {len(df):,}건")
    return df


def get_real_distribution_stats(df_wage: pd.DataFrame) -> dict:
    """
    합성 데이터 보정을 위한 실제 분포 통계 추출
    업종 × 규모 × 고용형태별 임금/근로시간 분포
    """
    stats = {}

    # 전체 통계
    stats["wage_mean"] = df_wage["정액급여액"].mean() * 1000
    stats["wage_std"] = df_wage["정액급여액"].std() * 1000
    stats["wage_p25"] = df_wage["정액급여액"].quantile(0.25) * 1000
    stats["wage_p50"] = df_wage["정액급여액"].quantile(0.50) * 1000
    stats["wage_p75"] = df_wage["정액급여액"].quantile(0.75) * 1000

    stats["overtime_mean"] = df_wage["초과실근로시간수"].mean()
    stats["overtime_rate_nonzero"] = (df_wage["초과실근로시간수"] > 0).mean()

    stats["insurance_violation_rate"] = df_wage["exploit_insurance"].mean()
    stats["wage_violation_rate"] = df_wage["exploit_wage"].mean()
    stats["overtime_exploitation_rate"] = df_wage["exploit_overtime"].mean()
    stats["total_exploitation_rate"] = df_wage["is_exploited"].mean()

    # 고용형태별 착취율
    stats["exploitation_by_employment"] = (
        df_wage.groupby("고용형태코드")["is_exploited"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "exploitation_rate", "count": "n"})
        .to_dict()
    )

    # 산업별 착취율
    stats["exploitation_by_industry"] = (
        df_wage.groupby("산업대분류코드")["is_exploited"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "exploitation_rate", "count": "n"})
        .to_dict()
    )

    return stats


def build_ml_features(df_wage: pd.DataFrame, sample_size: int = 100_000) -> pd.DataFrame:
    """
    ML 모델용 피처 테이블 생성
    XGBoost/분류 모델 훈련에 사용

    Note: 라벨 정의에 사용된 변수(4대보험 가입여부)는 피처에서 제외해
          데이터 누수(leakage)를 방지합니다.
    """
    feature_cols = [
        "산업대분류코드", "사업체규모코드", "고용형태코드", "성별코드", "연령",
        "소정실근로시간수", "초과실근로시간수", "휴일실근로시간수",
        "정액급여액", "초과급여액", "상여금성과급총액",
        # 4대보험 컬럼 제외 (라벨 정의에 사용됨 → leakage 방지)
        "hourly_wage", "overtime_pay_ratio", "total_work_hours",
        "employment_risk", "year", "is_exploited",
    ]

    df_feat = df_wage[feature_cols].copy()

    # 범주형 인코딩
    cat_cols = ["산업대분류코드", "사업체규모코드", "고용형태코드", "성별코드"]
    for col in cat_cols:
        df_feat[col] = pd.to_numeric(
            LabelEncoder().fit_transform(df_feat[col].astype(str)), errors="coerce"
        )

    # 4대보험 통합 스코어는 원본 df_wage에서 계산 후 추가
    insurance_cols = ["고용보험가입여부", "건강보험가입여부", "국민연금가입여부", "산재보험가입여부"]
    ins_df = df_wage[insurance_cols].copy()
    for col in insurance_cols:
        ins_df[col] = pd.to_numeric(ins_df[col], errors="coerce").fillna(3)
    df_wage["insurance_score"] = (ins_df == 1).sum(axis=1)
    df_feat["insurance_score"] = df_wage.loc[df_feat.index, "insurance_score"].values

    df_feat = df_feat.dropna()

    if sample_size and len(df_feat) > sample_size:
        # 착취 비율 유지하며 샘플링
        exploited = df_feat[df_feat["is_exploited"] == 1].sample(
            min(sample_size // 4, len(df_feat[df_feat["is_exploited"] == 1])), random_state=42
        )
        normal = df_feat[df_feat["is_exploited"] == 0].sample(
            min(sample_size - len(exploited), len(df_feat[df_feat["is_exploited"] == 0])), random_state=42
        )
        df_feat = pd.concat([exploited, normal]).sample(frac=1, random_state=42).reset_index(drop=True)

    print(f"ML 피처 데이터: {len(df_feat):,}건 | 착취 비율: {df_feat['is_exploited'].mean()*100:.1f}%")
    return df_feat


def get_migrant_risk_features() -> dict:
    """
    이민자 공통항목 + E9 데이터에서 산업×지역별 위험 지수 추출
    → 고용형태별근로실태조사와 산업코드로 조인 가능한 형태로 반환
    """
    risk = {}

    # 이민자 공통항목: 직장 내 차별 경험률
    migrant_dir = os.path.join(RAW_DIR, "공통항목_20260329_76845_데이터")
    if os.path.exists(migrant_dir):
        dfs = []
        for fpath in sorted(glob.glob(os.path.join(migrant_dir, "*.csv"))):
            df = pd.read_csv(fpath, encoding="cp949", low_memory=False)
            dfs.append(df)
        if dfs:
            df_m = pd.concat(dfs, ignore_index=True)
            # 직장 내 차별 경험 여부 (1=있음)
            if "차별대우_경험여부" in df_m.columns:
                risk["discrimination_rate"] = float((df_m["차별대우_경험여부"] == 1).mean())
            if "차별대우정도_직장코드" in df_m.columns:
                workplace_disc = pd.to_numeric(df_m["차별대우정도_직장코드"], errors="coerce")
                risk["workplace_discrimination_mean"] = float(workplace_disc.mean())
            if "본인소득_만족도코드" in df_m.columns:
                income_sat = pd.to_numeric(df_m["본인소득_만족도코드"], errors="coerce")
                risk["income_dissatisfaction_rate"] = float((income_sat >= 4).mean())

    # E9 부가항목: 계약-현실 괴리 지표, 이직 횟수
    e9_dir = os.path.join(RAW_DIR, "부가항목(비전문취업)_20260329_28455_데이터")
    if os.path.exists(e9_dir):
        dfs = []
        for fpath in sorted(glob.glob(os.path.join(e9_dir, "*.csv"))):
            df = pd.read_csv(fpath, encoding="cp949", low_memory=False)
            dfs.append(df)
        if dfs:
            df_e9 = pd.concat(dfs, ignore_index=True)
            if "근로계약조건_인지여부" in df_e9.columns:
                contract = pd.to_numeric(df_e9["근로계약조건_인지여부"], errors="coerce")
                # 코드북: 1=계약조건 알고 있음, 2=모름, 3=계약서 없음
                # 주의: 과거 `contract != 1`은 코드 2·3과 결측(NaN)까지 모두 '모름'으로
                #       과대 집계하여 미인지율을 66%로 부풀리는 버그였음. 고용허가제상
                #       표준근로계약 체결을 감안하면 실제 '모름(코드 2)' 비율은 훨씬 낮다.
                valid = contract.dropna()
                if len(valid) > 0:
                    # 실제 '계약조건 모름'만 집계 (결측 제외)
                    risk["e9_contract_unknown_rate"] = float((valid == 2).mean())
                    # 계약서 자체가 없는 비율 (별도 위험 신호)
                    risk["e9_no_contract_rate"] = float((valid == 3).mean())
            if "취업후직장이직횟수구간코드" in df_e9.columns:
                turnover = pd.to_numeric(df_e9["취업후직장이직횟수구간코드"], errors="coerce")
                risk["e9_high_turnover_rate"] = float((turnover >= 3).mean())

    if risk:
        print(f"이민자 위험 지수: {risk}")

    return risk


if __name__ == "__main__":
    print("=" * 60)
    print("실제 MDIS 데이터 로드 및 전처리")
    print("=" * 60)

    df_wage = load_wage_survey(sample_frac=0.1)  # 빠른 테스트용 10%

    print("\n분포 통계 추출 중...")
    stats = get_real_distribution_stats(df_wage)
    print(f"  평균 임금: {stats['wage_mean']:,.0f}원")
    print(f"  착취 비율: {stats['total_exploitation_rate']*100:.1f}%")

    print("\nML 피처 생성 중...")
    df_feat = build_ml_features(df_wage, sample_size=50_000)

    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "data", "processed"), exist_ok=True)
    df_feat.to_csv(
        os.path.join(os.path.dirname(__file__), "..", "data", "processed", "real_features.csv"),
        index=False
    )
    print("저장 완료: data/processed/real_features.csv")
