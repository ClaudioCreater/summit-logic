# -*- coding: utf-8 -*-
"""
===========================================================
  Summit Logic - 스마트스토어 × 대한통운 LOIS 자동화 도구
===========================================================
[실행]  streamlit run app.py
[배포]  summitlogic.streamlit.app
===========================================================
"""

import io
import msoffcrypto
import pandas as pd
import streamlit as st
from openpyxl import load_workbook


# ===========================================================
# 상수: 네이버 스마트스토어 엑셀 컬럼 인덱스 (0-based, header=1 기준)
#
# 실제 파일 구조:
#   0행(Row 1): 안내 문구  ← 건너뜀
#   1행(Row 2): 컬럼 헤더  ← header=1 로 읽음
#   2행(Row 3)~: 실제 주문 데이터
#
# openpyxl 로 직접 셀에 접근할 때는 1-indexed:
#   데이터 시작 행: row=3
#   H열(택배사):  row_cells[7]   (0-based 리스트)
#   I열(송장번호): row_cells[8]  (0-based 리스트)
# ===========================================================
NAVER = {
    "상품주문번호":   0,   # A열
    "택배사":        7,   # H열 — 채워야 할 칸
    "송장번호":      8,   # I열 — 채워야 할 칸
    "수취인명":      13,  # N열
    "상품명":        20,  # U열
    "수량":          26,  # AA열
    "수취인연락처1":  48,  # AW열
    "합배송지":      50,  # AY열 (기본주소+상세주소 합본)
    "우편번호":      54,  # BC열
    "배송메세지":    55,  # BD열
}
NAVER_DATA_START_ROW = 3   # openpyxl 1-indexed 기준 데이터 시작 행


# ===========================================================
# 유틸 함수
# ===========================================================

def find_header_row(file_obj) -> int:
    """
    '상품주문번호' 텍스트와 정확히 일치하는 셀이 있는 행 번호를 반환합니다.

    [핵심 수정] contains() → 정확히 == "상품주문번호" 비교
    - 네이버 엑셀 Row 0 안내 문구에는 "상품주문번호"가 설명 텍스트로 포함됨
    - contains() 사용 시 Row 0을 헤더로 잘못 잡는 버그 발생
    - 정확히 일치(==)하는 셀이 있는 행만 헤더로 인정해 안내 문구 행을 완전히 배제
    """
    file_obj.seek(0)
    # nrows 제한 없이 전체 스캔 (파일 구조 변경 대응)
    df_raw = pd.read_excel(file_obj, header=None, dtype=str)
    for idx, row in df_raw.iterrows():
        # str.strip() == "상품주문번호" : 공백 제거 후 정확히 일치하는 셀이 있는 행만 선택
        if (row.astype(str).str.strip() == "상품주문번호").any():
            return int(idx)
    raise ValueError(
        "'상품주문번호' 컬럼을 찾을 수 없습니다.\n"
        "네이버 스마트스토어에서 다운로드한 원본 엑셀 파일인지 확인해 주세요."
    )


def read_naver_excel(file_obj) -> pd.DataFrame:
    """
    네이버 스마트스토어 주문 엑셀을 안전하게 읽습니다.

    1. find_header_row()로 '상품주문번호' 열이 정확히 있는 행을 헤더로 설정
    2. [데이터 정제] 아래 두 가지 불량 행을 완전히 제거:
       - 상품주문번호 열이 빈 행 (빈 줄, 합계 행 등)
       - 상품주문번호 열이 '상품주문번호' 텍스트인 행 (중복 헤더 잔재)
    3. dtype=str → 주문번호·전화번호 앞자리 0 보존
    """
    header_row = find_header_row(file_obj)
    file_obj.seek(0)
    df = pd.read_excel(file_obj, header=header_row, dtype=str)
    df = df.fillna("")

    # 첫 번째 컬럼(상품주문번호)을 기준으로 불량 행 제거
    order_col = df.columns[0]
    df = df[
        (df[order_col].str.strip() != "") &          # 빈 행 제거
        (df[order_col].str.strip() != "상품주문번호")  # 중복 헤더 잔재 제거
    ].reset_index(drop=True)

    return df


