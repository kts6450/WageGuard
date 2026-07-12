"""
임금 착취 탐지 시스템 대시보드
실제 MDIS 공공 데이터 기반 분석 결과 시각화
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.contest_data_sources import contest_expander_markdown

st.set_page_config(
    page_title="임금 착취 탐지 시스템",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")

INDUSTRY_MAP = {
    "A": "농업·임업·어업", "B": "광업", "C": "제조업",
    "D": "전기·가스", "E": "수도·폐기물", "F": "건설업",
    "G": "도·소매업", "H": "운수·창고", "I": "숙박·음식점",
    "J": "정보통신", "K": "금융·보험", "L": "부동산",
    "M": "전문·과학기술", "N": "사업지원서비스", "P": "교육서비스",
    "Q": "보건·사회복지", "R": "예술·여가", "S": "기타서비스",
}

EMPLOYMENT_MAP = {
    "1": "특수형태", "2": "재택/가내", "3": "파견",
    "4": "용역", "5": "일일", "6": "단시간",
    "7": "기간제", "8": "기간제아닌한시적", "9": "정규직",
}


@st.cache_data(show_spinner=False)
def load_wage_data(sample_frac: float = 0.02):
    from utils.real_data_processor import load_wage_survey
    return load_wage_survey(sample_frac=sample_frac)


@st.cache_data(show_spinner=False)
def load_pipeline_results():
    fpath = os.path.join(RESULTS_DIR, "pipeline_results.json")
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def render_header():
    st.markdown("""
    <div style='background: linear-gradient(135deg,#1e3a5f,#2d6a9f); padding:24px 32px; border-radius:12px; margin-bottom:16px'>
        <h1 style='color:white; margin:0; font-size:2rem'>🔍 이주노동자 임금 착취 탐지 시스템</h1>
        <p style='color:#aecde0; margin:6px 0 0'>
            고용형태별근로실태조사 491만건 + 이민자체류실태조사 + 근로환경조사 기반 실증 분석
        </p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("제5회 고용노동 공공데이터·AI 활용 공모전 — 데이터·AI 출처 요약"):
        st.markdown(contest_expander_markdown())


def render_kpi(df: pd.DataFrame, results: dict):
    total = len(df) * 50  # 2% 샘플 기준 역산
    exploit_rate = df["is_exploited"].mean()
    ins_rate = df["exploit_insurance"].mean()
    wage_rate = df["exploit_wage"].mean()

    col1, col2, col3, col4, col5 = st.columns(5)
    metrics = [
        ("분석 데이터", f"{total/10000:.0f}만건", "실제 공공 마이크로데이터"),
        ("전체 착취 비율", f"{exploit_rate*100:.1f}%", f"{int(total*exploit_rate/10000):.0f}만명 추정"),
        ("4대보험 미가입", f"{ins_rate*100:.1f}%", "법적 의무 위반"),
        ("최저임금 미달", f"{wage_rate*100:.1f}%", "임금체불 추정"),
        ("XGBoost AUROC", f"{results['model_performance']['XGBoost (실제 데이터)']['auroc']:.4f}" if results else "학습 전",
         "실제 데이터 기반"),
    ]
    colors = ["#2196F3", "#F44336", "#FF9800", "#9C27B0", "#4CAF50"]
    for col, (label, val, sub), color in zip([col1, col2, col3, col4, col5], metrics, colors):
        with col:
            st.markdown(f"""
            <div style='background:#1e1e2e; border-left:4px solid {color};
                        padding:16px; border-radius:8px; text-align:center'>
                <div style='color:#888; font-size:0.75rem'>{label}</div>
                <div style='color:white; font-size:1.6rem; font-weight:700'>{val}</div>
                <div style='color:#666; font-size:0.7rem'>{sub}</div>
            </div>""", unsafe_allow_html=True)


# ────────────────────────────────────────────────
# TAB 1: 실제 데이터 분석
# ────────────────────────────────────────────────

