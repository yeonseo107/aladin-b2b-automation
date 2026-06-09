"""정산 분류 로직 단위 테스트 (오프라인)."""
from aladin_automation.settlement import (
    STATUS_NOTFOUND,
    STATUS_OK,
    STATUS_PRICE,
    STATUS_STOCK,
    classify,
)
from conftest import make_book


def test_correct_price_is_ok():
    book = make_book("책", price_standard=10000)  # 기대 9000
    c = classify(book, billed_unit=9000, discount_rate=0.10, tolerance=50)
    assert c["status"] == STATUS_OK
    assert c["expected_unit"] == 9000 and c["diff"] == 0


def test_price_mismatch_flagged():
    book = make_book("책", price_standard=10000)
    c = classify(book, billed_unit=9500, discount_rate=0.10, tolerance=50)
    assert c["status"] == STATUS_PRICE
    assert c["diff"] == 500


def test_within_tolerance_is_ok():
    book = make_book("책", price_standard=10000)
    c = classify(book, billed_unit=9030, discount_rate=0.10, tolerance=50)
    assert c["status"] == STATUS_OK


def test_not_found():
    c = classify(None, billed_unit=9000, discount_rate=0.10, tolerance=50)
    assert c["status"] == STATUS_NOTFOUND


def test_out_of_print_with_correct_price():
    book = make_book("책", price_standard=10000, stock_status="절판")
    c = classify(book, billed_unit=9000, discount_rate=0.10, tolerance=50)
    assert c["status"] == STATUS_STOCK
    assert "재발주" in c["note"]
