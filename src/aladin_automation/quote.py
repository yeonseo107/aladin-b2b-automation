"""견적서 생성.

매칭 결과 + 거래처 할인율로 공급단가/공급가를 계산하고,
'확정 / 검토필요 / 실패 / 요약' 시트로 구성된 견적서 엑셀을 만든다.

공급가 산식 (B2B 납품, 정가 기준 할인):
  공급단가 = round(정가 × (1 - 할인율))
  공급가   = 공급단가 × 수량
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from .config import PROJECT_ROOT
from .matching import MatchResult, MatchStatus

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "output"


@dataclass
class QuoteLine:
    """견적서 한 줄: 입력 + 매칭 + 계산 결과."""

    input_title: str
    input_author: str
    qty: int
    status: str
    matched_title: str
    isbn13: str
    publisher: str
    pub_date: str
    price_standard: int
    price_sales: int
    stock_status: str
    supply_unit_price: int   # 공급단가
    supply_amount: int       # 공급가 (= 공급단가 × 수량)
    confidence: float
    reasons: str


def _supply_price(price_standard: int, discount_rate: float) -> int:
    """정가 기준 할인 적용 공급단가 (원 단위 반올림)."""
    return int(round(price_standard * (1 - discount_rate)))


def build_quote_lines(
    results: list[tuple[MatchResult, int]],
    discount_rate: float,
) -> list[QuoteLine]:
    """(매칭결과, 수량) 목록 → 공급가 계산된 견적 라인 목록."""
    lines: list[QuoteLine] = []
    for result, qty in results:
        book = result.book
        if book is not None:
            unit = _supply_price(book.price_standard, discount_rate)
            lines.append(
                QuoteLine(
                    input_title=result.query_title,
                    input_author=result.query_author,
                    qty=qty,
                    status=result.status.value,
                    matched_title=book.title,
                    isbn13=book.isbn13,
                    publisher=book.publisher,
                    pub_date=book.pub_date,
                    price_standard=book.price_standard,
                    price_sales=book.price_sales,
                    stock_status=book.stock_status or "정상",
                    supply_unit_price=unit,
                    supply_amount=unit * qty,
                    confidence=result.confidence,
                    reasons="; ".join(result.reasons),
                )
            )
        else:  # 매칭 실패
            lines.append(
                QuoteLine(
                    input_title=result.query_title,
                    input_author=result.query_author,
                    qty=qty,
                    status=result.status.value,
                    matched_title="",
                    isbn13="",
                    publisher="",
                    pub_date="",
                    price_standard=0,
                    price_sales=0,
                    stock_status="",
                    supply_unit_price=0,
                    supply_amount=0,
                    confidence=result.confidence,
                    reasons="; ".join(result.reasons),
                )
            )
    return lines


# 시트별 컬럼 구성
_QUOTE_COLS = [
    ("input_title", "입력도서명"),
    ("input_author", "입력저자"),
    ("matched_title", "매칭도서명"),
    ("isbn13", "ISBN13"),
    ("publisher", "출판사"),
    ("pub_date", "출간일"),
    ("qty", "수량"),
    ("price_standard", "정가"),
    ("supply_unit_price", "공급단가"),
    ("supply_amount", "공급가"),
    ("stock_status", "재고상태"),
    ("confidence", "신뢰도"),
    ("reasons", "비고"),
]
_FAIL_COLS = [
    ("input_title", "입력도서명"),
    ("input_author", "입력저자"),
    ("qty", "수량"),
    ("reasons", "사유"),
]


def _to_df(lines: list[QuoteLine], cols: list[tuple[str, str]]) -> pd.DataFrame:
    rows = [{label: getattr(ln, attr) for attr, label in cols} for ln in lines]
    return pd.DataFrame(rows, columns=[label for _, label in cols])


def generate_quote_excel(
    lines: list[QuoteLine],
    *,
    discount_rate: float,
    client_name: str = "거래처",
    supplier_name: str = "책나래 도서유통",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    now: Optional[datetime] = None,
) -> Path:
    """견적 라인 목록 → 견적서 엑셀 파일 생성. 생성된 파일 경로 반환."""
    now = now or datetime.now()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"견적서_{client_name}_{now:%Y%m%d_%H%M%S}.xlsx"

    confirmed = [ln for ln in lines if ln.status == MatchStatus.CONFIRMED.value]
    review = [ln for ln in lines if ln.status == MatchStatus.REVIEW.value]
    failed = [ln for ln in lines if ln.status == MatchStatus.FAILED.value]

    sum_confirmed = sum(ln.supply_amount for ln in confirmed)
    sum_with_review = sum_confirmed + sum(ln.supply_amount for ln in review)

    summary = pd.DataFrame(
        [
            ("공급처", supplier_name),
            ("거래처", client_name),
            ("할인율", f"{discount_rate:.0%}"),
            ("생성일시", now.strftime("%Y-%m-%d %H:%M:%S")),
            ("총 요청 종수", len(lines)),
            ("자동 확정", len(confirmed)),
            ("검토 필요", len(review)),
            ("매칭 실패", len(failed)),
            ("확정 공급가 합계", sum_confirmed),
            ("확정+검토 공급가 합계", sum_with_review),
        ],
        columns=["항목", "값"],
    )

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="요약", index=False)
        _to_df(confirmed, _QUOTE_COLS).to_excel(writer, sheet_name="확정", index=False)
        _to_df(review, _QUOTE_COLS).to_excel(writer, sheet_name="검토필요", index=False)
        _to_df(failed, _FAIL_COLS).to_excel(writer, sheet_name="실패", index=False)
        _autofit_columns(writer)

    return out_path


def _autofit_columns(writer: "pd.ExcelWriter") -> None:
    """가독성을 위해 시트별 컬럼 너비를 내용 길이에 맞춰 조정."""
    for ws in writer.book.worksheets:
        for col_cells in ws.columns:
            length = max((len(str(c.value)) for c in col_cells if c.value is not None), default=8)
            # 한글 가중치 고려해 약간 넉넉히, 상한 60
            ws.column_dimensions[col_cells[0].column_letter].width = min(max(length + 2, 10), 60)
