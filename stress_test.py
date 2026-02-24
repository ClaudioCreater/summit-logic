# -*- coding: utf-8 -*-
"""
stress_test.py — Summit Logic 스트레스 테스트
════════════════════════════════════════════════
실제 현장에서 발생할 수 있는 '최악의 엑셀 데이터' 3가지 케이스를 시뮬레이션합니다.

[실행]  py stress_test.py
[목적]  logistics_engine.py + data_cleaner.py 의 방어 코드 검증

케이스:
  Case A — CJ 파일 컬럼명 변형 ('송장번호', 'Invoice No.', '운송장 번호')
  Case B — 더티 데이터 (이모지 주소, 국제전화 형식, 빈 연락처)
  Case C — 스마트스토어 헤더 위치 변동 (Row 0, Row 2, Row 4)
"""

import io
import sys
import os

# 프로젝트 경로 등록
BASE = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", "coding practice")
sys.path.insert(0, BASE)

import pandas as pd
from openpyxl import Workbook

from data_cleaner import clean_text, clean_phone, truncate_address
from logistics_engine import (
    find_column, map_cj_columns, find_header_row, read_naver_excel,
    build_cj_upload_df, NAVER,
)

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"

results: list[dict] = []


def record(case: str, desc: str, ok: bool, detail: str = ""):
    tag = PASS if ok else FAIL
    results.append({"case": case, "desc": desc, "ok": ok, "detail": detail})
    print(f"  {tag} {desc}" + (f"  →  {detail}" if detail else ""))


# ════════════════════════════════════════════════════
# 헬퍼: 스마트스토어 Excel BytesIO 생성
# ════════════════════════════════════════════════════
def make_smart_excel(header_at_row: int = 1, order_count: int = 3) -> io.BytesIO:
    """
    header_at_row 번째 행(0-indexed)에 컬럼 헤더를 배치한 스마트스토어 파일을 생성.
    그 위에는 안내 문구 행들이 들어갑니다.
    """
    wb = Workbook()
    ws = wb.active

    # 안내 문구 행 (header_at_row 개수만큼)
    for _ in range(header_at_row):
        ws.append(
            ["배송 방법: 아래 상품주문번호, 배송방법, 택배사, 송장번호를 입력해 주세요."]
            + [""] * 55
        )

    # 헤더 행: 56개 컬럼 (NAVER 인덱스 기준)
    col_count = max(NAVER.values()) + 1
    header = [""] * col_count
    for k, idx in NAVER.items():
        header[idx] = k
    ws.append(header)

    # 데이터 행
    for i in range(1, order_count + 1):
        row = [""] * col_count
        row[NAVER["상품주문번호"]]  = f"주문{i:03d}"
        row[NAVER["수취인명"]]      = f"수취인{i}"
        row[NAVER["수취인연락처1"]] = f"010-{1000+i:04d}-5678"
        row[NAVER["합배송지"]]      = f"서울시 강남구 테헤란로 {i}길"
        row[NAVER["우편번호"]]      = f"0623{i}"
        row[NAVER["상품명"]]        = f"상품{i}"
        row[NAVER["수량"]]          = str(i)
        row[NAVER["배송메세지"]]    = "문 앞에 놓아주세요"
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def make_cj_excel(waybill_col_name: str = "운송장번호",
                  order_col_name: str = "고객주문번호",
                  order_count: int = 3) -> pd.DataFrame:
    """지정된 컬럼명으로 CJ LOIS 결과 DataFrame 생성."""
    rows = []
    for i in range(1, order_count + 1):
        rows.append({
            order_col_name:  f"주문{i:03d}",
            waybill_col_name: f"628{i:08d}",
            "수취인명": f"수취인{i}",
        })
    return pd.DataFrame(rows)


# ════════════════════════════════════════════════════
# Case A: CJ 파일 컬럼명 변형
# ════════════════════════════════════════════════════
print("\n" + "═" * 55)
print("Case A — CJ 파일 컬럼명 변형")
print("═" * 55)

WAYBILL_VARIANTS = [
    ("운송장번호",  "고객주문번호"),   # 표준
    ("송장번호",   "주문번호"),        # 변형 1
    ("Invoice No.", "Order No."),     # 영문 표기
    ("운송장 번호", "고객 주문 번호"), # 공백 포함
    ("CJ운송장번호", "고객주문번호"),  # 접두어 포함
]

