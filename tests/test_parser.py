"""입력 파서 단위 테스트."""
import pandas as pd
import pytest

from aladin_automation.parser import load_requests


def test_column_aliases_and_defaults(tmp_path):
    # 별칭 컬럼(제목/지은이/권수) 인식 + 빈 셀/수량 기본값 처리
    csv = tmp_path / "req.csv"
    pd.DataFrame({
        "제목": ["아몬드", "데미안"],
        "지은이": ["손원평", ""],
        "권수": ["3", ""],
    }).to_csv(csv, index=False)

    rows = load_requests(csv)
    assert len(rows) == 2
    assert rows[0].title == "아몬드" and rows[0].author == "손원평" and rows[0].qty == 3
    # 빈 수량 → 기본 1, 빈 저자 → "" (NaN이 "nan"으로 새지 않아야 함)
    assert rows[1].qty == 1
    assert rows[1].author == ""
    assert rows[1].isbn == ""


def test_missing_title_column_raises(tmp_path):
    csv = tmp_path / "bad.csv"
    pd.DataFrame({"엉뚱": ["x"]}).to_csv(csv, index=False)
    with pytest.raises(ValueError):
        load_requests(csv)


def test_blank_title_rows_skipped(tmp_path):
    csv = tmp_path / "req.csv"
    pd.DataFrame({"도서명": ["책1", "", "책2"]}).to_csv(csv, index=False)
    rows = load_requests(csv)
    assert [r.title for r in rows] == ["책1", "책2"]


def test_unsupported_extension_raises(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("도서명\n책")
    with pytest.raises(ValueError):
        load_requests(f)
