"""국립중앙도서관 ISBN 서지정보 클라이언트 (seoji Open API).

알라딘 매칭으로 얻은 ISBN을 권위 있는 국가 서지(KDC 분류·판사항·정확한 출판사)로
보강하고, 알라딘 매칭이 맞는지 교차검증한다.

엔드포인트: https://www.nl.go.kr/seoji/SearchApi.do
인증: cert_key (URL 파라미터). 응답: result_style=json.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import requests

from .config import CACHE_DIR, get_nlk_cert_key
from .matching import title_similarity

SEOJI_URL = "https://www.nl.go.kr/seoji/SearchApi.do"
MIN_INTERVAL_SEC = 0.2

# 교차검증 임계값 (튜닝 가능)
VERIFY_TITLE_SIM = 0.6


@dataclass
class NLKRecord:
    """국립중앙도서관 서지 1건 (정규화)."""

    title: str
    author: str
    publisher: str
    isbn: str
    edition: str        # 판사항 (예: '개정판', '초판')
    kdc: str            # 한국십진분류
    ddc: str            # 듀이십진분류
    publish_date: str   # 발행(예정)일 YYYYMMDD
    page: str
    book_size: str

    @classmethod
    def from_api(cls, doc: dict[str, Any]) -> "NLKRecord":
        def g(*keys: str) -> str:
            for k in keys:
                v = doc.get(k)
                if v:
                    return str(v).strip()
            return ""

        return cls(
            title=g("TITLE"),
            author=g("AUTHOR"),
            publisher=g("PUBLISHER"),
            isbn=g("EA_ISBN", "SET_ISBN"),
            edition=g("EDITION_STMT"),
            kdc=g("KDC"),
            ddc=g("DDC"),
            publish_date=g("PUBLISH_PREDATE"),
            page=g("PAGE"),
            book_size=g("BOOK_SIZE"),
        )


class NLKClient:
    """seoji SearchApi 래퍼 (ISBN 조회 + 디스크 캐시)."""

    def __init__(
        self,
        cert_key: Optional[str] = None,
        cache_dir: Path = CACHE_DIR,
        use_cache: bool = True,
        timeout: int = 8,  # 보강은 best-effort — 라인마다 오래 막지 않도록 짧게
    ) -> None:
        self.cert_key = cert_key or get_nlk_cert_key()
        self.use_cache = use_cache
        self.cache_dir = cache_dir
        self.timeout = timeout
        self._session = requests.Session()
        self._last_call = 0.0
        if use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, params: dict[str, Any]) -> Path:
        sig = {k: v for k, v in params.items() if k != "cert_key"}
        h = hashlib.sha1(json.dumps(sig, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"nlk_{h}.json"

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = text.strip().lstrip("﻿")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            end = text.rfind("}")
            if end != -1:
                return json.loads(text[: end + 1])
            raise

    @staticmethod
    def _extract_docs(data: dict[str, Any]) -> list[dict[str, Any]]:
        """응답에서 서지 레코드 배열 추출 (보통 'docs', 방어적으로 첫 list)."""
        if isinstance(data.get("docs"), list):
            return data["docs"]
        for v in data.values():
            if isinstance(v, list):
                return v
        return []

    def lookup_isbn(self, isbn13: str) -> Optional[NLKRecord]:
        """ISBN13으로 국가 서지 조회. 없으면 None."""
        isbn13 = (isbn13 or "").strip()
        if not isbn13:
            return None
        params = {
            "cert_key": self.cert_key,
            "result_style": "json",
            "page_no": 1,
            "page_size": 1,
            "isbn": isbn13,
        }
        if self.use_cache:
            cpath = self._cache_path(params)
            if cpath.exists():
                data = json.loads(cpath.read_text(encoding="utf-8"))
                docs = self._extract_docs(data)
                return NLKRecord.from_api(docs[0]) if docs else None

        elapsed = time.monotonic() - self._last_call
        if self._last_call and elapsed < MIN_INTERVAL_SEC:
            time.sleep(MIN_INTERVAL_SEC - elapsed)
        self._last_call = time.monotonic()

        resp = self._session.get(SEOJI_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = self._parse_json(resp.text)
        if self.use_cache:
            cpath.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        docs = self._extract_docs(data)
        return NLKRecord.from_api(docs[0]) if docs else None


def verify_against(
    aladin_title: str,
    aladin_publisher: str,
    record: Optional[NLKRecord],
    *,
    title_threshold: float = VERIFY_TITLE_SIM,
) -> tuple[bool, str]:
    """알라딘 매칭을 국가 서지와 교차검증. (검증통과여부, 사유)."""
    if record is None:
        return (False, "국중도 서지 없음")
    sim = title_similarity(aladin_title, record.title)
    if sim < title_threshold:
        return (False, f"국중도 제목 불일치(유사도 {sim:.2f}: '{record.title[:30]}')")
    if aladin_publisher and record.publisher:
        a = aladin_publisher.replace(" ", "")
        b = record.publisher.replace(" ", "")
        if a not in b and b not in a:
            return (False, f"국중도 출판사 불일치(알라딘 '{aladin_publisher}' vs 국중도 '{record.publisher}')")
    return (True, "국중도 서지 일치")