def tab_real_data(df: pd.DataFrame):
    st.subheader("실제 고용형태별근로실태조사 분석")
    st.caption(f"샘플: {len(df):,}건 (전체 491만건 중 2%) | 2020~2024년 5개년")

    col1, col2 = st.columns(2)

    with col1:
        # 착취 유형별 비율
        exploit_counts = {
            "4대보험 미가입": df["exploit_insurance"].sum(),
            "최저임금 미달": df["exploit_wage"].sum(),
            "초과근무 착취": df["exploit_overtime"].sum(),
        }
        fig = px.bar(
            x=list(exploit_counts.keys()),
            y=list(exploit_counts.values()),
            color=list(exploit_counts.keys()),
            color_discrete_sequence=["#F44336", "#FF9800", "#9C27B0"],
            title="착취 유형별 발생 건수",
            labels={"x": "착취 유형", "y": "건수"},
        )
        fig.update_layout(showlegend=False, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                          font_color="white")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # 산업별 착취율
        df["산업명"] = df["산업대분류코드"].map(INDUSTRY_MAP).fillna(df["산업대분류코드"])
        industry_exploit = (
            df.groupby("산업명")["is_exploited"].agg(["mean", "count"])
            .rename(columns={"mean": "착취율", "count": "건수"})
            .sort_values("착취율", ascending=False)
            .head(10)
        )
        fig = px.bar(
            industry_exploit.reset_index(),
            x="착취율", y="산업명",
            orientation="h",
            color="착취율",
            color_continuous_scale="RdYlGn_r",
            title="산업별 착취율 Top 10",
        )
        fig.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="white",
                          yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        # 고용형태별 착취율
        df["고용형태명"] = df["고용형태코드"].astype(str).map(EMPLOYMENT_MAP).fillna("기타")
        emp_exploit = (
            df.groupby("고용형태명")["is_exploited"].mean()
            .sort_values(ascending=False)
        )
        fig = px.bar(
            x=emp_exploit.index,
            y=emp_exploit.values * 100,
            color=emp_exploit.values,
            color_continuous_scale="RdYlGn_r",
            title="고용형태별 착취율 (%)",
            labels={"x": "고용형태", "y": "착취율 (%)"},
        )
        fig.update_layout(showlegend=False, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                          font_color="white")
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        # 임금 분포 (착취 vs 정상)
        df_normal = df[df["is_exploited"] == 0]["정액급여액"].clip(0, 10000)
        df_exploit = df[df["is_exploited"] == 1]["정액급여액"].clip(0, 10000)
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=df_normal, name="정상", opacity=0.7,
                                   nbinsx=50, marker_color="#4CAF50"))
        fig.add_trace(go.Histogram(x=df_exploit, name="착취", opacity=0.7,
                                   nbinsx=50, marker_color="#F44336"))
        fig.update_layout(
            barmode="overlay",
            title="정액급여 분포 비교 (단위: 천원)",
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="white",
            legend=dict(bgcolor="#1e1e2e"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # 연도별 트렌드
    st.markdown("---")
    st.subheader("연도별 착취 지표 추이")
    yearly = df.groupby("year").agg(
        착취율=("is_exploited", "mean"),
        보험미가입률=("exploit_insurance", "mean"),
        최저임금미달률=("exploit_wage", "mean"),
        평균임금=("정액급여액", "mean"),
    ).reset_index()
    yearly["착취율"] *= 100
    yearly["보험미가입률"] *= 100
    yearly["최저임금미달률"] *= 100

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for col, color in [("착취율", "#F44336"), ("보험미가입률", "#FF9800"), ("최저임금미달률", "#9C27B0")]:
        fig.add_trace(go.Scatter(x=yearly["year"], y=yearly[col], name=col,
                                  line=dict(color=color, width=2)), secondary_y=False)
    fig.add_trace(go.Bar(x=yearly["year"], y=yearly["평균임금"], name="평균임금(천원)",
                          marker_color="#2196F3", opacity=0.3), secondary_y=True)
    fig.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="white",
                       legend=dict(bgcolor="#1e1e2e"))
    fig.update_yaxes(title_text="비율 (%)", secondary_y=False)
    fig.update_yaxes(title_text="평균임금 (천원)", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)


# ────────────────────────────────────────────────
# TAB 2: 모델 성능 비교
# ────────────────────────────────────────────────

def tab_model_performance(results: dict):
    if not results:
        st.warning("학습 결과가 없습니다. 먼저 파이프라인을 실행하세요.")
        st.code("python models/train_pipeline.py --sample 0.1")
        return

    st.subheader("모델 성능 비교")

    perf = results["model_performance"]
    df_perf = pd.DataFrame([
        {
            "모델": name,
            "AUROC": m["auroc"],
            "F1-score": m["f1"],
            "AP (Average Precision)": m["ap"],
            "데이터 유형": "실제 데이터" if m["data_type"] == "real" else "합성 시계열(보정)",
        }
        for name, m in perf.items()
    ])

    col1, col2 = st.columns(2)

    with col1:
        fig = px.bar(
            df_perf, x="모델", y="AUROC",
            color="데이터 유형",
            color_discrete_map={"실제 데이터": "#2196F3", "합성 시계열(보정)": "#4CAF50"},
            title="모델별 AUROC",
            text_auto=".4f",
        )
        fig.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="white",
                           legend=dict(bgcolor="#1e1e2e"), yaxis_range=[0.9, 1.01])
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.bar(
            df_perf.melt(id_vars=["모델", "데이터 유형"],
                          value_vars=["AUROC", "F1-score", "AP (Average Precision)"],
                          var_name="지표", value_name="값"),
            x="모델", y="값", color="지표",
            barmode="group",
            title="모델별 성능 지표 종합",
            text_auto=".3f",
        )
        fig.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="white",
                           legend=dict(bgcolor="#1e1e2e"))
        st.plotly_chart(fig, use_container_width=True)

    # 피처 중요도
    st.markdown("---")
    st.subheader("XGBoost 피처 중요도 (실제 데이터 기반)")
    feat_imp = results.get("feature_importance", {})
    if feat_imp:
        df_fi = pd.DataFrame(list(feat_imp.items()), columns=["피처", "중요도"]).sort_values("중요도")
        fig = px.bar(df_fi, x="중요도", y="피처", orientation="h",
                     color="중요도", color_continuous_scale="Blues",
                     title="Top 15 피처 중요도")
        fig.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="white",
                           height=500)
        st.plotly_chart(fig, use_container_width=True)

    # 실제 데이터 통계
    st.markdown("---")
    st.subheader("실제 데이터 기반 통계")
    stats = results.get("real_data_stats", {})
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("분석 레코드", f"{stats.get('total_records',0)*50:,}건", "전체 환산")
        col2.metric("착취 비율", f"{stats.get('exploitation_rate',0)*100:.1f}%", "3개 조건 기반")
        col3.metric("평균 임금", f"{stats.get('wage_mean',0)/10000:.0f}만원", "정액급여 기준")
        col4.metric("중간 임금", f"{stats.get('wage_p50',0)/10000:.0f}만원", "50th percentile")


