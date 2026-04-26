"""
제5회 고용노동 공공데이터·AI 활용 공모전 제출용 상수.

- 본 아이디어의 핵심 데이터는 주최(고용노동부)·주관(한국고용정보원) 공공데이터입니다.
- 통계청 MDIS는 미시 라벨링·이주노동자 보정의 보조 데이터로 사용합니다.
- 가점 항목 매칭(주관기관 공공데이터 = 가점 "나" 2점)을 위해 KEIS 데이터를 명시합니다.
"""

CONTEST_NAME = "제5회 고용노동 공공데이터·AI 활용 공모전"
CONTEST_URL = "https://www.2026datacontest.co.kr/"

# 접수 폼 '활용 AI명' 기타란 예시 (챗봇 미사용 시 그대로 사용 가능)
AI_STACK_SHORT = "XGBoost; PyTorch LNN/LSTM(ncps); PyOD 이상탐지"

# 핵심 공공데이터 (주최·주관 — 가점 대상)
PRIMARY_PUBLIC_DATA = [
    {
        "name": "외국인근로자 근무현황(대상별 현황)",
        "org": "한국고용정보원(주관)",
        "url": "https://www.data.go.kr/data/15105236/fileData.do",
        "role": "산업×지역×체류자격 이주노동자 가중치 — 가점 '나' 핵심",
    },
    {
        "name": "임금체불 사업주 명단공개",
        "org": "고용노동부(주최)",
        "url": "https://www.moel.go.kr/info/defaulter/defaulterList.do",
        "role": "외부 그라운드 트루스 (Precision@K 검증)",
    },
    {
        "name": "연도별 근로사건 현황",
        "org": "고용노동부(주최)",
        "url": "https://www.data.go.kr/data/15068752/fileData.do",
        "role": "노동관계법 위반 신고·처리 추세 — 모형 정합성 검증",
    },
    {
        "name": "임금체불 통계(노동포털)",
        "org": "고용노동부(주최)",
        "url": "https://labor.moel.go.kr/arrstat/arrstat_list.do",
        "role": "업종·규모별 체불액 시계열",
    },
    {
        "name": "(노동통계) 고용형태별근로실태조사 — 공공데이터포털 개방판",
        "org": "고용노동부(주최)",
        "url": "https://www.data.go.kr/data/3069915/fileData.do",
        "role": "공식 개방 라벨링 데이터(MDIS 마이크로데이터와 변수 정합)",
    },
    {
        "name": "EIS 고용행정통계",
        "org": "한국고용정보원(주관)",
        "url": "https://eis.work24.go.kr",
        "role": "사업장 규모·지역·연령·성별 노출 보정 — 가점 '나'",
    },
    {
        "name": "워크피디아 임금체계 통계",
        "org": "한국고용정보원(주관)",
        "url": "https://wagework.go.kr/pt/c/b/retrieveWageSytmStcs.do",
        "role": "직종 표준 임금 보조 라벨 — 가점 '나'",
    },
    {
        "name": "고용노동통계정보시스템",
        "org": "고용노동부(주최)",
        "url": "https://laborstat.moel.go.kr",
        "role": "산업·고용형태·임금 거시 분포 검증",
    },
    {
        "name": "최저임금위원회",
        "org": "고용노동부(주최)",
        "url": "https://www.minimumwage.go.kr",
        "role": "연도별 법정 최저임금(라벨 근거)",
    },
    {
        "name": "외국인고용관리시스템(EPS)",
        "org": "한국고용정보원(주관)",
        "url": "https://eps.go.kr",
        "role": "이주노동 고용허가 정책·연계 시나리오",
    },
]

# 호환성: 기존 코드가 MOEL_KEIS_PORTALS를 import하는 경우 유지
MOEL_KEIS_PORTALS = PRIMARY_PUBLIC_DATA

# 보조: 통계청 MDIS
MDIS_PORTAL = "https://mdis.kostat.go.kr"

# 가점 정보
SCORING_BONUS = {
    "나": "주관기관(한국고용정보원) 공공데이터 활용 — 가점 2점 (외국인근로자 근무현황·EIS·워크피디아 직접 활용으로 부합)",
    "가": "주최·주관·후원 국가중점데이터 활용 — 가점 2점 (https://www.data.go.kr/tcs/eds/selectCoreDataListView.do 매칭 시)",
    "라": "아이디어 부문 예비창업자 — 가점 1점",
    "상한": "가점 중복 적용 불가, 최대 2점",
}


def contest_expander_markdown() -> str:
    """Streamlit expander 등에 넣을 짧은 안내."""
    lines = [
        f"**{CONTEST_NAME}** ([공모 누리집]({CONTEST_URL})) 제출 정리 요약",
        "",
        "**핵심 공공데이터(주최·주관, 가점 대상):**",
    ]
    lines.extend(
        f"- [{p['name']}]({p['url']}) — {p['org']}: {p['role']}"
        for p in PRIMARY_PUBLIC_DATA
    )
    lines.extend([
        "",
        f"**보조 데이터:** 통계청 [MDIS]({MDIS_PORTAL}) — 미시 라벨링·이주노동자 보정.",
        "",
        "**AI(아이디어·파이프라인):** " + AI_STACK_SHORT.replace("; ", " · ") + ".",
        "",
        "**활용 AI명(기타):** `" + AI_STACK_SHORT + "`",
        "",
        "**공모 가점:** " + SCORING_BONUS["나"],
    ])
    return "\n".join(lines)
