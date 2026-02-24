# -*- coding: utf-8 -*-
"""
app.py — Summit Logic V3
─────────────────────────
Streamlit 메인 진입점. UI 구성 및 탭 레이아웃만 담당합니다.

핵심 로직은 아래 모듈에서 import합니다:
  data_cleaner      → 이모지·전화번호·주소 정제 함수
  security_utils    → Access Key 상수, 엑셀 암호 해제
  logistics_engine  → 헤더 탐색, 엑셀 읽기, 접수 파일 생성, 송장 매칭

[실행]  streamlit run app.py
[배포]  summitlogic.streamlit.app
"""

import pandas as pd
import streamlit as st

from data_cleaner import clean_text, clean_phone, truncate_address
from security_utils import ACCESS_KEY, unlock_excel
from logistics_engine import (
    NAVER,
    find_header_row,
    read_naver_excel,
    build_cj_upload_df,
    match_and_fill_waybill,
    df_to_excel_bytes,
    map_cj_columns,
    diagnose_smart_file,
)


# ===========================================================
# Streamlit 페이지 설정
# ===========================================================
st.set_page_config(
    page_title="Summit Logic",
    page_icon="📦",
    layout="centered",
)

# ── 전역 CSS ──
st.markdown(
    """
    <style>
        .main { background-color: #ffffff; }
        body  { font-family: 'Google Sans', 'Noto Sans KR', sans-serif; }

        .header-area { text-align: center; padding: 48px 0 12px 0; }
        .header-area h1 {
            font-size: 2rem; font-weight: 700;
            color: #1a73e8; margin-bottom: 4px;
        }
        .header-area p {
            font-size: 0.95rem; color: #5f6368; line-height: 1.6;
        }

        .divider { border: none; border-top: 1px solid #e8eaed; margin: 20px 0; }

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

        .result-grid { display: flex; gap: 16px; margin: 20px 0; flex-wrap: wrap; }
        .stat-card {
            flex: 1; min-width: 100px;
            background: #ffffff; border: 1px solid #e8eaed;
            border-radius: 12px; padding: 20px 16px; text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }
        .stat-card .stat-number { font-size: 2rem; font-weight: 700; margin-bottom: 4px; }
        .stat-card .stat-label  { font-size: 0.8rem; color: #70757a; }
        .stat-total   .stat-number { color: #1a73e8; }
        .stat-matched .stat-number { color: #34a853; }
        .stat-miss    .stat-number { color: #ea4335; }
        .stat-bundle  .stat-number { color: #f9ab00; }

        .miss-box {
            background: #fff8f7; border: 1px solid #fad2cf;
            border-radius: 8px; padding: 14px 18px;
            font-size: 0.85rem; color: #c5221f;
        }
        .info-banner {
            background: #e8f0fe; border-radius: 8px;
            padding: 14px 18px; color: #1a56a4;
            font-size: 0.88rem; text-align: center; margin-top: 8px;
        }
        .bundle-info {
            background: #e6f4ea; border: 1px solid #ceead6;
            border-radius: 8px; padding: 12px 16px;
            font-size: 0.85rem; color: #137333; margin: 8px 0;
        }
        .lock-overlay {
            background: #f8f9fa; border: 1px dashed #dadce0;
            border-radius: 16px; padding: 52px 24px;
            text-align: center; color: #5f6368; margin-top: 24px;
        }
        .lock-overlay .lock-icon { font-size: 3rem; margin-bottom: 12px; }
        .lock-overlay h2 { color: #202124; font-size: 1.3rem; margin-bottom: 8px; }
        .lock-overlay p  { font-size: 0.92rem; line-height: 1.7; }

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


# ===========================================================
# 사이드바: Access Key (security_utils.ACCESS_KEY 참조)
# ===========================================================
with st.sidebar:
    st.markdown("### 🔐 Access Control")
    st.markdown("---")
    access_input = st.text_input(
        "Access Key",
        type="password",
        placeholder="접속 키를 입력하세요",
        key="access_key",
    )
    if access_input == ACCESS_KEY:
        st.success("✅ 인증 완료")
    elif access_input:
        st.error("❌ 잘못된 접속 키")
    else:
        st.info("키를 입력하면 기능이 활성화됩니다")

    st.markdown("---")

    # ── 개인정보 처리 방침 (사이드바) ──
    with st.expander("🔒 개인정보 처리 방침"):
        st.markdown(
            """
            <div style="font-size:0.82rem; color:#3c4043; line-height:1.8;">
            <b>Summit Logic 데이터 처리 원칙</b><br><br>
            📋 <b>서버 무저장 원칙</b><br>
            &nbsp;&nbsp;업로드된 파일은 어떠한 서버에도<br>
            &nbsp;&nbsp;저장·기록되지 않습니다.<br><br>
            ⚡ <b>즉시 파기</b><br>
            &nbsp;&nbsp;변환·매칭 완료 즉시 메모리에서<br>
            &nbsp;&nbsp;완전히 삭제됩니다.<br><br>
            🔐 <b>암호화 전송</b><br>
            &nbsp;&nbsp;모든 통신은 HTTPS로 암호화됩니다.<br><br>
            👤 <b>제3자 미제공</b><br>
            &nbsp;&nbsp;개인정보를 외부에 제공하거나<br>
            &nbsp;&nbsp;판매하지 않습니다.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.caption("Summit Logic V3.1")


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
# Access Key 게이트 — 인증 실패 시 이하 모든 기능 차단
# ===========================================================
if access_input != ACCESS_KEY:
    st.markdown(
        """
        <div class="lock-overlay">
            <div class="lock-icon">🔐</div>
            <h2>접근 제한</h2>
            <p>
                좌측 사이드바에 <b>Access Key</b>를 입력해야<br>
                파일 업로드 및 변환 기능을 사용할 수 있습니다.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


# ===========================================================
# 탭 레이아웃 (인증 통과 후에만 표시)
# ===========================================================
tab1, tab2 = st.tabs(["  📋 1. 접수 파일 생성  ", "  🔗 2. 송장 번호 매칭  "])


# ===========================================================
# 탭 1: 접수 파일 생성
#   스마트스토어 주문서 → CJ LOIS 접수 양식 변환
#   (합배송 자동 감지 + 데이터 정제 포함)
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
            unlocked_t1 = unlock_excel(uploaded_t1, pw_t1)

            # ── [V3.1] 헤더 위치 탐색 (진단용) ──
            detected_header_row = find_header_row(unlocked_t1)
            df_smart = read_naver_excel(unlocked_t1)

            # ── [V3.1] 진단 모드: 인식된 헤더 정보 표시 ──
            diag = diagnose_smart_file(df_smart, detected_header_row)
            with st.expander("🔍 파일 인식 진단 결과 (클릭하여 확인)", expanded=False):
                st.markdown(
                    f"**헤더 행**: Row {diag['header_row'] + 1} &nbsp;|&nbsp; "
                    f"**전체 컬럼**: {diag['total_cols']}개 &nbsp;|&nbsp; "
                    f"**주문 데이터**: {diag['total_rows']}행",
                )
                rows_diag = []
                for logical, (idx, actual, ok) in diag["key_cols"].items():
                    rows_diag.append({
                        "필드": logical,
                        "열 번호": f"{idx}번열",
                        "인식된 컬럼명": actual,
                        "상태": "✅ 정상" if ok else "⚠️ 확인 필요",
                    })
                st.dataframe(
                    pd.DataFrame(rows_diag),
                    use_container_width=True,
                    hide_index=True,
                )

            df_cj_upload, original_count = build_cj_upload_df(df_smart)
            total   = len(df_cj_upload)
            bundled = original_count - total

            # ── 결과 통계 카드 ──
            bundle_html = (
                f'<div class="stat-card stat-bundle">'
                f'<div class="stat-number">{bundled}</div>'
                f'<div class="stat-label">🔗 합배송 절약 건</div>'
                f'</div>'
            ) if bundled > 0 else ""

            st.markdown(
                f"""
                <div class="result-grid">
                    <div class="stat-card stat-total">
                        <div class="stat-number">{original_count}</div>
                        <div class="stat-label">원본 주문 건수</div>
                    </div>
                    <div class="stat-card stat-matched">
                        <div class="stat-number">{total}</div>
                        <div class="stat-label">✅ 발송 건수</div>
                    </div>
                    {bundle_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

            if bundled > 0:
                st.markdown(
                    f"""
                    <div class="bundle-info">
                        🔗 <b>합배송 {bundled}건 자동 감지</b> — 수취인·연락처·주소가 동일한 주문을
                        1건으로 묶었습니다. 상품명은 <code>상품A 외 N건</code> 형태로 요약되었습니다.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with st.expander("컬럼 매핑 확인"):
                st.table(pd.DataFrame({
                    "스마트스토어 컬럼": [
                        "A열 상품주문번호", "N열 수취인명", "AW열 수취인연락처1",
                        "BC열 우편번호",    "AY열 합배송지", "U열 상품명",
                        "AA열 수량",        "BD열 배송메세지",
                    ],
                    "→ CJ LOIS 컬럼": [
                        "고객주문번호",        "수취인명 (이모지 제거)",
                        "연락처 (숫자만)",     "우편번호",
                        "주소 (이모지·100자)", "상품명 (합배송 요약)",
                        "수량 (합산)",         "배송메시지 (이모지 제거)",
                    ],
                }))

            with st.expander("📋 변환 결과 미리보기", expanded=True):
                st.dataframe(df_cj_upload, use_container_width=True)

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
#   스마트스토어 원본 + CJ LOIS 결과 → 송장번호 자동 기입
#   합배송 묶음 전체에 동일 송장번호 입력
# ===========================================================
with tab2:

    st.markdown("#### 대한통운 → 스마트스토어 송장번호 자동 매칭")
    st.markdown(
        """
        <div class="info-banner">
            두 파일을 올리면 <b>상품주문번호 ↔ 고객주문번호</b> 기준으로 자동 매칭하여<br>
            H열(택배사)과 I열(송장번호)을 채운 파일을 반환합니다.<br>
            <small>합배송 묶음 주문은 동일한 송장번호가 모든 관련 행에 자동 입력됩니다.</small>
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

    # ── [V3.1] 파일 업로드 즉시 진단 (버튼 클릭 전에도 표시) ──
    if uploaded_smart_t2 or uploaded_cj_t2:
        with st.expander("🔍 파일 인식 진단 결과 (클릭하여 확인)", expanded=False):
            diag_col1, diag_col2 = st.columns(2)

            with diag_col1:
                st.markdown("**① 스마트스토어 파일**")
                if uploaded_smart_t2:
                    try:
                        _buf_diag = unlock_excel(uploaded_smart_t2, pw_t2)
                        _hdr = find_header_row(_buf_diag)
                        _buf_diag.seek(0)
                        import pandas as _pd
                        _df_diag = _pd.read_excel(_buf_diag, header=_hdr, dtype=str, nrows=0)
                        st.markdown(
                            f"헤더 위치: **Row {_hdr + 1}** &nbsp;|&nbsp; "
                            f"컬럼 수: **{len(_df_diag.columns)}개**"
                        )
                        _key_checks = [
                            ("상품주문번호", NAVER["상품주문번호"]),
                            ("수취인명",     NAVER["수취인명"]),
                            ("택배사",       NAVER["택배사"]),
                            ("송장번호",     NAVER["송장번호"]),
                        ]
                        for logical, idx in _key_checks:
                            if idx < len(_df_diag.columns):
                                actual = str(_df_diag.columns[idx])
                                icon = "✅" if logical in actual or actual in logical else "⚠️"
                                st.caption(f"{icon} {idx}번열 → `{actual}`")
                            else:
                                st.caption(f"❌ {idx}번열 없음")
                    except Exception as _e:
                        st.warning(f"진단 중 오류: {_e}")
                else:
                    st.caption("파일을 업로드하면 진단 결과가 표시됩니다.")

            with diag_col2:
                st.markdown("**② CJ LOIS 파일**")
                if uploaded_cj_t2:
                    try:
                        _df_cj_diag = pd.read_excel(uploaded_cj_t2, dtype=str, nrows=0)
                        uploaded_cj_t2.seek(0)
                        st.markdown(f"컬럼 수: **{len(_df_cj_diag.columns)}개**")
                        try:
                            _cj_map = map_cj_columns(_df_cj_diag)
                            st.caption(f"✅ 주문번호 컬럼 → `{_cj_map['order']}`")
                            st.caption(f"✅ 운송장 컬럼  → `{_cj_map['waybill']}`")
                        except ValueError as _ve:
                            st.warning(str(_ve).split("\n")[0])
                    except Exception as _e:
                        st.warning(f"진단 중 오류: {_e}")
                else:
                    st.caption("파일을 업로드하면 진단 결과가 표시됩니다.")

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
                    unlocked_smart_t2 = unlock_excel(uploaded_smart_t2, pw_t2)

                    df_cj = pd.read_excel(uploaded_cj_t2, dtype=str).fillna("")

                    # [V3.1] 지능형 컬럼 탐색으로 유효성 검사 (정확한 오류 메시지 포함)
                    cj_detected = map_cj_columns(df_cj)  # ValueError 시 즉시 중단

                    result_bytes, matched, unmatched, unmatched_list = match_and_fill_waybill(
                        smart_file_obj=unlocked_smart_t2,
                        cj_df=df_cj,
                    )

                total = matched + unmatched

                # ── [V3.1] 인식된 컬럼 정보 표시 ──
                st.markdown(
                    f"<small style='color:#5f6368;'>✅ 주문번호 컬럼 → "
                    f"<code>{cj_detected['order']}</code> &nbsp;|&nbsp; "
                    f"✅ 운송장 컬럼 → "
                    f"<code>{cj_detected['waybill']}</code></small>",
                    unsafe_allow_html=True,
                )

                # ── 결과 통계 ──
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

                if unmatched_list:
                    miss_html = "<br>".join(f"• {o}" for o in unmatched_list)
                    st.markdown(
                        f'<div class="miss-box"><b>⚠ 미발급 주문번호 목록</b><br><br>{miss_html}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown("<br>", unsafe_allow_html=True)
                else:
                    st.success("모든 주문의 송장번호가 성공적으로 매칭되었습니다!")

                # ── 결과 미리보기 ──
                header_row_prev = find_header_row(unlocked_smart_t2)
                unlocked_smart_t2.seek(0)
                df_preview = pd.read_excel(
                    unlocked_smart_t2, header=header_row_prev, dtype=str
                ).fillna("")

                cj_lkp = dict(
                    zip(df_cj["고객주문번호"].str.strip(), df_cj["운송장번호"].str.strip())
                )
                ck = pd.DataFrame({
                    "order_no": df_preview.iloc[:, NAVER["상품주문번호"]].str.strip(),
                    "name":  df_preview.iloc[:, NAVER["수취인명"]].apply(
                                 lambda x: clean_text(str(x))),
                    "phone": df_preview.iloc[:, NAVER["수취인연락처1"]].apply(
                                 lambda x: clean_phone(str(x))),
                    "addr":  df_preview.iloc[:, NAVER["합배송지"]].apply(
                                 lambda x: truncate_address(clean_text(str(x)))),
                })
                rep_prev: dict = {}
                for _, grp in ck.groupby(["name", "phone", "addr"], sort=False):
                    ords = grp["order_no"].tolist()
                    r = ords[0]
                    for o in ords:
                        rep_prev[o] = r

                preview = df_preview.iloc[:, [
                    NAVER["상품주문번호"], NAVER["수취인명"],
                    NAVER["상품명"], NAVER["택배사"], NAVER["송장번호"],
                ]].copy()
                preview.columns = ["상품주문번호", "수취인명", "상품명", "택배사", "송장번호"]
                preview = preview[preview["상품주문번호"].str.strip() != ""].copy()

                for i, row in preview.iterrows():
                    key  = str(row["상품주문번호"]).strip()
                    rep  = rep_prev.get(key, key)
                    wb_n = cj_lkp.get(rep, "") or cj_lkp.get(key, "")
                    preview.at[i, "택배사"]  = "CJ대한통운" if wb_n else "미발급"
                    preview.at[i, "송장번호"] = wb_n if wb_n else "미발급"

                with st.expander("📋 결과 미리보기", expanded=False):
                    st.dataframe(preview, use_container_width=True)

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
# 하단 푸터 + 개인정보 처리 방침 배너
# ===========================================================
st.markdown("<br><br>", unsafe_allow_html=True)

# 개인정보 처리 방침 배너 (푸터 상단)
st.markdown(
    """
    <div style="
        background: #f0f4ff;
        border: 1px solid #d2e3fc;
        border-radius: 10px;
        padding: 14px 20px;
        margin-bottom: 16px;
        display: flex;
        align-items: flex-start;
        gap: 12px;
    ">
        <span style="font-size:1.3rem;">🔒</span>
        <div style="font-size:0.82rem; color:#3c4043; line-height:1.8;">
            <b style="color:#1a56a4;">개인정보 보호 안내</b><br>
            본 서비스는 사용자가 업로드한 엑셀 파일을 <b>서버에 저장하지 않습니다.</b>
            모든 데이터는 변환·매칭 처리가 완료되는 즉시 메모리에서 완전히 파기되며,
            개인정보(수취인명, 연락처, 주소 등)를 외부에 제공하거나 분석에 활용하지 않습니다.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# 푸터
st.markdown(
    """
    <div style="text-align:center; color:#bdc1c6; font-size:0.78rem;">
        Summit Logic V3.1 &nbsp;|&nbsp; 스마트스토어 × 대한통운 LOIS 자동화
        &nbsp;&nbsp;·&nbsp;&nbsp;
        업로드된 파일은 서버에 저장되지 않으며 처리 즉시 메모리에서 삭제됩니다.
    </div>
    """,
    unsafe_allow_html=True,
)