# ────────────────────────────────────────────────
# TAB 3: E9 이주노동자 분석
# ────────────────────────────────────────────────

def tab_migrant_analysis():
    st.subheader("E9 비전문취업 이주노동자 분석")

    data_dir = os.path.join(RAW_DIR, "부가항목(비전문취업)_20260329_28455_데이터")
    if not os.path.exists(data_dir):
        st.warning("E9 데이터 없음")
        return

    import glob
    dfs = []
    for fpath in sorted(glob.glob(os.path.join(data_dir, "*.csv"))):
        year = int(os.path.basename(fpath)[:4])
        df = pd.read_csv(fpath, encoding="cp949", low_memory=False)
        df["year"] = year
        dfs.append(df)

    df_e9 = pd.concat(dfs, ignore_index=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### 근로계약 인지 여부")
        contract_counts = df_e9["근로계약조건_인지여부"].value_counts()
        labels = {1: "계약조건 알고 있음", 2: "모름", 3: "계약서 없음"}
        contract_df = pd.DataFrame({
            "상태": [labels.get(k, str(k)) for k in contract_counts.index],
            "건수": contract_counts.values,
        })
        fig = px.pie(contract_df, values="건수", names="상태",
                     color_discrete_sequence=["#4CAF50", "#F44336", "#FF9800"],
                     title="계약조건 인지 여부 (E9 근로자)")
        fig.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="white")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("##### 이직 횟수 분포")
        df_e9["이직횟수"] = pd.to_numeric(df_e9["취업후직장이직횟수구간코드"], errors="coerce")
        idc = df_e9["이직횟수"].value_counts().sort_index()
        idc_labels = {1: "0회", 2: "1회", 3: "2회", 4: "3회", 5: "4회이상"}
        fig = px.bar(
            x=[idc_labels.get(k, str(k)) for k in idc.index],
            y=idc.values,
            color=idc.values,
            color_continuous_scale="RdYlGn_r",
            title="직장 이직 횟수 (빈번한 이직 = 착취 신호)",
            labels={"x": "이직 횟수", "y": "근로자 수"},
        )
        fig.update_layout(showlegend=False, plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                           font_color="white")
        st.plotly_chart(fig, use_container_width=True)

    # 이직 어려움
    st.markdown("---")
    col3, col4 = st.columns(2)

    with col3:
        st.markdown("##### 이직 시 어려움 (사업장 변경 제한이 착취 구조의 핵심)")
        if "이직시힘들었던점" in df_e9.columns:
            hard = df_e9["이직시힘들었던점"].value_counts().head(8)
            fig = px.bar(x=hard.values, y=hard.index.astype(str), orientation="h",
                         title="이직 시 어려움 코드 분포",
                         labels={"x": "건수", "y": "코드"})
            fig.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="white")
            st.plotly_chart(fig, use_container_width=True)

    with col4:
        st.markdown("##### 연도별 E9 근로자 현황")
        yearly_e9 = df_e9.groupby("year").size().reset_index(name="건수")
        fig = px.line(yearly_e9, x="year", y="건수", markers=True,
                      title="연도별 E9 조사 건수",
                      color_discrete_sequence=["#2196F3"])
        fig.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="white")
        st.plotly_chart(fig, use_container_width=True)

    st.info(f"E9 데이터 총 {len(df_e9):,}건 | {df_e9['year'].unique().tolist()} 년도")


