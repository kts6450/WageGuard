# -*- coding: utf-8 -*-
"""실행 중인 Streamlit 앱 화면 캡처 (Edge headless + selenium)."""
from __future__ import annotations

import sys
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def shot(driver, url: str, out: str, wait: float = 12,
         click_sidebar_option: str | None = None):
    driver.get(url)
    time.sleep(wait)
    if click_sidebar_option:
        try:
            # 시도 selectbox 열고 옵션 클릭
            box = driver.find_element(By.CSS_SELECTOR,
                                      "[data-testid='stSelectbox']")
            box.click()
            time.sleep(1.5)
            for li in driver.find_elements(By.CSS_SELECTOR, "li"):
                if li.text.strip() == click_sidebar_option:
                    li.click()
                    break
            time.sleep(8)
        except Exception as e:
            print("sidebar interaction skipped:", e)
    driver.save_screenshot(out)
    print("saved:", out)


def main():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1680,1050")
    opts.add_argument("--disable-gpu")
    driver = webdriver.Edge(options=opts)
    try:
        base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8766"
        out_prefix = sys.argv[2] if len(sys.argv) > 2 else "ui"
        pick = sys.argv[3] if len(sys.argv) > 3 else None
        shot(driver, base, f"{out_prefix}.png", click_sidebar_option=pick)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
