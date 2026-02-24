# -*- coding: utf-8 -*-
"""
===========================================================
  Summit Logic - 스마트스토어 × 대한통운 LOIS 자동화 도구
===========================================================
[실행 방법]
  pip install streamlit pandas openpyxl
  streamlit run test_run.py

[기능]
  탭 1: 스마트스토어 주문서 → 대한통운 LOIS 접수 파일 변환
  탭 2: 대한통운 LOIS 결과 + 스마트스토어 원본 → 송장번호 자동 기입
===========================================================
"""

import io
import pandas as pd
import streamlit as st
from openpyxl import load_workbook


# ===========================================================
# 상수: 네이버 스마트스토어 엑셀 컬럼 인덱스 (0-based)
#
# 실제 파일 구조:
#   0행(Row 1): 안내 문구          ← 건너뜀
#   1행(Row 2): 컬럼 헤더           ← header=1 로 읽음
#   2행(Row 3)~: 실제 주문 데이터  ← 처리 대상
#
# openpyxl 로 접근할 때는 행·열 모두 1부터 시작:
#   - 데이터 시작 행: row=3
#   - 택배사 열(H): col=8 → row_cells[7] (0-based 리스트)
#   - 송장번호 열(I): col=9 → row_cells[8] (0-based 리스트)
# ===========================================================
NAVER = {
    "상품주문번호":   0,   # A열 - 매칭의 기준이 되는 고유 키
    "택배사":        7,   # H열 - 우리가 채워야 할 택배사 칸
    "송장번호":      8,   # I열 - 우리가 채워야 할 송장번호 칸
    "수취인명":      13,  # N열
    "상품명":        20,  # U열
    "수량":          26,  # AA열
    "수취인연락처1":  48,  # AW열
    "합배송지":      50,  # AY열 (기본주소 + 세부주소 합본)
    "우편번호":      54,  # BC열
    "배송메세지":    55,  # BD열
}

# 엑셀에서 데이터가 시작되는 행 번호 (openpyxl 기준 1-indexed)
NAVER_DATA_START_ROW = 3


# ===========================================================
# 유틸 함수
# ===========================================================

def read_naver_excel(file_obj) -> pd.DataFrame:
    """
    네이버 스마트스토어 주문 엑셀을 데이터프레임으로 읽습니다.

    - header=1 : 인덱스 1번 행(2번째 줄, 컬럼명 행)을 헤더로 사용
    - dtype=str : 주문번호/전화번호 등 숫자로 오인될 수 있는 값을 문자열 유지
    - fillna("") : 빈칸을 NaN 대신 빈 문자열로 변환
    """
    file_obj.seek(0)
    df = pd.read_excel(file_obj, header=1, dtype=str)
    return df.fillna("")


def build_cj_upload_df(df_smart: pd.DataFrame) -> pd.DataFrame:
    """
    스마트스토어 데이터프레임에서 CJ 대한통운 LOIS 접수에
    필요한 컬럼만 추출해 새 데이터프레임으로 반환합니다.

    매핑 규칙:
      스마트스토어 '상품주문번호' → CJ '고객주문번호' (매칭 키)
      스마트스토어 '합배송지'     → CJ '주소'
      나머지는 동일한 이름 또는 표준 CJ LOIS 컬럼명으로 변환
    """
    df_cj = pd.DataFrame({
        # 고객주문번호: 나중에 LOIS 결과와 스마트스토어를 연결할 핵심 키
        "고객주문번호": df_smart.iloc[:, NAVER["상품주문번호"]],
        "수취인명":     df_smart.iloc[:, NAVER["수취인명"]],
        "연락처":       df_smart.iloc[:, NAVER["수취인연락처1"]],
        "우편번호":     df_smart.iloc[:, NAVER["우편번호"]],
        # 합배송지: 기본 주소 + 세부 주소가 합쳐진 전체 배송지 주소
        "주소":         df_smart.iloc[:, NAVER["합배송지"]],
        "상품명":       df_smart.iloc[:, NAVER["상품명"]],
        "수량":         df_smart.iloc[:, NAVER["수량"]],
        "배송메시지":   df_smart.iloc[:, NAVER["배송메세지"]],
    })

    # 고객주문번호가 비어 있는 행은 제거 (헤더 잔여 행 등 방지)
    return df_cj[df_cj["고객주문번호"].str.strip() != ""].reset_index(drop=True)


