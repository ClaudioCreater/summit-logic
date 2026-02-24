# -*- coding: utf-8 -*-
"""
security_utils.py
─────────────────
사이트 보안 및 엑셀 암호 해제 유틸리티.

- ACCESS_KEY     : 사이트 접근 제어 키 (운영 환경에서는 st.secrets 교체 권장)
- unlock_excel() : msoffcrypto 를 이용한 비밀번호 엑셀 복호화
"""

import io
import msoffcrypto

# ── 사이트 접근 제어 키 ──
# 우선순위: Streamlit Secrets > 환경변수 > 로컬 개발용 기본값
#
# [배포 시 필수 설정]
# Streamlit Cloud > 앱 선택 > Settings > Secrets 탭에 아래 내용 추가:
#   ACCESS_KEY = "사장님이_정한_새_비밀번호"
#
# [로컬 개발 시]
# .streamlit/secrets.toml 파일 생성 후 동일하게 작성 (Git 추적 제외됨)


def get_access_key() -> str:
    """
    Streamlit Secrets → 환경변수 → 로컬 개발 fallback 순으로 Access Key를 반환합니다.

    [중요] 모듈 레벨 상수가 아닌 함수로 구현합니다.
    모듈 상수 방식은 Streamlit이 완전히 재시작되지 않으면 이전 값이 캐시되어
    Secrets 변경이 반영되지 않는 버그가 있기 때문입니다.

    app.py에서 매번 get_access_key()를 호출하므로 항상 최신 값이 사용됩니다.
    """
    import os

    # 1순위: Streamlit Secrets (배포 환경)
    try:
        import streamlit as st
        # st.secrets["KEY"] 방식으로 직접 접근 (KeyError는 아래에서 처리)
        if "ACCESS_KEY" in st.secrets:
            key = str(st.secrets["ACCESS_KEY"]).strip()
            if key:
                return key
    except Exception:
        pass

    # 2순위: OS 환경변수 (Docker / CI 등)
    key = os.environ.get("SUMMIT_ACCESS_KEY", "").strip()
    if key:
        return key

    # 3순위: 로컬 개발 전용 기본값
    return "summit2026"


# 하위 호환성 유지: 기존에 ACCESS_KEY를 import하는 코드가 있으면 작동하도록
# 단, 실제 검증은 반드시 get_access_key()를 직접 호출해야 Secrets 변경이 반영됨
ACCESS_KEY: str = "summit2026"  # app.py에서 get_access_key()로 교체됨


def unlock_excel(file_obj, password: str = "") -> io.BytesIO:
    """
    엑셀 파일의 암호를 해제하여 BytesIO로 반환합니다.

    Args:
        file_obj : 업로드된 파일 객체 (UploadedFile 또는 BytesIO)
        password : 엑셀 비밀번호. 빈 문자열이면 암호 없는 파일로 처리.

    Returns:
        복호화된 파일 내용을 담은 BytesIO 객체.

    Raises:
        Exception: 비밀번호가 틀리거나 파일이 손상된 경우 msoffcrypto 예외 발생.

    Example:
        >>> buf = unlock_excel(uploaded_file, "mypassword")
        >>> df = pd.read_excel(buf)
    """
    file_obj.seek(0)
    raw = file_obj.read()

    if not password.strip():
        # 비밀번호 없음 → 원본 바이트를 그대로 BytesIO 로 래핑
        return io.BytesIO(raw)

    # msoffcrypto 로 복호화
    encrypted_buf = io.BytesIO(raw)
    office_file = msoffcrypto.OfficeFile(encrypted_buf)
    office_file.load_key(password=password.strip())
    decrypted_buf = io.BytesIO()
    office_file.decrypt(decrypted_buf)
    decrypted_buf.seek(0)
    return decrypted_buf
