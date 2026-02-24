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
# 운영 환경에서는 코드에 직접 넣는 대신
# Streamlit Secrets (st.secrets["ACCESS_KEY"]) 사용을 권장합니다.
ACCESS_KEY = "summit2026"


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
