# 🔍 이주노동자 임금 착취 탐지 시스템

> **Liquid Neural Network × 공공 마이크로데이터 기반 선제 탐지**

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-red)](https://pytorch.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-green)](https://streamlit.io)
[![Data](https://img.shields.io/badge/Data-MDIS_491만건-orange)](https://mdis.kostat.go.kr)

---

## 프로젝트 개요

국내 약 90만 이주노동자의 임금 착취를 **피해자 신고 없이** 공공 마이크로데이터만으로 선제 탐지하는 ML 시스템입니다.

### 핵심 성과

| 지표 | 결과 |
|------|------|
| 분석 데이터 | **491만 6,667건** (통계청 MDIS, 2020~2024) |
| 실제 착취 비율 | **6.7%** (3조건 복합 라벨) |
| XGBoost AUROC | **0.9998 ± 0.0001** (5-Fold CV) |
| LNN 3개월 조기탐지 | **AUROC 0.9957** (LSTM 0.9900 대비 +0.57%) |
| LNN 수렴 속도 | LSTM 대비 **25% 빠름** (에포크 3 vs 4) |

---

## 데이터 소스 (통계청 MDIS)

| 데이터 | 규모 | 활용 |
|--------|------|------|
| 고용형태별근로실태조사 (2020~2024) | **491만건** | 착취 라벨 + XGBoost |
| 이민자체류실태조사 공통항목 | ~12만건 | 외국인 차별·소득 분석 |
| 비전문취업(E9) 부가항목 | ~1.1만건 | 계약 인지·이직 패턴 |
| 근로환경조사 | ~10만건 | 폭력·괴롭힘 측정 |

---

## 착취 라벨 정의 (법적 기준 기반)

```
A. 4대보험 미가입  →  5.4% (고용/건강/국민연금 중 하나라도 미가입)
B. 최저임금 미달   →  1.4% (연도별 법정 최저임금 미만)
C. 초과근무 착취   →  0.1% (초과근무 20h+ && 초과급여=0)
전체 착취 (합집합) →  6.7%
```

---

## 프로젝트 구조

```
project-C/
├── data/
│   ├── raw/                    # 실제 MDIS 공공 데이터
│   │   ├── 총괄_*_데이터/      # 고용형태별근로실태조사 (491만건)
│   │   ├── 공통항목_*_데이터/   # 이민자 공통항목
│   │   ├── 부가항목(비전문취업)_*_데이터/  # E9 데이터
│   │   └── 총괄_20260329_48620_데이터/     # 근로환경조사
│   └── processed/              # 전처리된 ML 피처
│
├── utils/
│   ├── real_data_processor.py  # 실제 데이터 로딩 + 착취 라벨
│   ├── data_generator.py       # 합성 시계열 생성 (LNN용)
│   ├── network_analysis.py     # NetworkX 이분 그래프
│   └── anomaly_detection.py    # PyOD 앙상블
│
├── models/
│   ├── lnn_model.py            # LNN + LSTM 모델
│   ├── train_pipeline.py       # 통합 학습 파이프라인
│   └── evaluation.py           # K-Fold 교차검증
│
├── experiments/
│   └── lnn_vs_lstm_experiment.py  # 조기탐지 비교 실험
│
├── dashboard/
│   └── app.py                  # Streamlit 대시보드
│
├── results/
│   ├── pipeline_results.json   # 학습 결과
│   ├── lnn_experiment_summary.json
│   └── lnn_vs_lstm_experiment.png  # 비교 그래프
│
├── PAPER_DRAFT.md              # 논문 초안
└── requirements.txt
```

---

## 빠른 시작

### 1. 설치

```bash
pip install -r requirements.txt
```

### 2. 모델 학습

```bash
# 빠른 테스트 (3% 샘플)
python models/train_pipeline.py --quick --sample 0.03

# 전체 학습 (전체 데이터)
python models/train_pipeline.py --sample 0.3
```

### 3. LNN vs LSTM 실험

```bash
python experiments/lnn_vs_lstm_experiment.py
```

### 4. 대시보드 실행

```bash
streamlit run dashboard/app.py
```

---

## 대시보드 탭 구성

| 탭 | 내용 |
|----|------|
| 📊 실제 데이터 분석 | 491만건 착취 패턴, 산업별/고용형태별 분포 |
| 🤖 모델 성능 비교 | XGBoost vs LNN vs LSTM AUROC/F1 |
| 🌏 E9 이주노동자 | 계약 인지율, 이직 패턴, 연도별 추이 |
| ⚙️ 파이프라인 실행 | 대시보드 내 학습 실행 |

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| 딥러닝 | PyTorch 2.0+, ncps (CfC/LNN) |
| 머신러닝 | XGBoost, Scikit-learn |
| 이상탐지 | PyOD (IForest, LOF, COPOD, ECOD) |
| 네트워크 | NetworkX |
| 시각화 | Streamlit, Plotly |
| 데이터 | Pandas, NumPy |

---

## 수익화 경로

```
대학 프로젝트 → 공모전 수상 → 고용노동부 파일럿 → B2G/B2B SaaS
```

- **B2G**: 고용노동부 근로감독 우선순위 자동화
- **B2B**: 노무법인·ESG 실사 컨설팅 공급망 노동 리스크 스코어링
- **임팩트 투자**: 소풍벤처스, 아산사회복지재단 등

---

## 윤리 고려사항

- 개인 식별 불가 형태의 통계 데이터만 사용
- 착취 라벨은 법적 기준 기반 (주관적 판단 배제)
- 결과는 "점검 우선순위 제안"으로만 활용 (자동 처벌 불가)
- 이주노동자 권익 향상을 위한 도구 (감시 목적 아님)

---

## 논문

[PAPER_DRAFT.md](./PAPER_DRAFT.md) 참조

키워드: Liquid Neural Network, 이상 탐지, 이주노동자, 불규칙 시계열, 임금 착취, 공공 마이크로데이터
