"""입력 파서.

거래처가 보낸 도서 요청 목록(CSV/Excel)을 읽어 표준 형식으로 정규화한다.
거래처마다 컬럼명이 제각각이라 흔한 변형을 매핑한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class InputRow:
    title: str
    author: str = ""
    qty: int = 1
    isbn: str = ""


# 표준 필드 ← 허용하는 컬럼명 변형
_COLUMN_ALIASES = {
    "title": {"도서명", "제목", "책", "책이름", "도서", "title", "book", "name"},
    "author": {"저자", "지은이", "작가", "author"},
    "qty": {"수량", "권수", "부수", "qty", "quantity", "count"},
    "isbn": {"isbn", "isbn13", "희망isbn", "isbn번호"},
}


def _build_column_map(columns: list[str]) -> dict[str, str]:
    """실제 컬럼명 → 표준 필드명 매핑."""
    mapping: dict[str, str] = {}
    for col in columns:
        key = str(col).strip().lower().replace(" ", "")
        for std, aliases in _COLUMN_ALIASES.items():
            if key in {a.lower() for a in aliases}:
                mapping[col] = std
                break
    return mapping


def load_requests(path: str | Path) -> list[InputRow]:
    """CSV/Excel 입력 파일 → InputRow 목록."""
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path, dtype=str)
    elif path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str)
    else:
        raise ValueError(f"지원하지 않는 형식: {path.suffix} (.csv/.xlsx 만 지원)")

    colmap = _build_column_map(list(df.columns))
    if "title" not in colmap.values():
        raise ValueError(
            f"필수 컬럼 '도서명'을 찾지 못했습니다. 인식된 컬럼: {list(df.columns)}"
        )
    df = df.rename(columns=colmap)
    # 빈 셀이 NaN으로 읽히면 truthy로 오인되므로 빈 문자열로 정규화
    df = df.fillna("")

    rows: list[InputRow] = []
    for _, r in df.iterrows():
        title = str(r.get("title", "") or "").strip()
        if not title:
            continue  # 빈 행 skip
        rows.append(
            InputRow(
                title=title,
                author=str(r.get("author", "") or "").strip(),
                qty=_to_int(r.get("qty"), default=1),
                isbn=str(r.get("isbn", "") or "").strip(),
            )
        )
    return rows


def _to_int(value, default: int = 1) -> int:
    try:
        n = int(float(str(value).strip()))
        return n if n > 0 else default
    except (ValueError, TypeError):
        return default
