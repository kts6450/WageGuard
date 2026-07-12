# -*- coding: utf-8 -*-
"""data.go.kr 파일 데이터셋 일괄 수집기.

공공데이터포털의 파일형 데이터셋(로그인 불필요)을 데이터셋 ID로 내려받아
data/public/ 에 저장한다. 링크 연계형(KOSIS 등)은 첨부가 없어 건너뛴다.

usage: python scripts/fetch_datago_files.py [datasetId ...]
"""
from __future__ import annotations

import os
import re
import sys
import time

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(HERE, "data", "public")

DEFAULT_IDS = [
    "15105236",  # 한국고용정보원_외국인근로자_근무현황 (가점 '나')
    "15105231",  # 한국고용정보원_외국인_외국인고용_사업장현황 (가점 '나')
    "15111730",  # 고용노동부_제조업 외국인근로자 근무현황
    "15068736",  # 고용노동부_연도별 임금체불현황
    "3068549",   # 근로복지공단_임금체불 대지급금 지급현황
    "15068752",  # 고용노동부_연도별 근로사건 현황
]


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", s).strip()


def fetch_dataset(sess: requests.Session, ds_id: str) -> int:
    page = sess.get(f"https://www.data.go.kr/data/{ds_id}/fileData.do",
                    timeout=30)
    page.raise_for_status()
    pks = list(dict.fromkeys(re.findall(r"uddi:[0-9a-f-]+", page.text)))
    title = re.search(r"<title>([^<|]+)", page.text)
    print(f"[{ds_id}] {title.group(1).strip() if title else '?'} "
          f"— file keys: {len(pks)}")
    saved = 0
    for pk in pks:
        try:
            meta = sess.post(
                "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do",
                params={"recommendDataYn": "Y"},
                data={"publicDataPk": ds_id, "publicDataDetailPk": pk},
                timeout=30)
            meta.raise_for_status()
            j = meta.json()
        except Exception:
            continue
        atch, sn = j.get("atchFileId"), j.get("fileDetailSn")
        info = j.get("dataSetFileDetailInfo") or {}
        name = info.get("dataNm") or f"{ds_id}_{pk[-8:]}"
        ext = (info.get("atchFileExtsn") or "").lower()
        if not atch:
            link = info.get("dataUrl") or ""
            print(f"  - {name}: 첨부 없음 (링크 연계: {link or 'N/A'})")
            continue
        ext = ext if ext else "csv"
        fpath = os.path.join(OUT_DIR, safe_name(name) + "." + ext)
        try:
            r = sess.get("https://www.data.go.kr/cmm/cmm/fileDownload.do",
                         params={"atchFileId": atch, "fileDetailSn": sn},
                         timeout=120)
            r.raise_for_status()
            with open(fpath, "wb") as f:
                f.write(r.content)
            print(f"  + saved {os.path.basename(fpath)} "
                  f"({len(r.content):,} bytes)")
            saved += 1
        except Exception as e:
            print(f"  - {name}: 다운로드 실패 {e}")
        time.sleep(0.3)
    return saved


def main():
    ids = sys.argv[1:] or DEFAULT_IDS
    os.makedirs(OUT_DIR, exist_ok=True)
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    total = 0
    for ds_id in ids:
        try:
            total += fetch_dataset(sess, ds_id)
        except Exception as e:
            print(f"[{ds_id}] 실패: {e}")
    print(f"done. saved {total} files -> {OUT_DIR}")


if __name__ == "__main__":
    main()
