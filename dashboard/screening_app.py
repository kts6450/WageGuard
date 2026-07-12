# -*- coding: utf-8 -*-
"""WageGuard — 셀 단위 감독 우선순위 스크리닝 대시보드 (전면 공개 데이터 실증).

실행:  streamlit run dashboard/screening_app.py

이 앱은 승인·로그인이 필요 없는 공개 데이터만 사용한다:
  · 국민연금 가입 사업장 내역(54만 곳) → 위험 신호 3종
  · 고용노동부 임금체불 사업주 공개 명단(789명) → 외부 검증 전용
  · 고용노동부 제조업 E-9 근무현황 → 이주노동자 렌즈
위험 점수는 체불 명단을 전혀 사용하지 않고 산출된다(순환논리 구조적 차단).
"""
from __future__ import annotations

import json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(HERE, "results")
PUB = os.path.join(HERE, "data", "public")

NAVY = "#0F2A43"
TEAL = "#14B8A6"
AMBER = "#F59E0B"
CORAL = "#EF4B4B"
GRAY = "#64748B"
TEAL_SCALE = ["#F0FDFA", "#99F6E4", "#2DD4BF", "#0D9488", "#134E4A"]

st.set_page_config(page_title="WageGuard — 감독 우선순위 스크리닝",
                   page_icon="🛡️", layout="wide")


@st.cache_data(show_spinner=False)
def load_all():
    cells = pd.read_csv(os.path.join(RES, "cell_risk_table.csv"),
                        encoding="utf-8-sig")
    with open(os.path.join(RES, "cell_screening.json"), encoding="utf-8") as f:
        scr = json.load(f)
    deft = pd.read_csv(os.path.join(PUB, "defaulter_list.csv"),
                       encoding="utf-8-sig")
    return cells, scr, deft


def kpi_card(col, label, value, sub, color=TEAL):
    col.markdown(f"""
    <div style='background:white; border:1px solid #E2E8F0;
                border-left:5px solid {color}; padding:14px 16px;
                border-radius:10px'>
      <div style='color:{GRAY}; font-size:0.78rem'>{label}</div>
      <div style='color:{NAVY}; font-size:1.55rem; font-weight:700'>{value}</div>
      <div style='color:{GRAY}; font-size:0.72rem'>{sub}</div>
    </div>""", unsafe_allow_html=True)