def build_cj_upload_df(df_smart: pd.DataFrame) -> pd.DataFrame:
    """
    스마트스토어 데이터프레임 → CJ 대한통운 LOIS 접수 양식 변환
    핵심: '상품주문번호' → '고객주문번호' 로 매핑 (나중에 송장 매칭 키로 사용)
    """
    df = pd.DataFrame({
        "고객주문번호": df_smart.iloc[:, NAVER["상품주문번호"]],
        "수취인명":     df_smart.iloc[:, NAVER["수취인명"]],
        "연락처":       df_smart.iloc[:, NAVER["수취인연락처1"]],
        "우편번호":     df_smart.iloc[:, NAVER["우편번호"]],
        "주소":         df_smart.iloc[:, NAVER["합배송지"]],
        "상품명":       df_smart.iloc[:, NAVER["상품명"]],
        "수량":         df_smart.iloc[:, NAVER["수량"]],
        "배송메시지":   df_smart.iloc[:, NAVER["배송메세지"]],
    })
    return df[df["고객주문번호"].str.strip() != ""].reset_index(drop=True)


def match_and_fill_waybill(smart_file_obj, cj_df: pd.DataFrame):
    """
    [템플릿 유지형 송장 매칭]
    - openpyxl 로 원본 파일 로드 → 1·2행 안내 문구 그대로 보존
    - 3행부터 데이터 행 순회: A열(상품주문번호)로 룩업 후
      H열(택배사), I열(송장번호) 셀 값만 수정
    - 나머지 서식·수식·기타 컬럼 일절 변경 없음

    반환: (엑셀 바이트, 매칭 성공 건수, 미발급 건수, 미발급 주문번호 목록)
    """
    # 고객주문번호 → 운송장번호 룩업 사전 생성 (중복 시 첫 번째 값 사용)
    cj_lookup: dict[str, str] = {}
    for _, row in cj_df.iterrows():
        key = str(row.get("고객주문번호", "")).strip()
        val = str(row.get("운송장번호", "")).strip()
        if key and key not in cj_lookup:
            cj_lookup[key] = val

    smart_file_obj.seek(0)
    wb = load_workbook(smart_file_obj)
    ws = wb.active

    matched = 0
    unmatched = 0
    unmatched_list: list[str] = []

    for row_cells in ws.iter_rows(min_row=NAVER_DATA_START_ROW, max_row=ws.max_row):
        # A열 = 상품주문번호
        order_no = str(row_cells[NAVER["상품주문번호"]].value or "").strip()
        if not order_no:
            continue

        waybill = cj_lookup.get(order_no, "")
        if waybill:
            row_cells[NAVER["택배사"]].value   = "CJ대한통운"
            row_cells[NAVER["송장번호"]].value = waybill
            matched += 1
        else:
            row_cells[NAVER["택배사"]].value   = "미발급"
            row_cells[NAVER["송장번호"]].value = "미발급"
            unmatched += 1
            unmatched_list.append(order_no)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue(), matched, unmatched, unmatched_list


def unlock_excel(file_obj, password: str = "") -> io.BytesIO:
    """
    엑셀 파일의 암호를 해제하여 BytesIO로 반환합니다.

    - password가 비어 있으면 그대로 BytesIO로 변환 (암호 없는 파일)
    - password가 있으면 msoffcrypto로 복호화 후 반환
    - 암호가 틀리면 예외가 발생해 사용자에게 오류 메시지를 표시함
    """
    file_obj.seek(0)
    raw = file_obj.read()

    if not password.strip():
        # 비밀번호 없음 → 그대로 BytesIO 반환
        return io.BytesIO(raw)

    # msoffcrypto 로 암호 해제
    encrypted_buf = io.BytesIO(raw)
    office_file = msoffcrypto.OfficeFile(encrypted_buf)
    office_file.load_key(password=password.strip())
    decrypted_buf = io.BytesIO()
    office_file.decrypt(decrypted_buf)
    decrypted_buf.seek(0)
    return decrypted_buf


def df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    """데이터프레임 → 엑셀 바이트 스트림 변환 (다운로드 버튼용)"""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    buf.seek(0)
    return buf.getvalue()


# ===========================================================
# Streamlit 페이지 설정
# ===========================================================
st.set_page_config(
    page_title="Summit Logic",
    page_icon="📦",
    layout="centered",
)

