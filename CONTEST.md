# 제5회 고용노동 공공데이터·AI 활용 공모전 — 제출 정리 (WageGuard)

> 공모전 누리집: [www.2026datacontest.co.kr](https://www.2026datacontest.co.kr/)  
> 소통24 공고: [공모전 공고 상세](https://www.sotong.go.kr/front/epilogue/epilogueNewViewPage.do?bbs_id=24a75f24197c4826b5b98829f88fb4c8&pagetype=bbs&search_result=&search_result_cnddt=&epilogue_bgnde=&epilogue_endde=&date_range=all&epilogue_bgnde_cnddt=&epilogue_endde_cnddt=&date_range_cnddt=all&search_title_contents=&search_insttNm=&miv_pageNo=5&preDate=&endDate=)

본 문서는 **아이디어 기획 부문** 기준으로, 접수 화면의 **활용정보(자가점검)**·**데이터 명세서**·**아이디어 제안서(10페이지 이내)** 작성 시 그대로 옮겨 쓸 수 있도록 정리한 내부용 메모입니다.

---

## 1. 출품 개요 (한 단락 예시)

**WageGuard**는 통계청 MDIS의 고용·이주노동 관련 마이크로데이터를 활용하고, **XGBoost·시계열 딥러닝(LNN/LSTM)·이상탐지(PyOD)** 로 임금·근로 조건 기반 위험 신호를 도출하여, **근로감독·지원 자원의 우선순위를 제안**하는 선제 점검 아이디어입니다. 개인 식별 정보 없이 통계 단위만 사용하며, 결과는 **자동 처벌이 아닌 점검·정책 보조** 목적으로 한정합니다.

---

## 2. 접수 폼 — 활용정보(자가점검) 채움 가이드

| 항목 | 권장 선택 | 비고 |
|------|-----------|------|
| 주최·주관·후원기관 **공공데이터** | **사용** | 아래 §3·§4 참고 |
| **AI** 활용 | **사용** | **아이디어·서비스 설계 안의 AI** (제안서 작성용 챗봇만으로는 해당 없음) |
| **활용 AI명** (챗GPT 등 목록) | 프로젝트에 **미사용** 시 체크 없음 또는 **기타** | 실제 모델은 §5. **기타** 선택 시 입력란 예: `XGBoost; PyTorch 기반 LNN/LSTM(ncps); PyOD 이상탐지 앙상블` |
| 旣 수상 | 사실대로 | 공모요강의 제한(유사 아이디어·상금 한도 등) 확인 |

---

## 3. 주제(체크박스)

- **노동** (핵심: 임금, 근로시간, 4대보험, 착취 라벨)
- **일자리** (보조: 이주노동자 고용·불안정 일자리·E9 맥락 — 제안서에 한 단락 이상 서술 권장)

---

## 4. 데이터 계층 (명세서·제안서용)

### 4.1 핵심: 주최·주관 기관 공공데이터 (가점 대상)

| # | 데이터명 | 제공기관(구분) | 활용 |
|---|----------|----------------|------|
| 1 | 외국인근로자 근무현황(대상별 현황) — [data.go.kr](https://www.data.go.kr/data/15105236/fileData.do) | **한국고용정보원**(주관) | 산업×지역×체류자격 **이주노동자 가중치** |
| 2 | 임금체불 사업주 명단공개 — [moel.go.kr](https://www.moel.go.kr/info/defaulter/defaulterList.do) | **고용노동부**(주최) | **외부 그라운드 트루스** (Precision@K) |
| 3 | 연도별 근로사건 현황 — [data.go.kr](https://www.data.go.kr/data/15068752/fileData.do) | **고용노동부**(주최) | 위반 신고·처리 추세, 모형 정합성 검증 |
| 4 | 임금체불 통계(노동포털) — [labor.moel.go.kr](https://labor.moel.go.kr/arrstat/arrstat_list.do) | **고용노동부**(주최) | 업종·규모별 체불액 시계열 |
| 5 | (노동통계) 고용형태별근로실태조사 개방판 — [data.go.kr](https://www.data.go.kr/data/3069915/fileData.do) | **고용노동부**(주최) | **공식 개방 라벨링 데이터** |
| 6 | EIS 고용행정통계 — [eis.work24.go.kr](https://eis.work24.go.kr) | **한국고용정보원**(주관) | 사업장 규모·지역·연령·성별 노출 보정 |
| 7 | 워크피디아 임금체계 통계 — [wagework.go.kr](https://wagework.go.kr/pt/c/b/retrieveWageSytmStcs.do) | **한국고용정보원**(주관) | **직종 표준 임금** 보조 라벨 |
| 8 | 고용노동통계정보시스템 — [laborstat.moel.go.kr](https://laborstat.moel.go.kr) | **고용노동부**(주최) | 거시 분포 검증 |
| 9 | 최저임금위원회 — [minimumwage.go.kr](https://www.minimumwage.go.kr) | **고용노동부**(주최) | 연도별 법정 최저임금(라벨 근거) |
| 10 | 외국인고용관리시스템(EPS) — [eps.go.kr](https://eps.go.kr) | **한국고용정보원**(주관) | 정책·서비스 연계 |

> **가점**: #1, #6, #7은 **주관기관(한국고용정보원) 공공데이터** → 공모 가점 “나”(2점) 부합.  
> 가점 “가”(국가중점데이터)는 [공공데이터포털 국가중점데이터](https://www.data.go.kr/tcs/eds/selectCoreDataListView.do) 목록과 매칭하여 명시.

### 4.2 보조: 통계청 MDIS (마이크로데이터)

| 조사·데이터 | 역할 | 코드·경로 |
|-------------|------|-----------|
| 고용형태별근로실태조사 (2020~2024) | 미시 라벨링·XGBoost 피처 (개방판과 변수 정합) | `utils/real_data_processor.py` → `load_wage_survey`, `build_ml_features` |
| 이민자체류실태조사 공통항목 | 차별·소득 만족 등 위험 맥락 | `load_migrant_survey`, `get_migrant_risk_features` |
| 비전문취업(E9) 부가항목 | 계약 인지·이직 | `load_e9_survey` |
| 근로환경조사 | 근로환경·괴롭힘 등 (확장 분석) | `load_work_environment_survey` |

**착취 라벨(합집합, 법정 기준 정렬):** 4대보험 미가입 / 최저임금 미달 추정 / 초과근무 20h 이상·초과급여 0.

**XGBoost 학습 피처(라벨 직접 변수 제외·누수 방지):**  
`산업대분류코드`, `사업체규모코드`, `고용형태코드`, `성별코드`, `연령`, `소정실근로시간수`, `초과실근로시간수`, `휴일실근로시간수`, `정액급여액`, `초과급여액`, `상여금성과급총액`, `hourly_wage`, `overtime_pay_ratio`, `total_work_hours`, `employment_risk`, `year`, `insurance_score` — 상세는 `build_ml_features` 주석·코드 참고.

MDIS 이용은 **통계청 신청·승인 절차** 및 비밀유지 조건을 명시합니다.

---

## 5. AI 활용 (제안서·자가점검용 문장)

공모전 안내상 **AI는 아이디어·사업계획 그 자체에 포함**되어야 합니다. WageGuard에서의 역할 분담 예시:

| 기법 | 라이브러리·구현 | 역할 |
|------|-----------------|------|
| 그래디언트 부스팅 분류 | XGBoost | 공단면 피처 기반 **착취 위험 확률** 추정 |
| 시계열 딥러닝 | PyTorch + ncps(CfC/LNN), LSTM 비교 | 급여·근로 패턴 시계열 **조기 경보** 실험 |
| 이상탐지 앙상블 | PyOD | 다변량 이상 패턴 **보조 스코어** |
| 대시보드 | Streamlit | 정책·연구용 **결과 시각화·재현 실행** |

**제안서에 넣을 한 문장 예:**  
“본 아이디어는 공공 통계 마이크로데이터에서 도출한 근로·임금 변수를 입력으로 하여, XGBoost로 횡단면 위험도를 추정하고, PyTorch 기반 LNN/LSTM으로 시계열 조기 신호를 비교·보완하며, PyOD 앙상블로 이상 패턴을 보조한다.”

---

## 6. 아이디어 제안서 목차 초안 (A4 10페이지 이내)

1. **배경·문제** — 이주노동자 임금 착취, 신고 전 선제 대응 필요  
2. **아이디어 요약** — WageGuard 한 페이지(도식 1개 권장)  
3. **활용 공공데이터** — MDIS 조사명·규모·윤리, 주최·주관 포털 연계 표(§4.2)  
4. **AI 설계** — §5 표 + 데이터 흐름(입력→모델→출력)  
5. **기대효과** — 감독·지원 자원 효율, 이주노동자 권익(자동 처벌 아님 명시)  
6. **실현 가능성** — 본 저장소 파이프라인·대시보드·실험 결과 요약(수치는 README·`results/`와 일치)  
7. **한계·윤리** — 통계 한계, 라벨 정의, 설명가능성·인권  
8. **로드맵** — 파일럿·기관 협업(선택)

---

## 7. 저장소에서 인용할 파일

| 용도 | 경로 |
|------|------|
| 데이터·라벨·피처 | `utils/real_data_processor.py` |
| 통합 학습 | `models/train_pipeline.py` |
| LNN/LSTM | `models/lnn_model.py` |
| 실험 | `experiments/lnn_vs_lstm_experiment.py` |
| 대시보드 | `dashboard/app.py` |
| 기관 URL 상수(코드) | `utils/contest_data_sources.py` |

---

## 8. 실행 명령 (실현 가능성 근거)

```bash
pip install -r requirements.txt
python models/train_pipeline.py --quick --sample 0.03
streamlit run dashboard/app.py
```

---

*본 문서는 공모 주최 측 공식 해석을 대체하지 않습니다. 적격·가점은 최종 공고·사무국 답변을 따르십시오.*
