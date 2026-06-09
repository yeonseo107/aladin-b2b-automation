"""매칭 엔진.

거래처가 보낸 도서명(+선택 저자)을 알라딘 검색 결과 후보와 대조해
신뢰도 점수를 매기고 '자동 확정 / 검토필요 / 실패'로 분류한다.

핵심 설계: 완벽 자동화 대신 '검증 가능한 자동화'.
애매한 건은 사람이 확인하도록 플래그하여 노동의 대부분을 제거하되 오매칭을 막는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Optional

from .aladin_client import Book


class MatchStatus(str, Enum):
    CONFIRMED = "확정"      # 자동 확정 (사람 확인 불필요)
    REVIEW = "검토필요"      # 사람 확인 권장
    FAILED = "실패"         # 매칭 후보 없음


# --- 임계값 (튜닝 가능) ---
CONFIRM_THRESHOLD = 0.85   # 이 점수 이상이면 확정 후보
STRONG_TITLE_SIM = 0.90    # 제목 유사도가 이 이상이면 '강한 후보'
AMBIGUOUS_GAP = 0.06       # 강한 후보 2개 이상의 점수 차가 이보다 작으면 모호(판본 경쟁)

# 점수 가중치 (저자 정보가 있을 때)
W_TITLE = 0.7
W_AUTHOR = 0.3

# 단행본 요청 대상이 아닌 묶음/특수포맷 (후보에서 제외)
_EXCLUDE_FORMAT = re.compile(r"세트|전\s?\d+\s?권|합본|박스\s?세트|큰글자")
# 내용 자체가 다른 판본 구분자 (있으면 사람 확인 필요) — 단순 표지/에디션 차이와 구분
_CONTENT_MARKERS = re.compile(r"개정판|개정증보|증보|청소년|영문판|영어판|원서|만화|그림책|필사")


@dataclass
class Candidate:
    book: Book
    score: float
    title_sim: float
    author_match: bool


@dataclass
class MatchResult:
    query_title: str
    query_author: str
    status: MatchStatus
    book: Optional[Book]            # 선택된 도서 (실패 시 None)
    confidence: float               # 0.0 ~ 1.0
    reasons: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)  # 상위 후보 (검토용)


# --- 정규화/유사도 ---
_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NONWORD = re.compile(r"[\s\-_/.,:;!?'\"·…|]+")


def normalize_title(title: str) -> str:
    """부제·괄호·기호·공백을 제거해 핵심 제목만 남긴다."""
    # 부제 분리: ' - ' 앞부분을 핵심 제목으로
    core = re.split(r"\s-\s", title, maxsplit=1)[0]
    core = _PAREN.sub("", core)          # (…) [...] 제거
    core = _NONWORD.sub("", core)        # 기호/공백 제거
    return core.lower()


def title_similarity(a: str, b: str) -> float:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # 한쪽이 다른 쪽을 포함하면 강한 일치(단, 동일치 1.0보다는 낮게).
    # 0.95는 속편("미움받을 용기 2") 같은 확장 제목을 동일서로 오인시켜 0.90으로 낮춤.
    if na in nb or nb in na:
        return 0.90
    return SequenceMatcher(None, na, nb).ratio()


def _author_matches(query_author: str, book_author: str) -> bool:
    if not query_author:
        return False
    q = _NONWORD.sub("", query_author).lower()
    b = _NONWORD.sub("", book_author).lower()
    if not q:
        return False
    return q in b


def score_candidate(query_title: str, query_author: str, book: Book) -> Candidate:
    t_sim = title_similarity(query_title, book.title)
    a_match = _author_matches(query_author, book.author)
    if query_author:
        score = W_TITLE * t_sim + W_AUTHOR * (1.0 if a_match else 0.0)
    else:
        score = t_sim
    return Candidate(book=book, score=round(score, 4), title_sim=round(t_sim, 4), author_match=a_match)


def match(query_title: str, query_author: str, books: list[Book], top_n: int = 3) -> MatchResult:
    """검색 결과 후보들을 점수화해 매칭 결과를 만든다."""
    if not books:
        return MatchResult(
            query_title=query_title,
            query_author=query_author,
            status=MatchStatus.FAILED,
            book=None,
            confidence=0.0,
            reasons=["검색 결과 없음"],
        )

    # 세트/합본/큰글자 등 묶음·특수포맷은 단행본 요청 대상이 아니므로 후보에서 제외
    pool = [b for b in books if not _EXCLUDE_FORMAT.search(b.title)] or books
    ranked = sorted(
        (score_candidate(query_title, query_author, b) for b in pool),
        key=lambda c: c.score,
        reverse=True,
    )
    top = ranked[0]
    chosen = top

    reasons: list[str] = []
    status = MatchStatus.CONFIRMED

    # 점수 미달 → 검토
    if top.score < CONFIRM_THRESHOLD:
        status = MatchStatus.REVIEW
        reasons.append(f"최고 점수 {top.score} < 확정기준 {CONFIRM_THRESHOLD}")

    # 제목이 거의 동일한 '강한 후보'가 top과 비슷한 점수로 2개 이상 → 판본 경쟁
    rivals = [
        c for c in ranked
        if c.title_sim >= STRONG_TITLE_SIM and (top.score - c.score) < AMBIGUOUS_GAP
    ]
    if len(rivals) >= 2:
        pubs = {c.book.publisher for c in rivals}
        content_flags = [bool(_CONTENT_MARKERS.search(c.book.title)) for c in rivals]
        single_pub = len(pubs) == 1 and "" not in pubs
        mixed_content = any(content_flags) and not all(content_flags)
        if single_pub and not mixed_content:
            # 같은 출판사의 순수 표지/에디션 차이 → 대표 판본 자동 선택
            # (재고 우선 → 부가표기(괄호) 적음 → 제목 짧음 순으로 표준판 추정)
            chosen = min(
                rivals,
                key=lambda c: (not c.book.is_available, c.book.title.count("("), len(c.book.title)),
            )
            reasons.append(
                f"동일 출판사 판본 {len(rivals)}건 중 대표 자동선택 (다른 판본 {len(rivals) - 1}종 존재)"
            )
        else:
            status = MatchStatus.REVIEW
            why = "출판사 상이" if not single_pub else "개정판/청소년판 등 내용 구분 존재"
            reasons.append(
                f"동일 제목 강한 후보 {len(rivals)}건 ({why}) — 판본 선택 확인 필요"
            )

    # 절판/품절 → 견적 불가 가능성, 검토
    if not chosen.book.is_available:
        status = MatchStatus.REVIEW
        reasons.append(f"재고상태 '{chosen.book.stock_status}' — 납품 가능 여부 확인 필요")

    if status == MatchStatus.CONFIRMED and not reasons:
        reasons.append("제목/저자 일치도 높고 경쟁 후보 없음")

    return MatchResult(
        query_title=query_title,
        query_author=query_author,
        status=status,
        book=chosen.book,
        confidence=chosen.score,
        reasons=reasons,
        candidates=ranked[:top_n],
    )
