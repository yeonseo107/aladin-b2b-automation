"""국중도 보강·교차검증 단위 테스트 (오프라인 — 가짜 클라이언트)."""
from aladin_automation.matching import MatchResult, MatchStatus
from aladin_automation.nlk_client import NLKRecord, verify_against
from aladin_automation.quote import build_quote_lines
from conftest import make_book


def _rec(title="아몬드", publisher="창비", kdc="813.7", edition="초판"):
    return NLKRecord(title=title, author="손원평", publisher=publisher, isbn="9791198363510",
                     edition=edition, kdc=kdc, ddc="", publish_date="20170331", page="263", book_size="20")


class _FakeNLK:
    """lookup_isbn만 흉내내는 가짜 클라이언트."""
    def __init__(self, record):
        self.record = record

    def lookup_isbn(self, isbn13):
        return self.record


def _confirmed(book):
    return MatchResult(query_title=book.title, query_author="", status=MatchStatus.CONFIRMED,
                       book=book, confidence=1.0, reasons=["제목/저자 일치"])


# --- from_api 파싱 ---
def test_record_from_api():
    rec = NLKRecord.from_api({"TITLE": " 아몬드 ", "PUBLISHER": "창비", "KDC": "813.7", "EDITION_STMT": "개정판"})
    assert rec.title == "아몬드" and rec.publisher == "창비" and rec.kdc == "813.7" and rec.edition == "개정판"


# --- verify_against ---
def test_verify_match():
    ok, _ = verify_against("아몬드", "창비", _rec())
    assert ok is True


def test_verify_title_mismatch():
    ok, why = verify_against("아몬드", "창비", _rec(title="완전히 다른 책 제목"))
    assert ok is False and "제목" in why


def test_verify_publisher_mismatch():
    ok, why = verify_against("아몬드", "창비", _rec(publisher="다른출판사"))
    assert ok is False and "출판사" in why


def test_verify_none_record():
    ok, _ = verify_against("아몬드", "창비", None)
    assert ok is False


# --- build_quote_lines 보강 ---
def test_enrich_fills_kdc_edition_and_verifies():
    book = make_book("아몬드", publisher="창비", isbn13="9791198363510", price_standard=10000)
    lines = build_quote_lines([(_confirmed(book), 2)], 0.10, nlk_client=_FakeNLK(_rec()))
    ln = lines[0]
    assert ln.kdc == "813.7" and ln.edition == "초판"
    assert ln.nlk_verified is True
    assert ln.status == MatchStatus.CONFIRMED.value  # 일치 → 확정 유지


def test_enrich_mismatch_downgrades_confirmed_to_review():
    book = make_book("아몬드", publisher="창비", isbn13="9791198363510", price_standard=10000)
    lines = build_quote_lines([(_confirmed(book), 1)], 0.10,
                              nlk_client=_FakeNLK(_rec(title="엉뚱한 책")))
    ln = lines[0]
    assert ln.nlk_verified is False
    assert ln.status == MatchStatus.REVIEW.value  # 불일치 → 검토로 강등
    assert "교차검증 실패" in ln.reasons


def test_enrich_missing_record_does_not_downgrade():
    book = make_book("아몬드", publisher="창비", isbn13="x", price_standard=10000)
    lines = build_quote_lines([(_confirmed(book), 1)], 0.10, nlk_client=_FakeNLK(None))
    ln = lines[0]
    assert ln.nlk_verified is None
    assert ln.status == MatchStatus.CONFIRMED.value  # 서지 없음은 반증 아님
    assert "국중도 서지 없음" in ln.reasons


def test_no_nlk_client_is_backward_compatible():
    book = make_book("아몬드", price_standard=10000)
    lines = build_quote_lines([(_confirmed(book), 1)], 0.10)  # nlk_client 미전달
    assert lines[0].kdc == "" and lines[0].nlk_verified is None
