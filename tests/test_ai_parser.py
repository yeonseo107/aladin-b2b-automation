"""AI 파서 오프라인 단위 테스트 (네트워크/키 불필요).

실제 Claude 호출은 tests/smoke_ai_parser.py에서 키가 있을 때만 수행.
여기서는 추출 결과 → InputRow 변환 로직만 검증한다.
"""
import pytest

from aladin_automation.ai_parser import _books_to_rows, _BookRequest, parse_freeform_text


def test_books_to_rows_normalizes():
    books = [
        _BookRequest(title="  아몬드 ", author="손원평", qty=3),
        _BookRequest(title="데미안", author="", qty=0),  # qty<1 → 1
        _BookRequest(title="   ", author="x", qty=1),     # 빈 제목 → skip
    ]
    rows = _books_to_rows(books)
    assert len(rows) == 2
    assert rows[0].title == "아몬드" and rows[0].qty == 3
    assert rows[1].title == "데미안" and rows[1].qty == 1


def test_empty_text_returns_empty_without_api_call():
    # 빈 텍스트는 API를 부르지 않고 즉시 빈 목록
    assert parse_freeform_text("") == []
    assert parse_freeform_text("   \n ") == []