# ────────────────────────────────────────────────
# TAB 3: LNN 핵심 실험
# ────────────────────────────────────────────────

def tab_lnn_experiment():
    st.subheader("LNN vs LSTM: 불규칙 시계열 비교 실험")

    st.markdown("""
    **핵심 질문**: 왜 LSTM 대신 LNN을 써야 하는가?

    임금 지급은 **불규칙한 시간 간격**으로 발생합니다.
    착취 사업장일수록 지급이 지연되고 간격이 불규칙합니다.
    LNN(CfC)은 이 불규칙성을 연속시간 ODE로 직접 처리하지만,
    LSTM은 등간격 시계열을 가정합니다.
    """)

    exp_path = os.path.join(RESULTS_DIR, "lnn_experiment_summary.json")
    img_path = os.path.join(RESULTS_DIR, "lnn_vs_lstm_experiment.png")

    # 핵심 지표 카드
    if os.path.exists(exp_path):
        with open(exp_path) as f:
            exp = json.load(f)

        col1, col2, col3 = st.columns(3)
        with col1:
            lnn_ep = exp["convergence"]["LNN_epoch_to_90pct"]
            lstm_ep = exp["convergence"]["LSTM_epoch_to_90pct"]
            diff_ep = lstm_ep - lnn_ep
            st.metric(
                "수렴 속도 우위",
                f"LNN: {lnn_ep}에포크",
                delta=f"LSTM보다 {diff_ep}에포크 빠름",
                delta_color="normal"
            )
        with col2:
            lnn_3m = exp["early_detection"].get("seq_3_LNN") or exp["early_detection"].get("seq_6_LNN", 0)
            lstm_3m = exp["early_detection"].get("seq_3_LSTM") or exp["early_detection"].get("seq_6_LSTM", 0)
            if lnn_3m and lstm_3m:
                st.metric(
                    "조기 탐지 AUROC (3~6개월)",
                    f"LNN: {lnn_3m:.4f}",
                    delta=f"+{(lnn_3m - lstm_3m):.4f} vs LSTM",
                )
        with col3:
            adv = exp["irregularity"]["advantage_at_high_irr"]
            st.metric(
                "고불규칙도 환경 우위",
                f"+{adv:.4f} AUROC",
                delta="불규칙도 높을수록 LNN 우세",
            )

    # 실험 그래프
    if os.path.exists(img_path):
        st.image(img_path, caption="LNN vs LSTM 비교 실험 결과 (3가지 실험)", use_column_width=True)
    else:
        st.warning("실험 그래프 없음. experiments/lnn_vs_lstm_experiment.py 실행 후 새로고침하세요.")
        if st.button("LNN 실험 실행"):
            with st.spinner("실험 중... (약 5분)"):
                import subprocess
                cwd = os.path.dirname(os.path.dirname(__file__))
                r = subprocess.run(
                    [sys.executable, "experiments/lnn_vs_lstm_experiment.py"],
                    capture_output=True, text=True, cwd=cwd
                )
                if r.returncode == 0:
                    st.success("실험 완료! 새로고침하세요.")
                    st.code(r.stdout[-2000:])
                else:
                    st.error("오류 발생")
                    st.code(r.stderr[-1000:])

    st.markdown("---")
    st.markdown("""
    ### 실험 설계

    | 실험 | 방법 | 결과 |
    |------|------|------|
    | **수렴 속도** | 에포크별 Val AUROC (불규칙도=0.7, 3회 반복) | LNN이 AUROC 0.9 도달 에포크 수 비교 |
    | **조기 탐지** | seq_len 3~12 변화 → Test AUROC | 짧은 시퀀스에서 LNN 우위 |
    | **불규칙도 수준** | irregularity 0.0~1.0 변화 → AUC | 불규칙도 증가 시 LNN 우위 크기 |

    ### 이론적 배경

    LNN의 핵심 방정식 (CfC):
    ```
    dh/dt = -[τ(x,t)]⁻¹ · h + f(h,x,t)
    ```
    시간 상수 τ가 **입력과 시간에 따라 동적으로 변화**하므로
    불규칙한 시간 간격 데이터를 추가 전처리 없이 자연스럽게 처리합니다.
    """)