for waybill_col, order_col in WAYBILL_VARIANTS:
    df_cj = make_cj_excel(waybill_col_name=waybill_col, order_col_name=order_col)
    try:
        col_map = map_cj_columns(df_cj)
        ok = col_map["waybill"] == waybill_col and col_map["order"] == order_col
        detail = f"주문→'{col_map['order']}', 운송장→'{col_map['waybill']}'"
        record("A", f"컬럼명 '{waybill_col}' / '{order_col}'", ok, detail)
    except ValueError as e:
        record("A", f"컬럼명 '{waybill_col}' / '{order_col}'", False, str(e).split('\n')[0])


# ════════════════════════════════════════════════════
# Case B: 더티 데이터 (이모지, 국제전화, 빈값)
# ════════════════════════════════════════════════════
print("\n" + "═" * 55)
print("Case B — 더티 데이터")
print("═" * 55)

dirty_phones = [
    ("010-1234-5678",      "01012345678",  "표준 하이픈"),
    ("(010) 1234 5678",    "01012345678",  "괄호·공백"),
    ("+82-10-1234-5678",   "01012345678",  "국제번호 +82"),
    ("82 10 1234 5678",    "01012345678",  "국가코드 82"),
    ("010.1234.5678",      "01012345678",  "마침표"),
    ("nan",                "",             "NaN값"),
    ("",                   "",             "빈 문자열"),
    ("010 1234  5678",     "01012345678",  "이중공백"),
]

for raw, expected, desc in dirty_phones:
    got = clean_phone(raw)
    ok = got == expected
    record("B-phone", f"전화번호 정제 ({desc}): {raw!r}", ok, f"→ '{got}' (기대: '{expected}')")

dirty_addresses = [
    ("서울시 강남구 😊테헤란로 123",       "서울시 강남구 테헤란로 123",     "이모지 포함"),
    ("🏠 부산시 해운대구 🚀 해운대로 1",   "부산시 해운대구 해운대로 1",     "이모지 여러 개"),
    ("서울시\t강남구\n테헤란로",           "서울시 강남구 테헤란로",          "탭·줄바꿈"),
    ("A" * 120,                           "A" * 100,                        "100자 초과 절삭"),
]

for raw, expected, desc in dirty_addresses:
    cleaned = truncate_address(clean_text(raw))
    ok = cleaned == expected
    record("B-addr", f"주소 정제 ({desc})", ok, f"결과: '{cleaned[:40]}...' " if len(cleaned) > 40 else f"결과: '{cleaned}'")


# ════════════════════════════════════════════════════
# Case C: 스마트스토어 헤더 위치 변동
# ════════════════════════════════════════════════════
print("\n" + "═" * 55)
print("Case C — 스마트스토어 헤더 위치 변동")
print("═" * 55)

for header_at_row in [0, 1, 2, 4]:
    buf = make_smart_excel(header_at_row=header_at_row, order_count=3)
    try:
        detected = find_header_row(buf)
        ok_detect = detected == header_at_row
        record("C-detect", f"헤더 탐색 (헤더가 Row {header_at_row}에 있음)", ok_detect,
               f"감지된 헤더 행: {detected}")

        df = read_naver_excel(buf)
        ok_rows = len(df) == 3
        record("C-read",   f"데이터 읽기 (헤더 Row {header_at_row})", ok_rows,
               f"데이터 행 수: {len(df)}개 (기대: 3)")

        df_cj, cnt = build_cj_upload_df(df)
        ok_build = cnt == 3 and len(df_cj) == 3
        record("C-build",  f"CJ 변환 (헤더 Row {header_at_row})", ok_build,
               f"원본 {cnt}건 → 발송 {len(df_cj)}건")

    except Exception as e:
        record("C", f"헤더 Row {header_at_row}", False, f"예외 발생: {e}")


# ════════════════════════════════════════════════════
# 최종 결과 요약
# ════════════════════════════════════════════════════
total  = len(results)
passed = sum(1 for r in results if r["ok"])
failed = total - passed

print("\n" + "═" * 55)
print("최종 결과 요약")
print("═" * 55)
print(f"  전체: {total}건  |  통과: {passed}건  |  실패: {failed}건")

if failed > 0:
    print("\n  실패 항목:")
    for r in results:
        if not r["ok"]:
            print(f"    [{r['case']}] {r['desc']}  →  {r['detail']}")

print()
if failed == 0:
    print("  ALL STRESS TESTS PASSED — 실전 배포 준비 완료!")
else:
    print(f"  {failed}건 실패 — 위 항목을 확인하세요.")
    sys.exit(1)
