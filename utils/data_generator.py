"""
합성 데이터 생성 모듈
실제 임금 체불 판례 패턴 기반으로 이주노동자 임금 지급 데이터를 생성합니다.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random


def generate_payment_records(
    n_workplaces: int = 500,
    exploitation_ratio: float = 0.2,
    seed: int = 42,
) -> pd.DataFrame:
    """
    사업장별 임금 지급 기록 생성
    
    착취 패턴 (판례 기반):
    1. 지급 지연형: 매월 지급일이 점점 늦어짐
    2. 임금 삭감형: 계약 대비 실지급액이 감소
    3. 과다 공제형: 숙식비 명목으로 과도한 공제
    4. 초과근무 미지급형: 추가 근무 시간 대비 수당 없음
    """
    np.random.seed(seed)
    random.seed(seed)

    records = []
    n_exploited = int(n_workplaces * exploitation_ratio)

    for workplace_id in range(n_workplaces):
        is_exploited = workplace_id < n_exploited
        exploitation_type = None

        if is_exploited:
            exploitation_type = random.choice([
                "payment_delay",
                "wage_cut",
                "excessive_deduction",
                "overtime_unpaid",
            ])

        n_workers = np.random.randint(3, 20)
        n_months = np.random.randint(6, 24)

        contracted_wage = np.random.choice([2_060_740, 2_500_000, 3_000_000, 3_500_000])
        industry = np.random.choice(["제조업", "농축산업", "건설업", "서비스업"])
        region = np.random.choice(["경기", "충남", "전남", "경북", "경남", "인천"])

        base_date = datetime(2022, 1, 1)
        prev_delay = 0

        for month in range(n_months):
            payment_date = base_date + timedelta(days=30 * month)

            # 지급 지연 패턴
            if is_exploited and exploitation_type == "payment_delay":
                delay = min(prev_delay + np.random.randint(2, 7), 30)
                prev_delay = delay
            else:
                delay = np.random.randint(-2, 3)

            actual_payment_date = payment_date + timedelta(days=int(delay))

            # 실지급액 계산
            overtime_hours = np.random.randint(0, 52)
            overtime_pay = overtime_hours * (contracted_wage / 209) * 1.5

            if is_exploited and exploitation_type == "wage_cut":
                cut_ratio = min(0.1 + month * 0.02, 0.4)
                actual_wage = contracted_wage * (1 - cut_ratio)
            else:
                actual_wage = contracted_wage * np.random.uniform(0.97, 1.03)

            # 공제 항목
            if is_exploited and exploitation_type == "excessive_deduction":
                deduction = contracted_wage * np.random.uniform(0.25, 0.45)
            else:
                deduction = contracted_wage * np.random.uniform(0.05, 0.15)

            # 초과근무 수당 미지급
            if is_exploited and exploitation_type == "overtime_unpaid":
                actual_overtime_pay = overtime_pay * np.random.uniform(0.0, 0.2)
            else:
                actual_overtime_pay = overtime_pay * np.random.uniform(0.9, 1.1)

            records.append({
                "workplace_id": workplace_id,
                "industry": industry,
                "region": region,
                "n_workers": n_workers,
                "month": month,
                "payment_date": actual_payment_date,
                "payment_delay_days": int(delay),
                "contracted_wage": contracted_wage,
                "actual_wage": round(actual_wage),
                "deduction_amount": round(deduction),
                "overtime_hours": overtime_hours,
                "actual_overtime_pay": round(actual_overtime_pay),
                "expected_overtime_pay": round(overtime_pay),
                "is_exploited": int(is_exploited),
                "exploitation_type": exploitation_type if is_exploited else "none",
            })

    df = pd.DataFrame(records)
    df = df.sort_values(["workplace_id", "payment_date"]).reset_index(drop=True)
    return df


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    사업장별 피처 엔지니어링
    LNN 입력을 위한 시계열 피처 생성
    """
    features = []

    for wid, group in df.groupby("workplace_id"):
        group = group.sort_values("payment_date").reset_index(drop=True)

        wage_ratio = group["actual_wage"] / group["contracted_wage"]
        deduction_ratio = group["deduction_amount"] / group["contracted_wage"]
        overtime_ratio = group["actual_overtime_pay"] / (group["expected_overtime_pay"] + 1)

        delay_trend = np.polyfit(range(len(group)), group["payment_delay_days"], 1)[0] if len(group) > 1 else 0.0
        wage_trend = np.polyfit(range(len(group)), wage_ratio, 1)[0] if len(group) > 1 else 0.0

        timestamps = (group["payment_date"] - group["payment_date"].min()).dt.total_seconds().values
        time_gaps = np.diff(timestamps) if len(timestamps) > 1 else np.array([0.0])

        features.append({
            "workplace_id": wid,
            "industry": group["industry"].iloc[0],
            "region": group["region"].iloc[0],
            "n_workers": group["n_workers"].iloc[0],
            "mean_delay": group["payment_delay_days"].mean(),
            "std_delay": group["payment_delay_days"].std(),
            "delay_trend": delay_trend,
            "mean_wage_ratio": wage_ratio.mean(),
            "min_wage_ratio": wage_ratio.min(),
            "wage_trend": wage_trend,
            "mean_deduction_ratio": deduction_ratio.mean(),
            "max_deduction_ratio": deduction_ratio.max(),
            "mean_overtime_ratio": overtime_ratio.mean(),
            "min_overtime_ratio": overtime_ratio.min(),
            "mean_time_gap": time_gaps.mean(),
            "std_time_gap": time_gaps.std(),
            "n_months": len(group),
            "is_exploited": group["is_exploited"].iloc[0],
            "exploitation_type": group["exploitation_type"].iloc[0],
        })

    return pd.DataFrame(features)


if __name__ == "__main__":
    print("데이터 생성 중...")
    df_raw = generate_payment_records(n_workplaces=500, exploitation_ratio=0.2)
    df_raw.to_csv("data/synthetic/payment_records.csv", index=False)
    print(f"원시 데이터 생성 완료: {len(df_raw)}행")

    df_features = compute_features(df_raw)
    df_features.to_csv("data/processed/workplace_features.csv", index=False)
    print(f"피처 데이터 생성 완료: {len(df_features)}개 사업장")
    print(f"착취 사업장: {df_features['is_exploited'].sum()}개 ({df_features['is_exploited'].mean()*100:.0f}%)")
    print(df_features.head())