# ────────────────────────────────────────────────
# TAB 5: 파이프라인 실행
# ────────────────────────────────────────────────

def tab_run_pipeline():
    st.subheader("모델 학습 파이프라인 실행")

    st.markdown("""
    **학습 파이프라인 구성:**
    1. 고용형태별근로실태조사 로드 → 착취 라벨 정의
    2. XGBoost 5-Fold CV (실제 데이터)
    3. LNN + LSTM 학습 (합성 시계열 - 실제 분포 보정)
    4. 결과 JSON 저장
    """)

    col1, col2, col3 = st.columns(3)
    sample_frac = col1.slider("데이터 샘플 비율", 0.01, 0.5, 0.05, 0.01)
    quick_mode = col2.checkbox("빠른 모드 (합성 데이터 소규모)", value=True)

    if col3.button("학습 시작", type="primary"):
        with st.spinner("학습 중... (2~5분 소요)"):
            import subprocess
            cmd = [
                sys.executable, "models/train_pipeline.py",
                f"--sample={sample_frac}",
            ]
            if quick_mode:
                cmd.append("--quick")

            cwd = os.path.dirname(os.path.dirname(__file__))
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)

            if result.returncode == 0:
                st.success("학습 완료! 페이지를 새로고침하세요.")
                st.code(result.stdout[-3000:])
            else:
                st.error("오류 발생")
                st.code(result.stderr[-2000:])

    results = load_pipeline_results()
    if results:
        st.markdown("---")
        st.subheader("마지막 학습 결과")
        st.json(results["model_performance"])


# ────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────

def main():
    render_header()

    with st.spinner("실제 데이터 로딩 중... (최초 1회)"):
        try:
            df = load_wage_data(sample_frac=0.02)
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")
            df = pd.DataFrame()

    results = load_pipeline_results()

    if not df.empty:
        render_kpi(df, results)

    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 실제 데이터 분석",
        "🤖 모델 성능 비교",
        "🔬 LNN 핵심 실험",
        "🌏 E9 이주노동자",
        "⚙️ 파이프라인 실행",
    ])

    with tab1:
        if not df.empty:
            tab_real_data(df)
        else:
            st.warning("데이터 없음")

    with tab2:
        tab_model_performance(results)

    with tab3:
        tab_lnn_experiment()

    with tab4:
        tab_migrant_analysis()

    with tab5:
        tab_run_pipeline()


if __name__ == "__main__":
    main()