def df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    """데이터프레임을 엑셀 바이트 스트림으로 변환 (다운로드 버튼용)"""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    buf.seek(0)
    return buf.getvalue()


def match_and_fill_waybill(
    smart_file_obj,
    cj_df: pd.DataFrame,
) -> tuple[bytes, int, int, list[str]]:
    """
    스마트스토어 원본 파일에 대한통운 운송장번호를 기입합니다.

    [처리 방식: 템플릿 유지형]
    - openpyxl 로 원본 파일을 그대로 로드 (1·2행 안내 문구 보존)
    - 3행부터 데이터 행을 순회하며 H열(택배사), I열(송장번호)만 수정
    - 나머지 셀, 서식, 수식 등은 일절 변경하지 않음

    반환값:
      (수정된 엑셀 바이트, 매칭 성공 건수, 미발급 건수, 미발급 주문번호 목록)
    """

    # ── CJ 파일에서 {고객주문번호: 운송장번호} 사전 생성 ──
    # 혹시 같은 번호가 중복으로 있으면 첫 번째 값 사용
    cj_lookup: dict[str, str] = {}
    for _, row in cj_df.iterrows():
        key = str(row.get("고객주문번호", "")).strip()
        val = str(row.get("운송장번호", "")).strip()
        if key and key not in cj_lookup:
            cj_lookup[key] = val

    # ── 스마트스토어 원본 파일 openpyxl 로드 ──
    smart_file_obj.seek(0)
    wb = load_workbook(smart_file_obj)
    ws = wb.active

    matched_count   = 0
    unmatched_count = 0
    unmatched_list: list[str] = []

    # 3행(NAVER_DATA_START_ROW)부터 마지막 행까지 순회
    for row_cells in ws.iter_rows(min_row=NAVER_DATA_START_ROW, max_row=ws.max_row):

        # A열 = 상품주문번호 (리스트 인덱스 0)
        order_no = str(row_cells[NAVER["상품주문번호"]].value or "").strip()

        # 주문번호가 없는 빈 행은 건너뜀
        if not order_no:
            continue

        if order_no in cj_lookup and cj_lookup[order_no]:
            # 매칭 성공: 운송장번호 기입
            # H열(리스트 인덱스 7) = 택배사
            row_cells[NAVER["택배사"]].value   = "CJ대한통운"
            # I열(리스트 인덱스 8) = 송장번호
            row_cells[NAVER["송장번호"]].value = cj_lookup[order_no]
            matched_count += 1
        else:
            # 매칭 실패: 빈칸 대신 '미발급' 기입 (스마트스토어 업로드 에러 방지)
            row_cells[NAVER["택배사"]].value   = "미발급"
            row_cells[NAVER["송장번호"]].value = "미발급"
            unmatched_count += 1
            unmatched_list.append(order_no)

    # 수정된 워크북을 바이트 스트림으로 저장
    output_buf = io.BytesIO()
    wb.save(output_buf)
    output_buf.seek(0)

    return output_buf.getvalue(), matched_count, unmatched_count, unmatched_list


# ===========================================================
# Streamlit UI
# ===========================================================

st.set_page_config(
    page_title="Summit Logic",
    page_icon="📦",
    layout="centered",
)

# ── 앱 헤더 ──
st.title("📦 Summit Logic")
st.caption("스마트스토어 × 대한통운 LOIS 자동화 도구")
st.divider()

# ── 두 개의 탭 생성 ──
tab1, tab2 = st.tabs(["  1. 접수 파일 생성  ", "  2. 송장 번호 매칭  "])


