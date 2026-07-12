# -*- coding: utf-8 -*-
"""고용노동부 임금체불 사업주 명단 수집기.

https://www.moel.go.kr/info/defaulter/defaulterList.do 공개 명단(체불사업주
명단공개 제도, 근로기준법 제43조의2)을 전 페이지 수집해
data/public/defaulter_list.csv 로 저장한다.

외부 검증(그라운드 트루스)용: 업종 × 소재지(시도) 분포.
"""
from __future__ import annotations

import csv
import os
import re
import sys
import time

import requests

BASE = "https://www.moel.go.kr/info/defaulter/defaulterList.do"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "public", "defaulter_list.csv")

ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TAG_RE = re.compile(r"<[^>]+>")


def clean(html: str) -> str:
    return TAG_RE.sub("", html).replace("&amp;", "&").strip()


def parse_page(html: str):
    body_i = html.find("<tbody")
    body_j = html.find("</tbody>")
    if body_i < 0:
        return []
    rows = []
    for m in ROW_RE.finditer(html[body_i:body_j]):
        tds = [clean(t) for t in TD_RE.findall(m.group(1))]
        if len(tds) == 8:
            rows.append(tds)
    return rows


def main():
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    all_rows = []
    page = 1
    while True:
        r = sess.get(BASE, params={"pageIndex": page}, timeout=30)
        r.raise_for_status()
        rows = parse_page(r.text)
        if not rows:
            break
        all_rows.extend(rows)
        m = re.search(r"pageIndex=(\d+)\"[^>]*class=\"arr last\"", r.text)
        last = int(m.group(1)) if m else page
        print(f"page {page}/{last}: +{len(rows)} (total {len(all_rows)})")
        if page >= last:
            break
        page += 1
        time.sleep(0.4)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["공개차수", "성명", "나이", "사업장명", "업종",
                    "주소지_사업주", "소재지_사업장", "체불액_원"])
        w.writerows(all_rows)
    print(f"saved: {OUT} ({len(all_rows)} rows)")


if __name__ == "__main__":
    sys.exit(main())
