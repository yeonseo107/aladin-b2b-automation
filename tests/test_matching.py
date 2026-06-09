"""매칭 엔진 단위 테스트 (네트워크 미사용)."""
from aladin_automation.matching import (
    MatchStatus,
    match,
    normalize_title,
    title_similarity,
)
from conftest import make_book


def test_normalize_title_strips_subtitle_and_symbols():
    assert normalize_title("미움받을 용기 (스페셜) - 부제입니다") == "미움받을용기"


def test_title_similarity_exact_vs_contains():
    assert title_similarity("데미안", "데미안") == 1.0
    # 포함은 강하지만 동일치보다 낮음 (속편/확장판 오인 방지)
    assert title_similarity("미움받을 용기", "미움받을 용기 2") == 0.90


def test_no_results_is_failure():
    r = match("없는책", "", [])
    assert r.status == MatchStatus.FAILED
    assert r.book is None


def test_single_clear_match_confirmed():
    books = [make_book("아몬드", isbn13="9791198363510")]
    r = match("아몬드", "저자", books)
    assert r.status == MatchStatus.CONFIRMED
    assert r.book.isbn13 == "9791198363510"


def test_multi_publisher_editions_go_review():
    books = [
        make_book("데미안", author="헤르만 헤세", publisher="민음사", isbn13="111"),
        make_book("데미안", author="헤르만 헤세", publisher="문학동네", isbn13="222"),
    ]
    r = match("데미안", "헤르만 헤세", books)
    assert r.status == MatchStatus.REVIEW


def test_same_publisher_cosmetic_editions_auto_pick():
    # 같은 출판사의 표지/에디션 차이 → 대표 자동선택(확정), 깔끔한 제목 우선
    books = [
        make_book("불편한 편의점 (양장 한정판)", author="김호연", publisher="나무옆의자", isbn13="222"),
        make_book("불편한 편의점", author="김호연", publisher="나무옆의자", isbn13="111"),
    ]
    r = match("불편한 편의점", "김호연", books)
    assert r.status == MatchStatus.CONFIRMED
    assert r.book.isbn13 == "111"  # 부가표기 없는 표준판 선택


def test_content_marker_editions_go_review():
    # 개정판/청소년판 등 내용 구분이 섞이면 검토
    books = [
        make_book("파친코 1", author="이민진", publisher="인플루엔셜", isbn13="111"),
        make_book("파친코 1 - 개정판", author="이민진", publisher="인플루엔셜", isbn13="222"),
    ]
    r = match("파친코 1", "이민진", books)
    assert r.status == MatchStatus.REVIEW


def test_bundle_excluded_from_candidates():
    # 세트는 단행본 요청 대상이 아니므로 후보에서 제외 → 단행본이 선택됨
    books = [
        make_book("[세트] 해리포터 1~7 세트", author="조앤 롤링", isbn13="set"),
        make_book("해리포터 1", author="조앤 롤링", isbn13="single"),
    ]
    r = match("해리포터 1", "조앤 롤링", books)
    assert r.book.isbn13 == "single"


def test_out_of_stock_goes_review():
    books = [make_book("절판도서", stock_status="절판")]
    r = match("절판도서", "저자", books)
    assert r.status == MatchStatus.REVIEW
