"""정산 매칭 리포트.

납품 완료 목록(ISBN/도서명 + 납품단가 + 수량)을 알라딘 현재 정가/재고와 대조해
가격 불일치·절판·조회실패를 탐지하고 정산 리포트 엑셀을 만든다.

기대 공급단가 = round(정가 × (1 - 할인율)). 납품단가가 이와 다르면 '가격불일치'.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from .aladin_client import AladinClient, Book
from .config import PROJECT_ROOT
from .matching import match

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "output"

STATUS_OK = "정상"
STATUS_PRICE = "가격불일치"
STATUS_STOCK = "절판주의"
STATUS_NOTFOUND = "조회실패"


@dataclass
class SettlementLine:
    isbn: str
    title: str
    qty: int
    billed_unit: int       # 납품단가(청구)
    standard_price: int    # 알라딘 정가
    expected_unit: int     # 기대 공급단가
    diff: int              # 납품단가 - 기대단가
    stock_status: str
    status: str
    note: str


def classify(book: Optional[Book], billed_unit: int, discount_rate: float, tolerance: int) -> dict:
    """대조 결과 분류 (순수 함수 — 네트워크 무관, 테스트 용이)."""
    if book is None:
        return {"status": STATUS_NOTFOUND, "expected_unit": 0, "diff": 0,
                "standard_price": 0, "stock_status": "", "note": "ISBN/제목 매칭 실패"}

    expected = int(round(book.price_standard * (1 - discount_rate)))
    diff = billed_unit - expected
    notes = []
    status = STATUS_OK
    if abs(diff) > tolerance:
        status = STATUS_PRICE
        notes.append(f"기대 {expected:,}원과 {diff:+,}원 차이")
    if not book.is_available:
        # 가격 문제와 별개로 재고 위험도 표시 (가격불일치가 우선순위)
        notes.append(f"현재 재고상태 '{book.stock_status}' — 재발주 주의")
        if status == STATUS_OK:
            status = STATUS_STOCK
    return {"status": status, "expected_unit": expected, "diff": diff,
            "standard_price": book.price_standard, "stock_status": book.stock_status or "정상",
            "note": "; ".join(notes)}


def reconcile(
    rows: list[dict],
    client: AladinClient,
    *,
    discount_rate: float,
    tolerance: int = 50,
    max_results: int = 5,
) -> list[SettlementLine]:
    """납품 행 목록을 알라딘과 대조. 행: {isbn?, title?, billed_unit, qty}."""
    lines: list[SettlementLine] = []
    for r in rows:
        isbn = str(r.get("isbn", "") or "").strip()
        title = str(r.get("title", "") or "").strip()
        billed = int(r.get("billed_unit") or 0)
        qty = int(r.get("qty") or 1)

        book: Optional[Book] = None
        if isbn:
            book = client.lookup(isbn)
        if book is None and title:
            res = match(title, "", client.search(title, max_results=max_results))
            book = res.book

        c = classify(book, billed, discount_rate, tolerance)
        lines.append(SettlementLine(
            isbn=isbn or (book.isbn13 if book else ""),
            title=title or (book.title if book else ""),
            qty=qty, billed_unit=billed,
            standard_price=c["standard_price"], expected_unit=c["expected_unit"],
            diff=c["diff"], stock_status=c["stock_status"], status=c["status"], note=c["note"],
        ))
    return lines


_COLS = [
    ("isbn", "ISBN"), ("title", "도서명"), ("qty", "수량"),
    ("billed_unit", "납품단가"), ("standard_price", "정가"),
    ("expected_unit", "기대단가"), ("diff", "차이"),
    ("stock_status", "재고상태"), ("status", "판정"), ("note", "비고"),
]


def generate_settlement_excel(
    lines: list[SettlementLine],
    *,
    discount_rate: float,
    client_name: str = "거래처",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    now: Optional[datetime] = None,
) -> Path:
    now = now or datetime.now()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"정산리포트_{client_name}_{now:%Y%m%d_%H%M%S}.xlsx"

    def to_df(items):
        return pd.DataFrame(
            [{label: getattr(ln, attr) for attr, label in _COLS} for ln in items],
            columns=[label for _, label in _COLS],
        )

    issues = [ln for ln in lines if ln.status != STATUS_OK]
    normal = [ln for ln in lines if ln.status == STATUS_OK]

    summary = pd.DataFrame([
        ("거래처", client_name),
        ("할인율", f"{discount_rate:.0%}"),
        ("생성일시", now.strftime("%Y-%m-%d %H:%M:%S")),
        ("총 건수", len(lines)),
        ("정상", len(normal)),
        ("이상(가격/절판/조회)", len(issues)),
        ("가격불일치", sum(1 for ln in lines if ln.status == STATUS_PRICE)),
        ("절판주의", sum(1 for ln in lines if ln.status == STATUS_STOCK)),
        ("조회실패", sum(1 for ln in lines if ln.status == STATUS_NOTFOUND)),
        ("총 청구액", sum(ln.billed_unit * ln.qty for ln in lines)),
    ], columns=["항목", "값"])

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="요약", index=False)
        to_df(issues).to_excel(writer, sheet_name="이상", index=False)
        to_df(normal).to_excel(writer, sheet_name="정상", index=False)
        for ws in writer.book.worksheets:
            for col in ws.columns:
                length = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                ws.column_dimensions[col[0].column_letter].width = min(max(length + 2, 10), 50)

    return out_path
