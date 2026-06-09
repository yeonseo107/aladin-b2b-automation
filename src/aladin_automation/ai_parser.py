"""AI 비정형 입력 파싱.

거래처가 메일/메신저로 보낸 자유 형식 텍스트(인사말·요청이 뒤섞인)에서
도서 주문 목록(도서명·저자·수량)을 Claude로 구조화 추출한다.

단일 추출 작업이므로 Messages API 한 번 호출 + 구조화 출력(messages.parse)을 사용한다.
모델: claude-opus-4-8 (Anthropic 공식 SDK).
"""
from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel

from .parser import InputRow

MODEL = "claude-opus-4-8"

SYSTEM = (
    "너는 B2B 도서 납품업체의 주문 접수 보조다. "
    "거래처가 보낸 자유 형식 텍스트(메일/메신저)에서 '주문하려는 도서 목록'만 구조화해 추출한다.\n"
    "규칙:\n"
    "- 각 도서의 핵심 제목만 추출한다(괄호 부제·따옴표·'책', '도서' 같은 군더더기 제거).\n"
    "- 저자가 명시된 경우만 author에 넣고, 없으면 빈 문자열.\n"
    "- 수량이 명시되면 qty(양의 정수), 없으면 1.\n"
    "- 인사말·서명·납기 문의 등 도서가 아닌 내용은 무시한다.\n"
    "- 도서가 하나도 없으면 빈 목록을 반환한다."
)


class _BookRequest(BaseModel):
    title: str
    author: str = ""
    qty: int = 1


class _BookList(BaseModel):
    books: list[_BookRequest]


def _books_to_rows(books: list[_BookRequest]) -> list[InputRow]:
    """추출 결과 → InputRow 목록 (순수 변환, 네트워크 무관)."""
    rows: list[InputRow] = []
    for b in books:
        title = (b.title or "").strip()
        if not title:
            continue
        rows.append(InputRow(title=title, author=(b.author or "").strip(), qty=max(1, b.qty)))
    return rows


def _require_key() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY가 설정되지 않았습니다. "
            ".env에 발급받은 키를 넣어주세요. (https://console.anthropic.com)"
        )


def parse_freeform_text(text: str, *, model: str = MODEL, client=None) -> list[InputRow]:
    """자유 형식 텍스트에서 도서 주문 목록을 추출해 InputRow 목록으로 반환."""
    if not text or not text.strip():
        return []
    if client is None:
        _require_key()
        import anthropic

        client = anthropic.Anthropic()

    resp = client.messages.parse(
        model=model,
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": text}],
        output_format=_BookList,
    )
    parsed: Optional[_BookList] = resp.parsed_output
    return _books_to_rows(parsed.books) if parsed else []
