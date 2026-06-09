"""알라딘 OpenAPI 클라이언트.

기능:
- search(): 도서명/키워드 검색 (ItemSearch)
- lookup(): ISBN으로 정밀 조회 (ItemLookUp)
- 디스크 캐시: 동일 요청 재호출 방지 (5,000건/일 한도 대응)
- 레이트리밋: 호출 간 최소 간격 + 일일 호출 카운트 가드

참고: 알라딘은 인증키를 헤더가 아닌 URL 파라미터(ttbkey)로 전달한다.
"""
from __future__ import annotations

import hashlib
import html
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests

from .config import CACHE_DIR, get_ttb_key

# --- API 상수 ---
SEARCH_URL = "http://www.aladin.co.kr/ttb/api/ItemSearch.aspx"
LOOKUP_URL = "http://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"
API_VERSION = "20131101"

# 일일 호출 한도(알라딘 정책) — 안전 마진을 두고 가드
DAILY_CALL_LIMIT = 4800
# 호출 간 최소 간격(초) — 과도한 연속 호출 방지
MIN_INTERVAL_SEC = 0.2


@dataclass
class Book:
    """정규화된 도서 정보 (검색/조회 공통)."""

    title: str
    author: str
    publisher: str
    pub_date: str
    isbn13: str
    price_standard: int  # 정가
    price_sales: int      # 판매가
    stock_status: str     # 재고상태 (정상이면 빈 문자열, 아니면 "품절"/"절판" 등)
    category_name: str
    item_id: Optional[int] = None
    cover: str = ""

    @property
    def is_available(self) -> bool:
        """정상 판매(재고) 여부. stockStatus가 비어 있으면 정상으로 간주."""
        s = (self.stock_status or "").strip()
        return s == "" or s == "정상"

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> "Book":
        # 알라딘 응답의 제목/저자에 &lt; &amp; 등 HTML 엔티티가 섞여 오므로 복원
        def clean(s: str) -> str:
            return html.unescape((s or "").strip())

        return cls(
            title=clean(item.get("title", "")),
            author=clean(item.get("author", "")),
            publisher=clean(item.get("publisher", "")),
            pub_date=item.get("pubDate", "").strip(),
            isbn13=str(item.get("isbn13") or item.get("isbn") or "").strip(),
            price_standard=int(item.get("priceStandard") or 0),
            price_sales=int(item.get("priceSales") or 0),
            stock_status=(item.get("stockStatus") or "").strip(),
            category_name=item.get("categoryName", "").strip(),
            item_id=item.get("itemId"),
            cover=item.get("cover", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["is_available"] = self.is_available
        return d


@dataclass
class _RateLimiter:
    """단순 레이트리밋: 일일 카운트 + 호출 간 최소 간격."""

    daily_limit: int = DAILY_CALL_LIMIT
    min_interval: float = MIN_INTERVAL_SEC
    _count: int = 0
    _last_call: float = 0.0

    def acquire(self) -> None:
        if self._count >= self.daily_limit:
            raise RuntimeError(
                f"일일 API 호출 한도({self.daily_limit})에 도달했습니다. "
                "목록을 분할해 다음 날 처리하거나 캐시를 활용하세요."
            )
        elapsed = time.monotonic() - self._last_call
        if self._last_call and elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()
        self._count += 1

    @property
    def calls_made(self) -> int:
        return self._count


class AladinClient:
    """알라딘 OpenAPI 호출 래퍼."""

    def __init__(
        self,
        ttb_key: Optional[str] = None,
        cache_dir: Path = CACHE_DIR,
        use_cache: bool = True,
        timeout: int = 10,
    ) -> None:
        self.ttb_key = ttb_key or get_ttb_key()
        self.use_cache = use_cache
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.limiter = _RateLimiter()
        self._session = requests.Session()
        if use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # --- 내부: 캐시 ---
    def _cache_path(self, kind: str, params: dict[str, Any]) -> Path:
        # 키 제외한 파라미터로 안정적 해시 (키가 바뀌어도 캐시 유효)
        sig = {k: v for k, v in params.items() if k != "ttbkey"}
        raw = kind + json.dumps(sig, sort_keys=True, ensure_ascii=False)
        h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{kind}_{h}.json"

    def _request(self, url: str, kind: str, params: dict[str, Any]) -> dict[str, Any]:
        params = {**params, "ttbkey": self.ttb_key, "Output": "js", "Version": API_VERSION}

        if self.use_cache:
            cpath = self._cache_path(kind, params)
            if cpath.exists():
                return json.loads(cpath.read_text(encoding="utf-8"))

        self.limiter.acquire()
        resp = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = self._parse_json(resp.text)

        # 알라딘은 오류도 200으로 errorCode/errorMessage 필드로 줄 수 있음.
        # errorCode 8(해당 상품 없음)은 예외가 아니라 '결과 없음'으로 처리해 배치가 죽지 않게 한다.
        if "errorCode" in data:
            if str(data.get("errorCode")) == "8":
                data = {"item": []}
            else:
                raise RuntimeError(
                    f"알라딘 API 오류 {data.get('errorCode')}: {data.get('errorMessage')}"
                )

        if self.use_cache:
            cpath.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """알라딘 JSON 응답 파싱. 가끔 끝에 불필요한 문자가 붙어 보정."""
        text = text.strip().lstrip("﻿")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 마지막 '}' 까지만 취해 재시도
            end = text.rfind("}")
            if end != -1:
                return json.loads(text[: end + 1])
            raise

    # --- 공개 API ---
    def search(
        self,
        query: str,
        query_type: str = "Keyword",
        max_results: int = 10,
        search_target: str = "Book",
    ) -> list[Book]:
        """도서 검색. query_type: Keyword | Title | Author | Publisher."""
        data = self._request(
            SEARCH_URL,
            "search",
            {
                "Query": query,
                "QueryType": query_type,
                "MaxResults": max_results,
                "Start": 1,
                "SearchTarget": search_target,
                "Sort": "Accuracy",
                "Cover": "Small",
            },
        )
        return [Book.from_api(it) for it in data.get("item", [])]

    def lookup(self, isbn13: str) -> Optional[Book]:
        """ISBN13으로 정밀 조회. 결과 없으면 None."""
        data = self._request(
            LOOKUP_URL,
            "lookup",
            {"ItemId": isbn13, "ItemIdType": "ISBN13"},
        )
        items = data.get("item", [])
        return Book.from_api(items[0]) if items else None

    @property
    def calls_made(self) -> int:
        return self.limiter.calls_made
