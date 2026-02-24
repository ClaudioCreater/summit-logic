# -*- coding: utf-8 -*-
"""
Summit Logic - 스마트스토어 송장 자동 젠더
Streamlit 웹 애플리케이션
"""

import io
import pandas as pd
import streamlit as st

# ──────────────────────────────────────────────
# 페이지 기본 설정
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Summit Logic - 송장 자동 젠더",
    page_icon="📦",
    layout="centered",
)

# ──────────────────────────────────────────────
# 전역 CSS (구글 스타일의 깔끔한 디자인)
# ──────────────────────────────────────────────
st.markdown(
    """
    <style>
        /* 배경 및 기본 폰트 */
        .main { background-color: #ffffff; }
        body { font-family: 'Google Sans', 'Noto Sans KR', sans-serif; }

        /* 상단 헤더 영역 */
        .header-area {
            text-align: center;
            padding: 48px 0 12px 0;
        }
        .header-area h1 {
            font-size: 2rem;
            font-weight: 700;
            color: #1a73e8;
            margin-bottom: 4px;
        }
        .header-area p {
            font-size: 0.95rem;
            color: #5f6368;
            line-height: 1.6;
        }

        /* 구분선 */
        .divider { border: none; border-top: 1px solid #e8eaed; margin: 24px 0; }

        /* 업로드 카드 */
        .upload-card {
            background: #f8f9fa;
            border: 1px solid #e8eaed;
            border-radius: 12px;
            padding: 24px 28px;
            margin-bottom: 16px;
        }
        .upload-card h3 {
            font-size: 1rem;
            font-weight: 600;
            color: #202124;
            margin-bottom: 8px;
        }
        .upload-card p {
            font-size: 0.82rem;
            color: #70757a;
            margin-bottom: 12px;
        }

        /* 결과 요약 카드 */
        .result-grid {
            display: flex;
            gap: 16px;
            margin: 24px 0;
        }
        .stat-card {
            flex: 1;
            background: #ffffff;
            border: 1px solid #e8eaed;
            border-radius: 12px;
            padding: 20px 16px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }
        .stat-card .stat-number {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .stat-card .stat-label {
            font-size: 0.8rem;
            color: #70757a;
        }
        .stat-total   .stat-number { color: #1a73e8; }
        .stat-matched .stat-number { color: #34a853; }
        .stat-miss    .stat-number { color: #ea4335; }

        /* 미발급 목록 */
        .miss-box {
            background: #fff8f7;
            border: 1px solid #fad2cf;
            border-radius: 8px;
            padding: 14px 18px;
            font-size: 0.85rem;
            color: #c5221f;
        }

        /* 안내 배너 */
        .info-banner {
            background: #e8f0fe;
            border-radius: 8px;
            padding: 14px 18px;
            color: #1a56a4;
            font-size: 0.88rem;
            text-align: center;
            margin-top: 8px;
        }

        /* 다운로드 버튼 스타일 오버라이드 */
        div[data-testid="stDownloadButton"] button {
            background-color: #1a73e8;
            color: white;
            border: none;
            border-radius: 24px;
            padding: 10px 32px;
            font-size: 0.95rem;
            font-weight: 600;
            width: 100%;
            cursor: pointer;
            transition: background 0.2s;
        }
        div[data-testid="stDownloadButton"] button:hover {
            background-color: #1558b0;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────
# 헤더
# ──────────────────────────────────────────────
st.markdown(
    """
    <div class="header-area">
        <h1>📦 Summit Logic</h1>
        <p>스마트스토어 주문서와 대한통운 LOIS 파일을 업로드하면<br>
        자동으로 송장번호를 매칭해 드립니다.</p>
    </div>
    <hr class="divider">
    """,
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────
# 파일 업로드 섹션
# ──────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
        <div class="upload-card">
            <h3>① 스마트스토어 주문서</h3>
            <p>네이버 스마트스토어 발주/발송 관리에서<br>다운로드한 엑셀 파일을 업로드해주세요.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    smart_file = st.file_uploader(
        "스마트스토어 주문서 (.xlsx)",
        type=["xlsx"],
        key="smart",
        label_visibility="collapsed",
    )

with col2:
    st.markdown(
        """
        <div class="upload-card">
            <h3>② 대한통운 LOIS 결과 파일</h3>
            <p>대한통운 LOIS 시스템에서 다운로드한<br>송장 발급 결과 엑셀 파일을 업로드해주세요.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cj_file = st.file_uploader(
        "대한통운 LOIS 결과 파일 (.xlsx)",
        type=["xlsx"],
        key="cj",
        label_visibility="collapsed",
    )


# ──────────────────────────────────────────────
# 매칭 실행 버튼
# ──────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
run_btn = st.button("🔍 송장번호 자동 매칭 실행", use_container_width=True)

st.markdown("<hr class='divider'>", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# 엑셀 읽기 헬퍼 (cp949 / utf-8 / openpyxl 순서로 시도)
# ──────────────────────────────────────────────
def read_excel_safe(uploaded_file) -> pd.DataFrame:
    """
    업로드된 파일을 안전하게 읽습니다.
    - xlsx 파일은 openpyxl 엔진으로 처리
    - 주문번호 앞자리 0 손실 방지를 위해 dtype=str 적용
    """
    raw = uploaded_file.read()
    buf = io.BytesIO(raw)
    df = pd.read_excel(buf, dtype=str, engine="openpyxl")
    return df


# ──────────────────────────────────────────────
# 핵심 매칭 로직 (test_run.py의 create_final_upload_file 이식)
# ──────────────────────────────────────────────
def run_matching(df_smart: pd.DataFrame, df_cj: pd.DataFrame):
    """
    스마트스토어 주문서와 대한통운 LOIS 데이터를 매칭합니다.

    반환값:
        df_final  : 최종 업로드용 DataFrame
        total     : 전체 주문 건수
        matched   : 매칭 성공 건수
        unmatched : 미발급(매칭 실패) 건수
        miss_list : 미발급 상품주문번호 목록
        warn_msg  : 경고 메시지 (없으면 None)
    """
    warn_msg = None

    # 필수 컬럼 검증 ──────────────────────────────
    required_smart = ["상품주문번호", "송장번호"]
    missing_smart = [c for c in required_smart if c not in df_smart.columns]
    if missing_smart:
        raise ValueError(f"스마트스토어 파일에 필수 컬럼이 없습니다: {missing_smart}\n실제 컬럼: {list(df_smart.columns)}")

    required_cj = ["고객주문번호", "운송장번호"]
    missing_cj = [c for c in required_cj if c not in df_cj.columns]
    if missing_cj:
        raise ValueError(f"대한통운 파일에 필수 컬럼이 없습니다: {missing_cj}\n실제 컬럼: {list(df_cj.columns)}")

    # 매칭 키 컬럼만 추출 + 중복 제거 ─────────────
    df_cj_key = df_cj[["고객주문번호", "운송장번호"]].copy()

    before = len(df_cj_key)
    df_cj_key = df_cj_key.drop_duplicates(subset="고객주문번호", keep="first")
    after = len(df_cj_key)
    if before != after:
        warn_msg = f"대한통운 파일에 중복된 고객주문번호 {before - after}건이 발견되어 첫 번째 항목만 사용했습니다."

    # LEFT JOIN 매칭 ───────────────────────────────
    df_merged = pd.merge(
        left=df_smart,
        right=df_cj_key,
        left_on="상품주문번호",
        right_on="고객주문번호",
        how="left",
    )

    # 운송장번호 → 송장번호 복사, 미매칭은 '미발급' ─
    df_merged["송장번호"] = df_merged["운송장번호"].fillna("미발급")

    # 택배사 컬럼 처리 (있을 경우에만)
    if "택배사" in df_merged.columns:
        df_merged["택배사"] = df_merged["운송장번호"].apply(
            lambda x: "CJ대한통운" if pd.notna(x) and str(x).strip() != "" else "미발급"
        )

    # 임시 컬럼 제거
    df_merged.drop(columns=["고객주문번호", "운송장번호"], errors="ignore", inplace=True)

    # 최종 컬럼 순서 정리 ──────────────────────────
    preferred_order = [
        "상품주문번호", "주문번호", "수취인명", "수취인연락처1",
        "수취인우편번호", "수취인주소", "상품명", "옵션정보",
        "수량", "택배사", "송장번호",
    ]
    existing_cols = [c for c in preferred_order if c in df_merged.columns]
    extra_cols = [c for c in df_merged.columns if c not in existing_cols]
    df_final = df_merged[existing_cols + extra_cols].copy()

    # 통계 계산 ────────────────────────────────────
    total     = len(df_final)
    matched   = int((df_final["송장번호"] != "미발급").sum())
    unmatched = total - matched
    miss_list = df_final.loc[df_final["송장번호"] == "미발급", "상품주문번호"].tolist()

    return df_final, total, matched, unmatched, miss_list, warn_msg


# ──────────────────────────────────────────────
# 엑셀 바이트 변환 (다운로드용)
# ──────────────────────────────────────────────
def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="최종업로드")
    return buf.getvalue()


# ──────────────────────────────────────────────
# 실행 분기
# ──────────────────────────────────────────────
if run_btn:
    # 파일 미업로드 처리
    if smart_file is None or cj_file is None:
        missing = []
        if smart_file is None:
            missing.append("스마트스토어 주문서")
        if cj_file is None:
            missing.append("대한통운 LOIS 결과 파일")
        st.markdown(
            f"""
            <div class="info-banner">
                📂 <b>{' 및 '.join(missing)}</b>를 먼저 업로드해주세요.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # 파일 읽기 및 매칭 실행
        try:
            with st.spinner("매칭 중... 잠시만 기다려주세요."):
                df_smart = read_excel_safe(smart_file)
                df_cj    = read_excel_safe(cj_file)
                df_final, total, matched, unmatched, miss_list, warn_msg = run_matching(df_smart, df_cj)

            # 경고 메시지
            if warn_msg:
                st.warning(warn_msg)

            # ── 결과 요약 카드 ──
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

            # 미발급 목록 표시
            if miss_list:
                miss_html = "<br>".join(f"• {o}" for o in miss_list)
                st.markdown(
                    f"""
                    <div class="miss-box">
                        <b>⚠ 미발급 주문번호 목록</b><br><br>
                        {miss_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown("<br>", unsafe_allow_html=True)

            # ── 데이터 미리보기 ──
            with st.expander("📋 결과 미리보기 (상위 10행)", expanded=False):
                st.dataframe(df_final.head(10), use_container_width=True)

            # ── 다운로드 버튼 ──
            st.markdown("<br>", unsafe_allow_html=True)
            excel_bytes = to_excel_bytes(df_final)
            st.download_button(
                label="⬇️  최종 업로드 파일 다운로드 (final_upload.xlsx)",
                data=excel_bytes,
                file_name="final_upload.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        except ValueError as ve:
            st.error(f"파일 형식 오류\n\n{ve}")
        except Exception as e:
            st.error(f"처리 중 오류가 발생했습니다.\n\n{e}")

else:
    # 초기 안내 문구 (버튼을 누르기 전)
    if smart_file is None and cj_file is None:
        st.markdown(
            """
            <div class="info-banner">
                📂 위에서 두 파일을 모두 업로드한 뒤, <b>송장번호 자동 매칭 실행</b> 버튼을 눌러주세요.
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif smart_file is None:
        st.markdown(
            """
            <div class="info-banner">
                📂 <b>스마트스토어 주문서</b> 파일을 먼저 업로드해주세요.
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif cj_file is None:
        st.markdown(
            """
            <div class="info-banner">
                📂 <b>대한통운 LOIS 결과 파일</b>을 먼저 업로드해주세요.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="info-banner">
                ✅ 두 파일이 모두 업로드되었습니다. <b>매칭 실행 버튼</b>을 눌러주세요.
            </div>
            """,
            unsafe_allow_html=True,
        )


# ──────────────────────────────────────────────
# 하단 푸터
# ──────────────────────────────────────────────
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown(
    """
    <div style="text-align:center; color:#bdc1c6; font-size:0.78rem;">
        Summit Logic &nbsp;|&nbsp; 스마트스토어 × 대한통운 LOIS 송장 자동 매칭
    </div>
    """,
    unsafe_allow_html=True,
)
