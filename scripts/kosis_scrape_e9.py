# -*- coding: utf-8 -*-
"""KOSIS DT_11827_A003 — 시도×업종 E-9 근로자 수를 렌더된 DOM에서 직접 추출.

로그인·다운로드 버튼 불필요: statHtml 뷰어가 게스트에게 표를 그대로 렌더한다.
저장: data/public/kosis_e9_sido_industry.csv (최신 분기)
"""
from __future__ import annotations

import io
import os
import sys
import time

import pandas as pd
from selenium import webdriver
from selenium.webdriver.edge.options import Options

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "public", "kosis_e9_sido_industry.csv")
URL = ("https://kosis.kr/statHtml/statHtml.do?orgId=118"
       "&tblId=DT_11827_A003&conn_path=I2")


def main():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")
    driver = webdriver.Edge(options=opts)
    try:
        driver.get(URL)
        time.sleep(14)
        driver.switch_to.window(driver.window_handles[-1])
        # 데이터 그리드는 중첩 프레임(root→1→0)에 렌더된다
        driver.switch_to.frame(1)
        driver.switch_to.frame(0)
        tables = pd.read_html(io.StringIO(driver.page_source))
        print(f"tables found: {len(tables)}")
        # 시도명이 들어있는 가장 큰 표 선택
        best = None
        for t in tables:
            hit = t.astype(str).apply(
                lambda col: col.str.contains("경기도|서울특별시",
                                             na=False)).to_numpy().any()
            if hit and (best is None or t.size > best.size):
                best = t
        if best is None:
            raise SystemExit("데이터 표를 찾지 못함")
        best.to_csv(OUT, index=False, encoding="utf-8-sig")
        print("saved:", OUT, "shape:", best.shape)
        print(best.head(25).to_string())
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