# ===========================================================
# 탭 1: 접수 파일 생성
#   스마트스토어 주문서 → 대한통운 LOIS 업로드 양식 변환
# ===========================================================
with tab1:

    st.subheader("대한통운 LOIS 접수 파일 생성")
    st.info(
        "**네이버 스마트스토어 주문서**를 올리면 "
        "CJ 대한통운 LOIS 업로드 전용 양식으로 변환해 줍니다.\n\n"
        "스마트스토어 > 발주(주문)확인/발송관리 > 엑셀 다운로드 파일을 사용하세요."
    )

    # ── 파일 업로드 ──
    uploaded_smart_t1 = st.file_uploader(
        "스마트스토어 주문서 (xlsx)",
        type=["xlsx"],
        key="tab1_uploader",
        help="네이버 스마트스토어에서 다운로드한 주문 엑셀 파일을 올려주세요.",
    )

    if uploaded_smart_t1:
        try:
            # ── 파일 읽기 ──
            df_smart = read_naver_excel(uploaded_smart_t1)

            # ── CJ LOIS 양식으로 변환 ──
            df_cj_upload = build_cj_upload_df(df_smart)
            total = len(df_cj_upload)

            # ── 결과 안내 ──
            st.success(f"파일 읽기 완료! 총 **{total}건** 주문을 변환합니다.")

            # ── 컬럼 매핑 확인 (접기/펼치기) ──
            with st.expander("컬럼 매핑 확인 (클릭해서 펼치기)"):
                mapping_info = pd.DataFrame({
                    "스마트스토어 컬럼명": [
                        "상품주문번호(A열)",
                        "수취인명(N열)",
                        "수취인연락처1(AW열)",
                        "우편번호(BC열)",
                        "합배송지(AY열)",
                        "상품명(U열)",
                        "수량(AA열)",
                        "배송메세지(BD열)",
                    ],
                    "→ CJ LOIS 컬럼명": [
                        "고객주문번호",
                        "수취인명",
                        "연락처",
                        "우편번호",
                        "주소",
                        "상품명",
                        "수량",
                        "배송메시지",
                    ],
                })
                st.table(mapping_info)

            # ── 변환 결과 미리보기 ──
            st.markdown("**변환 결과 미리보기**")
            st.dataframe(df_cj_upload, use_container_width=True)

            # ── 다운로드 버튼 ──
            excel_bytes = df_to_excel_bytes(df_cj_upload, sheet_name="LOIS_접수")
            st.download_button(
                label="⬇ CJ LOIS 접수 파일 다운로드 (xlsx)",
                data=excel_bytes,
                file_name="CJ_LOIS_접수.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        except IndexError:
            st.error(
                "파일 컬럼 구조가 예상과 다릅니다. "
                "네이버 스마트스토어에서 다운로드한 원본 엑셀 파일인지 확인해 주세요."
            )
        except Exception as e:
            st.error(f"파일 처리 중 오류가 발생했습니다: {e}")
            with st.expander("오류 상세 내용"):
                st.exception(e)


# ===========================================================
# 탭 2: 송장 번호 매칭
#   스마트스토어 원본 + 대한통운 LOIS 결과 → 송장번호 자동 기입
#   [템플릿 유지형]: 1·2행 안내 문구를 그대로 보존하고 데이터만 수정
# ===========================================================
with tab2:

    st.subheader("대한통운 → 스마트스토어 송장번호 자동 매칭")
    st.info(
        "두 파일을 올리면 **상품주문번호 ↔ 고객주문번호**를 기준으로 "
        "자동으로 매칭해서 H열(택배사)과 I열(송장번호)을 채워 줍니다.\n\n"
        "원본 파일의 1·2행 양식(안내 문구)이 **그대로 유지**됩니다."
    )

    # ── 두 파일 업로드 (좌우 배치) ──
    col_left, col_right = st.columns(2)
    with col_left:
        uploaded_smart_t2 = st.file_uploader(
            "① 스마트스토어 원본 파일 (xlsx)",
            type=["xlsx"],
            key="tab2_smart",
            help="네이버 스마트스토어 주문 엑셀 원본 파일",
        )
    with col_right:
        uploaded_cj_t2 = st.file_uploader(
            "② 대한통운 LOIS 결과 파일 (xlsx)",
            type=["xlsx"],
            key="tab2_cj",
            help="대한통운 LOIS에서 운송장 발급 후 다운로드한 결과 파일",
        )

    # 두 파일이 모두 업로드됐을 때만 처리
    if uploaded_smart_t2 and uploaded_cj_t2:
        try:
            # ── CJ 파일 읽기 ──
            # 고객주문번호, 운송장번호 컬럼이 있는지 검증
            df_cj = pd.read_excel(uploaded_cj_t2, dtype=str).fillna("")

            required_cj_cols = ["고객주문번호", "운송장번호"]
            missing_cols = [c for c in required_cj_cols if c not in df_cj.columns]
            if missing_cols:
                st.error(
                    f"대한통운 파일에 필수 컬럼이 없습니다: **{missing_cols}**\n\n"
                    f"실제 컬럼 목록: `{list(df_cj.columns)}`"
                )
                st.stop()

            # ── 매칭 실행 (템플릿 유지형) ──
            with st.spinner("매칭 처리 중..."):
                result_bytes, matched, unmatched, unmatched_list = match_and_fill_waybill(
                    smart_file_obj=uploaded_smart_t2,
                    cj_df=df_cj,
                )

            total = matched + unmatched

            # ── 매칭 결과 통계 ──
            st.markdown("---")
            m1, m2, m3 = st.columns(3)
            m1.metric("전체 주문", f"{total}건")
            m2.metric("매칭 성공", f"{matched}건")
            m3.metric("미발급", f"{unmatched}건")

            if unmatched > 0:
                st.warning(
                    f"아래 **{unmatched}건**은 대한통운 파일에서 운송장번호를 찾지 못해 "
                    "'미발급'으로 표시되었습니다."
                )
                st.code("\n".join(unmatched_list), language=None)
            else:
                st.success("모든 주문의 송장번호가 성공적으로 매칭되었습니다!")

            # ── 매칭 결과 미리보기 ──
            st.markdown("**매칭 결과 미리보기** (상품주문번호 / 택배사 / 송장번호)")

            # 미리보기용: pandas로 별도 읽어서 주요 컬럼만 표시
            uploaded_smart_t2.seek(0)
            df_preview = pd.read_excel(uploaded_smart_t2, header=1, dtype=str).fillna("")

            # CJ lookup 을 다시 만들어 미리보기에 반영
            cj_preview_lookup = dict(
                zip(df_cj["고객주문번호"].str.strip(), df_cj["운송장번호"].str.strip())
            )
            preview_df = df_preview.iloc[:, [
                NAVER["상품주문번호"],
                NAVER["수취인명"],
                NAVER["상품명"],
                NAVER["택배사"],
                NAVER["송장번호"],
            ]].copy()
            preview_df.columns = ["상품주문번호", "수취인명", "상품명", "택배사", "송장번호"]

            # 매칭된 값으로 업데이트
            for idx, row in preview_df.iterrows():
                key = str(row["상품주문번호"]).strip()
                waybill = cj_preview_lookup.get(key, "")
                if waybill:
                    preview_df.at[idx, "택배사"]  = "CJ대한통운"
                    preview_df.at[idx, "송장번호"] = waybill
                else:
                    preview_df.at[idx, "택배사"]  = "미발급"
                    preview_df.at[idx, "송장번호"] = "미발급"

            # 빈 행 제거 후 표시
            preview_df = preview_df[preview_df["상품주문번호"].str.strip() != ""]
            st.dataframe(preview_df, use_container_width=True)

            # ── 다운로드 버튼 ──
            st.markdown("---")
            st.download_button(
                label="⬇ 송장번호 기입 완료된 스마트스토어 파일 다운로드 (xlsx)",
                data=result_bytes,
                file_name="스마트스토어_송장입력완료.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.caption(
                "다운로드한 파일을 스마트스토어 "
                "'발주(주문)확인/발송관리 > 일괄발송 처리' 메뉴에서 업로드하세요."
            )

        except Exception as e:
            st.error(f"파일 처리 중 오류가 발생했습니다: {e}")
            with st.expander("오류 상세 내용"):
                st.exception(e)

    elif uploaded_smart_t2 and not uploaded_cj_t2:
        st.info("대한통운 LOIS 결과 파일(②)도 업로드해 주세요.")
    elif not uploaded_smart_t2 and uploaded_cj_t2:
        st.info("스마트스토어 원본 파일(①)도 업로드해 주세요.")