def main():
    cells, scr, deft = load_all()
    inp = scr["inputs"]
    u_all = scr["unsupervised_vs_all"]
    u_fut = scr["unsupervised_vs_future"]

    st.markdown(f"""
    <div style='background:linear-gradient(135deg,{NAVY},#1B3A5A);
                padding:22px 30px; border-radius:12px; margin-bottom:14px'>
      <h1 style='color:white; margin:0; font-size:1.7rem'>🛡️ WageGuard — 셀 단위 감독 우선순위 스크리닝</h1>
      <p style='color:#AECDE0; margin:6px 0 0; font-size:0.95rem'>
        전면 공개 행정데이터 실증 · 개별 사업장 지목 없음 · 위험 지표는 체불 명단을 보지 않고 산출
      </p>
    </div>""", unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    kpi_card(c1, "국민연금 사업장 실측", f"{inp['nps_workplaces']//10000}만 곳",
             f"가입자 {inp['nps_insured']/1e4:,.0f}만 명 · {inp['nps_snapshot']}", NAVY)
    kpi_card(c2, "분석 셀 (시도×업종)", f"{inp['n_cells']}개",
             f"셀당 가입자 {inp['min_insured_per_cell']:,}명 이상", TEAL)
    kpi_card(c3, "외부 검증 명단", f"{inp['defaulters_total']}명",
             "임금체불 사업주 공개 명단 (2023~2026)", AMBER)
    kpi_card(c4, "상위 10% 셀 체불 포착", f"{u_all['top10']['lift']}배",
             f"고용 {u_all['top10']['insured_share']:.0%} → 체불 "
             f"{u_all['top10']['capture']:.0%}", CORAL)
    kpi_card(c5, "홀드아웃 차수(25~26) 검증", f"{u_fut['top10']['lift']}배",
             "지표 산출에 전혀 쓰지 않은 명단", CORAL)

    tabs = st.tabs(["📍 위험 지도·우선순위", "⚙️ 탐지 로직", "✅ 검증(외부 명단)",
                    "🌏 이주노동자 렌즈", "📋 데이터·한계"])

    # ------------------------------------------------------------------ 지도
    with tabs[0]:
        left, right = st.columns([3, 2])
        c = cells.copy()
        c["백분위"] = (c["위험점수"].rank(pct=True) * 100).round(0)
        with left:
            top_ind = (c.groupby("업종대분류")["가입자수"].sum()
                       .sort_values(ascending=False).head(12).index)
            sido_order = (c.groupby("시도")["가입자수"].sum()
                          .sort_values(ascending=False).index.tolist())
            mat = (c[c["업종대분류"].isin(top_ind)]
                   .pivot_table(index="업종대분류", columns="시도", values="백분위")
                   .reindex(index=top_ind, columns=sido_order))
            fig = px.imshow(mat, color_continuous_scale=TEAL_SCALE,
                            zmin=0, zmax=100, aspect="auto",
                            labels=dict(color="위험 백분위"))
            fig.update_layout(height=460, margin=dict(l=10, r=10, t=30, b=10),
                              title="시도 × 산업 위험 백분위 (100 = 최고위험)")
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.markdown("**이번 분기 감독 우선순위 (위험 상위 셀)**")
            top = c.sort_values("위험점수", ascending=False).head(12)
            show = top[["시도", "업종대분류", "가입자수", "백분위",
                        "체불_전체"]].rename(columns={
                            "체불_전체": "체불 명단(검증용)"})
            st.dataframe(show, use_container_width=True, hide_index=True,
                         height=420)
            st.caption("체불 명단 열은 사후 검증용 표시 — 위험 점수 산출에는 미사용")

    # ------------------------------------------------------------------ 로직
    with tabs[1]:
        st.markdown("""
        ### 어떻게 '신고 전에' 탐지하는가 — 3단계

        | 단계 | 무엇을 | 어디서 |
        |---|---|---|
        | **1. 신호 수집** | 저임금(1인당 보험료↓) · 고용 불안정(취득+상실↑) · 영세성(5인 미만↑) | 국민연금 월별 신고 (전 사업장 의무) |
        | **2. 셀 점수화** | 시도×업종 셀로 묶어 3신호 표준화(z) 합성 → 위험 점수 | 개별 사업장 지목 없음 |
        | **3. 우선순위** | 위험 상위 셀부터 감독·통역 지원 배정 | 최종 판단은 감독관 |

        **왜 이 3개 신호인가** — 임금을 체불하는 사업장은 그 전에 ① 임금 수준이 낮고(보험료 신고액에 그대로 찍힘)
        ② 근로자가 못 버티고 나가며(상실 급증) ③ 감독이 닿지 않는 영세 규모인 경우가 압도적이다.
        이 세 가지는 **체불이 신고되기 전에** 행정데이터에 먼저 나타나는 선행 신호다.
        """)
        sc = cells.copy()
        sc["체불셀"] = (sc["체불_전체"] > 0).map({True: "체불 명단 포함 셀",
                                                False: "명단 없음"})
        fig = px.scatter(
            sc, x="이직률", y="인당보험료", size="가입자수",
            color="체불셀", color_discrete_map={
                "체불 명단 포함 셀": CORAL, "명단 없음": "#CBD5E1"},
            hover_data=["시도", "업종대분류"], log_y=True, size_max=42)
        fig.update_layout(
            height=440, margin=dict(l=10, r=10, t=40, b=10),
            title="신호가 실제로 갈라놓는다 — 이직률 높고 1인당 보험료 낮은 셀(오른쪽 아래)에 체불 셀이 몰림",
            xaxis_title="고용 불안정 (월 이직률)",
            yaxis_title="임금 수준 프록시 (1인당 보험료, log)")
        st.plotly_chart(fig, use_container_width=True)

    # ------------------------------------------------------------------ 검증
    with tabs[2]:
        st.markdown("""
        ### 순환논리가 **구조적으로 불가능한** 검증
        위험 점수는 **국민연금 데이터만**으로 계산했고, **임금체불 명단은 채점에만** 썼다.
        서로 다른 기관의 독립된 데이터이므로 '답을 미리 보고 맞히는' 일이 성립할 수 없다.
        """)
        c = cells.sort_values("위험점수", ascending=False).reset_index(drop=True)
        ins = c["가입자수"].cumsum() / c["가입자수"].sum()
        cap_all = c["체불_전체"].cumsum() / max(c["체불_전체"].sum(), 1)
        cap_fut = c["체불_2025이후"].cumsum() / max(c["체불_2025이후"].sum(), 1)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines",
                                 name="무작위 점검", line=dict(dash="dash",
                                                          color=GRAY)))
        fig.add_trace(go.Scatter(
            x=ins, y=cap_all, mode="lines",
            name=f"전체 명단 ({int(c['체불_전체'].sum())}명)",
            line=dict(color=NAVY, width=3)))
        fig.add_trace(go.Scatter(
            x=ins, y=cap_fut, mode="lines",
            name=f"홀드아웃 차수 (2025~26, {int(c['체불_2025이후'].sum())}명)",
            line=dict(color=TEAL, width=3)))
        fig.update_layout(height=430, margin=dict(l=10, r=10, t=40, b=10),
                          title="누적 포착 곡선 — 위험 상위 셀부터 점검했을 때",
                          xaxis_title="점검 대상 고용 비중(누적)",
                          yaxis_title="체불 사업주 포착률(누적)")
        st.plotly_chart(fig, use_container_width=True)

        m1, m2, m3 = st.columns(3)
        ws = scr["weight_sensitivity"]
        sup = scr["supervised_temporal"]
        kpi_card(m1, "가중치 민감도 (임의성 반박)",
                 f"ρ = {ws['rho_mean']}",
                 f"무작위 가중 {ws['n_perturb']}조합에도 셀 순위 유지", TEAL)
        kpi_card(m2, "학습 검증 (23~24 학습→25~26 채점)",
                 f"{sup['top10']['lift']}배",
                 f"홀드아웃 차수 상위10% 포착 {sup['top10']['capture']:.0%} "
                 "(참고: 피처는 최신 스냅샷)", NAVY)
        kpi_card(m3, "데이터가 정한 가중치",
                 "이직률 1.0", "저임금 -0.36 · 영세성 0.30 (로지스틱 계수)",
                 AMBER)

    # ------------------------------------------------------------ 이주노동자
    with tabs[3]:
        mp_path = os.path.join(RES, "migrant_priority.csv")
        if os.path.exists(mp_path):
            mp = pd.read_csv(mp_path, encoding="utf-8-sig")
            st.markdown(f"""
            ### 이주노동자 노출-가중 우선순위 — E-9 {int(mp['E9인원'].sum()):,}명 실측 결합
            우선순위 = **E-9 인원(KOSIS 시도×업종) × 셀 위험 백분위** — 두 실측의 곱, 임의 가중 없음.
            '고위험 환경에 노출된 이주노동자 규모' 순서로 통역 동반 점검·모국어 안내를 배정한다.
            """)
            top = mp.head(10).iloc[::-1]
            top["셀"] = top["시도"] + " · " + top["업종대분류"]
            fig = px.bar(top, x="노출가중지수", y="셀", orientation="h",
                         color="위험백분위",
                         color_continuous_scale=["#CBD5E1", TEAL, CORAL],
                         range_color=[0, 100],
                         hover_data=["E9인원", "위험백분위"])
            fig.update_layout(height=420, margin=dict(l=10, r=10, t=40, b=10),
                              title="통역 동반 점검 우선순위 상위 10 셀",
                              xaxis_title="노출-가중 위험 지수", yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(mp.head(15), use_container_width=True,
                         hide_index=True)
            st.info("규모의 축: 경기 제조업(E-9 9.3만) · 농도의 축: 전남/경기/충남 "
                    "농림어업(위험 백분위 84~97). E-9 라벨이 붙은 체불 명단이 "
                    "없어 이주노동자 한정 포착률 검증은 시범 적용 과제로 남긴다.")
        else:
            mf = scr["migrant_focus"]
            st.markdown(f"### 제조업 E-9 {mf['e9_total_mfg']:,}명 (요약)")
            st.info("python scripts/kosis_scrape_e9.py && "
                    "python scripts/build_migrant_priority.py 실행 시 "
                    "노출-가중 우선순위가 표시됩니다.")

    # ------------------------------------------------------------------ 한계
    with tabs[4]:
        st.markdown(f"""
        ### 데이터 출처 (전부 승인·로그인 불필요 공개 데이터)
        | 데이터 | 규모 | 역할 |
        |---|---|---|
        | 국민연금공단 가입 사업장 내역 | {inp['nps_workplaces']:,}곳 / 가입자 {inp['nps_insured']:,}명 | 위험 신호 3종 (지표 산출) |
        | 고용노동부 임금체불 사업주 공개 명단 | {inp['defaulters_total']}명 · 6개 차수 | **검증 전용** (지표에 미사용) |
        | 고용노동부 제조업 E-9 근무현황 | {scr['migrant_focus']['e9_total_mfg']:,}명 | 이주노동자 렌즈 |
        | 한국고용정보원 외국인근로자 근무현황 (EIS) | 분기 통계 | 가점 '나' · 노출 보정(연계) |

        ### 정직한 한계
        - 체불 명단은 **고액·상습 확정자 위주의 선별 표본** — 전수 위반의 대표성엔 한계. 근로감독 결과 통계로 검증 확장 예정.
        - 국민연금 업종코드(구분류)→현행 대분류 **크로스워크는 근사** — 기관 협력 시 사업자번호 기반 정밀화.
        - 셀 내부의 개별 사업장 위험은 구분하지 않음 — 의도된 설계(통계법·개인정보 리스크 차단)이며, 최종 선정은 감독관 몫.
        - LNN 시계열 조기경보는 합성 시뮬레이션 단계 — 고용보험 이력 확보 후 실검증.
        """)


if __name__ == "__main__":
    main()
