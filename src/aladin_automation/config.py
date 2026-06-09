"""환경설정 로딩 (알라딘 TTBKey 등).

.env 파일에서 인증키를 읽는다. 키는 절대 커밋하지 않으며 .env.example 만 공유한다.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트 (src/aladin_automation/config.py 기준 두 단계 위)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 캐시 디렉터리 (gitignore 대상)
CACHE_DIR = PROJECT_ROOT / "data" / "cache"

# .env 로드 (이미 로드돼 있으면 덮어쓰지 않음)
load_dotenv(PROJECT_ROOT / ".env")


def get_ttb_key() -> str:
    """알라딘 TTBKey 반환. 없으면 명확한 안내와 함께 예외."""
    key = os.getenv("ALADIN_TTB_KEY")
    if not key or key.startswith("ttbYOURKEY"):
        raise RuntimeError(
            "ALADIN_TTB_KEY가 설정되지 않았습니다. "
            ".env.example을 참고해 .env 파일에 발급받은 키를 넣어주세요. "
            "(키 발급: http://blog.aladin.co.kr/openapi )"
        )
    return key


def _nlk_key_value() -> str | None:
    key = os.getenv("NLK_CERT_KEY")
    if not key or key.startswith("YOURKEY"):
        return None
    return key


def has_nlk_key() -> bool:
    """국립중앙도서관 서지 API 키 설정 여부 (보강 기능 활성화 판단용)."""
    return _nlk_key_value() is not None


def get_nlk_cert_key() -> str:
    """국립중앙도서관 seoji cert_key 반환. 없으면 안내 예외."""
    key = _nlk_key_value()
    if key is None:
        raise RuntimeError(
            "NLK_CERT_KEY가 설정되지 않았습니다. "
            ".env에 발급받은 키를 넣어주세요. (발급: https://www.nl.go.kr/seoji )"
        )
    return key
