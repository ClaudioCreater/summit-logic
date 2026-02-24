# -*- coding: utf-8 -*-
"""
data_cleaner.py
───────────────
대한통운 LOIS 업로드 전 데이터 정제 함수 모음.

- clean_text()       : 이름·주소·배송메시지에서 이모지·제어문자 제거
- clean_phone()      : 전화번호 숫자만 추출 (하이픈·공백 제거)
- truncate_address() : 주소 길이 초과 시 잘라냄 (CJ LOIS 업로드 제한 대응)
"""

import re

# CJ LOIS 주소 필드 최대 허용 길이 (문자 수)
ADDRESS_MAX_LEN = 100

# ── 이모지·특수기호 범위 사전 컴파일 (모듈 로드 시 1회만 실행) ──
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FFFF"   # Misc Symbols / Emoticons / Transport 등
    "\U00002600-\U000027BF"   # Misc Symbols, Dingbats
    "\U0000200B-\U0000200F"   # Zero-width chars (ZWSP, ZWNJ, ZWJ, LRM, RLM)
    "\U0000FE00-\U0000FE0F"   # Variation Selectors
    "]+",
    flags=re.UNICODE,
)


def clean_text(text: str) -> str:
    """
    이름·주소·배송메시지에서 이모지 및 제어문자를 제거합니다.

    보존 대상: 한글, 영문, 숫자, 공백, 기본 구두점(-.,()/ 등)
    제거 대상: 이모지(😊🎉 등), 탭·줄바꿈 등 제어문자, Zero-width 문자

    Example:
        >>> clean_text("홍길동😊\\n서울시")
        '홍길동 서울시'
    """
    text = _EMOJI_RE.sub("", str(text))
    # 탭·줄바꿈·기타 제어문자를 공백으로 치환
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    # 연속 공백 압축
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def clean_phone(phone: str) -> str:
    """
    전화번호에서 숫자 이외의 모든 문자(하이픈·공백·괄호 등)를 제거합니다.

    Example:
        >>> clean_phone("010-1234-5678")
        '01012345678'
        >>> clean_phone("(010) 1234 5678")
        '01012345678'
    """
    return re.sub(r"[^0-9]", "", str(phone))


def truncate_address(address: str, max_len: int = ADDRESS_MAX_LEN) -> str:
    """
    주소가 CJ LOIS 업로드 길이 제한을 초과하면 잘라냅니다.

    Args:
        address: 원본 주소 문자열
        max_len: 허용 최대 길이 (기본값: ADDRESS_MAX_LEN = 100)

    Example:
        >>> truncate_address("A" * 120)  # 100자로 절삭
        'AAAA...(100자)'
    """
    return address[:max_len] if len(address) > max_len else address
