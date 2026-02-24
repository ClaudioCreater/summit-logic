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


def _load_access_key() -> str:
    """Streamlit Secrets → 환경변수 → 로컬 개발 fallback 순으로 Access Key 로드."""

    # 1순위: Streamlit Secrets (배포 환경)
    try:
        import streamlit as st
        key = st.secrets.get("ACCESS_KEY", None)
        if key:
            return str(key)
    except Exception:
        pass

    # 2순위: OS 환경변수 (Docker / CI 등)
    import os
    key = os.environ.get("SUMMIT_ACCESS_KEY", "")
    if key:
        return key

    # 3순위: 로컬 개발 전용 기본값
    # ※ 이 값은 배포 환경에서는 절대 사용되지 않습니다.
    #    Streamlit Cloud Secrets에 ACCESS_KEY가 등록되어 있으면 이 값은 무시됩니다.
    return "summit2026"


ACCESS_KEY: str = _load_access_key()


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