# ── 전역 CSS (Google 스타일 디자인) ──
st.markdown(
    """
    <style>
        .main { background-color: #ffffff; }
        body  { font-family: 'Google Sans', 'Noto Sans KR', sans-serif; }

        /* 상단 헤더 */
        .header-area { text-align: center; padding: 48px 0 12px 0; }
        .header-area h1 {
            font-size: 2rem; font-weight: 700;
            color: #1a73e8; margin-bottom: 4px;
        }
        .header-area p {
            font-size: 0.95rem; color: #5f6368; line-height: 1.6;
        }

        /* 구분선 */
        .divider { border: none; border-top: 1px solid #e8eaed; margin: 20px 0; }

        /* 업로드 카드 */
        .upload-card {
            background: #f8f9fa; border: 1px solid #e8eaed;
            border-radius: 12px; padding: 20px 24px; margin-bottom: 12px;
        }
        .upload-card h3 {
            font-size: 1rem; font-weight: 600;
            color: #202124; margin-bottom: 6px;
        }
        .upload-card p {
            font-size: 0.82rem; color: #70757a; margin-bottom: 10px;
        }

        /* 결과 통계 카드 */
        .result-grid { display: flex; gap: 16px; margin: 20px 0; }
        .stat-card {
            flex: 1; background: #ffffff;
            border: 1px solid #e8eaed; border-radius: 12px;
            padding: 20px 16px; text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }
        .stat-card .stat-number { font-size: 2rem; font-weight: 700; margin-bottom: 4px; }
        .stat-card .stat-label  { font-size: 0.8rem; color: #70757a; }
        .stat-total   .stat-number { color: #1a73e8; }
        .stat-matched .stat-number { color: #34a853; }
        .stat-miss    .stat-number { color: #ea4335; }

        /* 미발급 목록 박스 */
        .miss-box {
            background: #fff8f7; border: 1px solid #fad2cf;
            border-radius: 8px; padding: 14px 18px;
            font-size: 0.85rem; color: #c5221f;
        }

        /* 안내 배너 */
        .info-banner {
            background: #e8f0fe; border-radius: 8px;
            padding: 14px 18px; color: #1a56a4;
            font-size: 0.88rem; text-align: center; margin-top: 8px;
        }

        /* 다운로드 버튼 */
        div[data-testid="stDownloadButton"] button {
            background-color: #1a73e8; color: white;
            border: none; border-radius: 24px;
            padding: 10px 32px; font-size: 0.95rem;
            font-weight: 600; width: 100%; cursor: pointer;
            transition: background 0.2s;
        }
        div[data-testid="stDownloadButton"] button:hover {
            background-color: #1558b0;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── 앱 헤더 ──
st.markdown(
    """
    <div class="header-area">
        <h1>📦 Summit Logic</h1>
        <p>스마트스토어 주문서와 대한통운 LOIS 파일을 업로드하면<br>
        자동으로 접수 파일 생성 및 송장번호 매칭을 처리해 드립니다.</p>
    </div>
    <hr class="divider">
    """,
    unsafe_allow_html=True,
)


# ===========================================================
# 탭 레이아웃
# ===========================================================
tab1, tab2 = st.tabs(["  📋 1. 접수 파일 생성  ", "  🔗 2. 송장 번호 매칭  "])


# ===========================================================
# 탭 1: 접수 파일 생성
#   스마트스토어 주문서 → 대한통운 LOIS 업로드 전용 양식 변환
# ===========================================================
with tab1:

    st.markdown("#### 대한통운 LOIS 접수 파일 생성")
    st.markdown(
        """
        <div class="info-banner">
            네이버 스마트스토어 주문서를 올리면 CJ 대한통운 LOIS 업로드 전용 양식으로 변환합니다.<br>
            <small>스마트스토어 &gt; 발주(주문)확인/발송관리 &gt; 엑셀 다운로드 파일을 사용하세요.</small>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="upload-card">
            <h3>① 스마트스토어 주문서 업로드</h3>
            <p>네이버 스마트스토어에서 다운로드한 주문 엑셀 파일을 올려주세요.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    uploaded_t1 = st.file_uploader(
        "스마트스토어 주문서 (xlsx)",
        type=["xlsx"],
        key="tab1_upload",
        label_visibility="collapsed",
    )
    pw_t1 = st.text_input(
        "Excel Password (Optional)",
        type="password",
        key="tab1_pw",
        placeholder="엑셀 파일에 비밀번호가 있는 경우에만 입력하세요",
    )

    if uploaded_t1:
        try:
            # 암호 해제 후 읽기 (비밀번호 없으면 그대로 통과)
            unlocked_t1 = unlock_excel(uploaded_t1, pw_t1)
            df_smart = read_naver_excel(unlocked_t1)
            df_cj_upload = build_cj_upload_df(df_smart)
            total = len(df_cj_upload)

            # 결과 통계 카드
            st.markdown(
                f"""
                <div class="result-grid">
                    <div class="stat-card stat-total">
                        <div class="stat-number">{total}</div>
                        <div class="stat-label">변환 완료 건수</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 컬럼 매핑 안내 (접기/펼치기)
            with st.expander("컬럼 매핑 확인"):
                st.table(pd.DataFrame({
                    "스마트스토어 컬럼": [
                        "A열 상품주문번호", "N열 수취인명", "AW열 수취인연락처1",
                        "BC열 우편번호", "AY열 합배송지", "U열 상품명",
                        "AA열 수량", "BD열 배송메세지",
                    ],
                    "→ CJ LOIS 컬럼": [
                        "고객주문번호", "수취인명", "연락처",
                        "우편번호", "주소", "상품명",
                        "수량", "배송메시지",
                    ],
                }))

            # 미리보기
            with st.expander("📋 변환 결과 미리보기", expanded=True):
                st.dataframe(df_cj_upload, use_container_width=True)

            # 다운로드
            st.markdown("<br>", unsafe_allow_html=True)
            st.download_button(
                label="⬇️  CJ LOIS 접수 파일 다운로드",
                data=df_to_excel_bytes(df_cj_upload, "LOIS_접수"),
                file_name="CJ_LOIS_접수.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        except IndexError:
            st.error("컬럼 구조가 예상과 다릅니다. 네이버 스마트스토어 원본 엑셀 파일인지 확인해 주세요.")
        except Exception as e:
            st.error(f"처리 중 오류가 발생했습니다: {e}")
            with st.expander("오류 상세"):
                st.exception(e)

    else:
        st.markdown(
            """
            <div class="info-banner" style="margin-top:16px;">
                📂 스마트스토어 주문서 파일을 업로드해 주세요.
            </div>
            """,
            unsafe_allow_html=True,
        )


# ===========================================================
# 탭 2: 송장 번호 매칭
#   스마트스토어 원본 + CJ LOIS 결과 → H열(택배사)·I열(송장번호) 자동 기입
#   [템플릿 유지형]: 1·2행 안내 문구 보존, 데이터 셀만 수정
# ===========================================================
with tab2:

    st.markdown("#### 대한통운 → 스마트스토어 송장번호 자동 매칭")
    st.markdown(
        """
        <div class="info-banner">
            두 파일을 올리면 <b>상품주문번호 ↔ 고객주문번호</b> 기준으로 자동 매칭하여<br>
            H열(택배사)과 I열(송장번호)을 채운 파일을 반환합니다.<br>
            <small>원본 파일의 1·2행 양식(안내 문구)이 그대로 유지됩니다.</small>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown(
            """
            <div class="upload-card">
                <h3>① 스마트스토어 원본 파일</h3>
                <p>네이버 스마트스토어 주문 엑셀 원본 파일을 올려주세요.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        uploaded_smart_t2 = st.file_uploader(
            "스마트스토어 원본 (xlsx)",
            type=["xlsx"],
            key="tab2_smart",
            label_visibility="collapsed",
        )
        pw_t2 = st.text_input(
            "Excel Password (Optional)",
            type="password",
            key="tab2_pw",
            placeholder="비밀번호가 있는 경우에만 입력",
        )

    with col_r:
        st.markdown(
            """
            <div class="upload-card">
                <h3>② 대한통운 LOIS 결과 파일</h3>
                <p>LOIS 시스템에서 운송장 발급 후 다운로드한 결과 파일을 올려주세요.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        uploaded_cj_t2 = st.file_uploader(
            "대한통운 LOIS 결과 (xlsx)",
            type=["xlsx"],
            key="tab2_cj",
            label_visibility="collapsed",
        )

    st.markdown("<br>", unsafe_allow_html=True)
    run_btn = st.button("🔍 송장번호 자동 매칭 실행", use_container_width=True, key="run_btn")
    st.markdown("<hr class='divider'>", unsafe_allow_html=True)

    if run_btn:
        if not uploaded_smart_t2 or not uploaded_cj_t2:
            missing = []
            if not uploaded_smart_t2: missing.append("스마트스토어 원본 파일 ①")
            if not uploaded_cj_t2:    missing.append("대한통운 LOIS 결과 파일 ②")
            st.markdown(
                f'<div class="info-banner">📂 <b>{", ".join(missing)}</b>를 먼저 업로드해주세요.</div>',
                unsafe_allow_html=True,
            )
        else:
            try:
                with st.spinner("매칭 처리 중... 잠시만 기다려주세요."):
                    # 스마트스토어 파일 암호 해제 (비밀번호 없으면 그대로 통과)
                    unlocked_smart_t2 = unlock_excel(uploaded_smart_t2, pw_t2)

                    # CJ 파일 읽기 및 컬럼 검증
                    df_cj = pd.read_excel(uploaded_cj_t2, dtype=str).fillna("")
                    required_cj = ["고객주문번호", "운송장번호"]
                    missing_cols = [c for c in required_cj if c not in df_cj.columns]
                    if missing_cols:
                        raise ValueError(
                            f"대한통운 파일에 필수 컬럼이 없습니다: {missing_cols}\n"
                            f"실제 컬럼: {list(df_cj.columns)}"
                        )

                    # 매칭 실행 (암호 해제된 BytesIO 전달 — 템플릿 유지형)
                    result_bytes, matched, unmatched, unmatched_list = match_and_fill_waybill(
                        smart_file_obj=unlocked_smart_t2,
                        cj_df=df_cj,
                    )

                total = matched + unmatched

                # 결과 통계 카드
                st.markdown("### 📊 매칭 결과 요약")
                st.markdown(
                    f"""
                    <div class="result-grid">
                        <div class="stat-card stat-total">
                            <div class="stat-number">{total}</div>
                            <div class="stat-label">전체 주문 건수</div>
                        </div>
                        <div class="stat-card stat-matched">
                            <div class="stat-number">{matched}</div>
                            <div class="stat-label">✅ 매칭 성공</div>
                        </div>
                        <div class="stat-card stat-miss">
                            <div class="stat-number">{unmatched}</div>
                            <div class="stat-label">❌ 미발급</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # 미발급 목록
                if unmatched_list:
                    miss_html = "<br>".join(f"• {o}" for o in unmatched_list)
                    st.markdown(
                        f"""
                        <div class="miss-box">
                            <b>⚠ 미발급 주문번호 목록</b><br><br>{miss_html}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown("<br>", unsafe_allow_html=True)
                else:
                    st.success("모든 주문의 송장번호가 성공적으로 매칭되었습니다!")

                # 결과 미리보기 (이미 해제된 BytesIO 재사용)
                header_row_prev = find_header_row(unlocked_smart_t2)
                unlocked_smart_t2.seek(0)
                df_preview = pd.read_excel(unlocked_smart_t2, header=header_row_prev, dtype=str).fillna("")
                cj_lookup_prev = dict(
                    zip(df_cj["고객주문번호"].str.strip(), df_cj["운송장번호"].str.strip())
                )
                preview = df_preview.iloc[:, [
                    NAVER["상품주문번호"], NAVER["수취인명"],
                    NAVER["상품명"], NAVER["택배사"], NAVER["송장번호"],
                ]].copy()
                preview.columns = ["상품주문번호", "수취인명", "상품명", "택배사", "송장번호"]
                for i, row in preview.iterrows():
                    key = str(row["상품주문번호"]).strip()
                    wb_no = cj_lookup_prev.get(key, "")
                    preview.at[i, "택배사"]  = "CJ대한통운" if wb_no else "미발급"
                    preview.at[i, "송장번호"] = wb_no if wb_no else "미발급"
                preview = preview[preview["상품주문번호"].str.strip() != ""]

                with st.expander("📋 결과 미리보기", expanded=False):
                    st.dataframe(preview, use_container_width=True)

                # 다운로드
                st.markdown("<br>", unsafe_allow_html=True)
                st.download_button(
                    label="⬇️  송장번호 기입 완료된 스마트스토어 파일 다운로드",
                    data=result_bytes,
                    file_name="스마트스토어_송장입력완료.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
                st.caption(
                    "다운로드한 파일을 스마트스토어 "
                    "'발주(주문)확인/발송관리 > 일괄발송 처리' 메뉴에서 업로드하세요."
                )

            except ValueError as ve:
                st.error(f"파일 형식 오류\n\n{ve}")
            except Exception as e:
                st.error(f"처리 중 오류가 발생했습니다: {e}")
                with st.expander("오류 상세"):
                    st.exception(e)

    else:
        if uploaded_smart_t2 and uploaded_cj_t2:
            st.markdown(
                '<div class="info-banner">✅ 두 파일이 모두 업로드되었습니다. <b>매칭 실행 버튼</b>을 눌러주세요.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="info-banner">📂 위에서 두 파일을 모두 업로드한 뒤 매칭 실행 버튼을 눌러주세요.</div>',
                unsafe_allow_html=True,
            )


# ===========================================================
# 하단 푸터
# ===========================================================
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown(
    """
    <div style="text-align:center; color:#bdc1c6; font-size:0.78rem;">
        Summit Logic &nbsp;|&nbsp; 스마트스토어 × 대한통운 LOIS 자동화
    </div>
    """,
    unsafe_allow_html=True,
)
