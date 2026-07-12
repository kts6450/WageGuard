# -*- coding: utf-8 -*-
"""WageGuard 월별 자동 갱신 — 수집 → 재계산 → 이력 적재 원커맨드.

usage:
  python scripts/refresh_all.py              # 전체 (다운로드 포함)
  python scripts/refresh_all.py --skip-fetch # 재계산만

Windows 작업 스케줄러 등록(매월 1일 07:00):
  schtasks /Create /TN "WageGuard 갱신" /SC MONTHLY /D 1 /ST 07:00 ^
    /TR "python C:\\...\\WageGuard\\scripts\\refresh_all.py"
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE.parent / "results" / "ops" / "refresh.log"

STEPS_FETCH = [
    ("임금체불 공개 명단 수집", [sys.executable, str(HERE / "fetch_defaulter_list.py")]),
    ("공개 데이터셋 수집(국민연금 등)", [sys.executable, str(HERE / "fetch_datago_files.py"),
                             "15083277", "15111730", "15068736", "15068752"]),
    ("KOSIS E-9 시도×업종 수집", [sys.executable, str(HERE / "kosis_scrape_e9.py")]),
]
STEPS_BUILD = [
    ("시도 단위 스크리닝·검증", [sys.executable, str(HERE / "build_cell_screening.py")]),
    ("시군구 운영 스크리닝·이력 적재", [sys.executable, str(HERE / "build_ops_screening.py")]),
    ("이주노동자 노출-가중 우선순위", [sys.executable, str(HERE / "build_migrant_priority.py")]),
    ("발표·문서용 그림 재생성", [sys.executable, str(HERE / "build_screening_figures.py")]),
]


def log(msg: str):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    skip_fetch = "--skip-fetch" in sys.argv
    steps = STEPS_BUILD if skip_fetch else STEPS_FETCH + STEPS_BUILD
    log(f"=== 갱신 시작 (fetch {'생략' if skip_fetch else '포함'}) ===")
    for name, cmd in steps:
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            log(f"실패: {name}\n{r.stderr[-1500:]}")
            log("=== 갱신 중단 — 이전 산출물 유지 ===")
            return 1
        log(f"완료: {name} ({time.time()-t0:.0f}s)")
    log("=== 갱신 완료 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
