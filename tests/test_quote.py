"""견적 계산/생성 단위 테스트."""
import pandas as pd

from aladin_automation.matching import MatchResult, MatchStatus
from aladin_automation.quote import build_quote_lines, generate_quote_excel
from conftest import make_book


def _result(title, book, status=MatchStatus.CONFIRMED, conf=1.0):
    return MatchResult(query_title=title, query_author="", status=status, book=book, confidence=conf)


def test_supply_price_calculation():
    book = make_book("책", price_standard=15900)
    lines = build_quote_lines([(_result("책", book), 5)], discount_rate=0.10)
    ln = lines[0]
    assert ln.supply_unit_price == 14310  # round(15900*0.9)
    assert ln.supply_amount == 14310 * 5


def test_failed_line_has_zero_price():
    r = MatchResult(query_title="없음", query_author="", status=MatchStatus.FAILED,
                    book=None, confidence=0.0, reasons=["검색 결과 없음"])
    lines = build_quote_lines([(r, 3)], discount_rate=0.10)
    assert lines[0].supply_amount == 0
    assert lines[0].isbn13 == ""


def test_generate_excel_has_four_sheets(tmp_path):
    book = make_book("책", price_standard=10000)
    lines = build_quote_lines([(_result("책", book), 2)], discount_rate=0.10)
    out = generate_quote_excel(lines, discount_rate=0.10, client_name="테스트", output_dir=tmp_path)
    assert out.exists()
    sheets = pd.read_excel(out, sheet_name=None)
    assert set(sheets.keys()) == {"요약", "확정", "검토필요", "실패"}
    assert len(sheets["확정"]) == 1
