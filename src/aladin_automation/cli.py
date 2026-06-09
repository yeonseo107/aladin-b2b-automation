"""CLI: 입력 파일 하나를 받아 견적서 엑셀까지 한 번에 생성.

예) python run.py data/input/sample_request.csv --client 가상도서관 --discount 0.10
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .aladin_client import AladinClient
from .matching import MatchResult, MatchStatus, match
from .parser import InputRow, load_requests
from .quote import build_quote_lines, generate_quote_excel


def resolve_row(client: AladinClient, row: InputRow, max_results: int) -> MatchResult:
    """한 입력 행을 매칭 결과로. ISBN이 있으면 직접 조회(빠른 경로), 없으면 검색+매칭."""
    if row.isbn:
        book = client.lookup(row.isbn)
        if book is not None:
            return MatchResult(
                query_title=row.title,
                query_author=row.author,
                status=MatchStatus.CONFIRMED,
                book=book,
                confidence=1.0,
                reasons=["ISBN 직접 지정"],
            )
        # ISBN 조회 실패 시 제목 검색으로 폴백
    books = client.search(row.title, max_results=max_results)
    return match(row.title, row.author, books)


def run(args: argparse.Namespace) -> int:
    rows = load_requests(args.input)
    if not rows:
        print("입력에 처리할 도서가 없습니다.")
        return 1

    print(f"입력 {len(rows)}건 처리 시작 (거래처={args.client}, 할인율={args.discount:.0%})")
    client = AladinClient()
    results: list[tuple[MatchResult, int]] = []
    for i, row in enumerate(rows, 1):
        result = resolve_row(client, row, args.max_results)
        results.append((result, row.qty))
        print(f"  [{i}/{len(rows)}] {row.title} → {result.status.value} (신뢰도 {result.confidence})")

    lines = build_quote_lines(results, discount_rate=args.discount)
    out = generate_quote_excel(
        lines,
        discount_rate=args.discount,
        client_name=args.client,
        output_dir=Path(args.output_dir),
    )

    confirmed = sum(1 for ln in lines if ln.status == MatchStatus.CONFIRMED.value)
    review = sum(1 for ln in lines if ln.status == MatchStatus.REVIEW.value)
    failed = sum(1 for ln in lines if ln.status == MatchStatus.FAILED.value)
    total = sum(ln.supply_amount for ln in lines if ln.status == MatchStatus.CONFIRMED.value)

    print("\n=== 처리 요약 ===")
    print(f"  총 {len(rows)}종 | 확정 {confirmed} · 검토필요 {review} · 실패 {failed}")
    print(f"  확정 공급가 합계: {total:,}원")
    print(f"  실제 API 호출: {client.calls_made}회")
    print(f"  견적서: {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aladin-quote",
        description="거래처 도서 요청 목록(CSV/Excel) → 알라딘 매칭 → 견적서 엑셀 생성",
    )
    p.add_argument("input", help="입력 파일 경로 (.csv / .xlsx)")
    p.add_argument("--client", default="거래처", help="거래처명 (출력 파일명/요약에 사용)")
    p.add_argument("--discount", type=float, default=0.10, help="납품 할인율 (0~1, 기본 0.10)")
    p.add_argument("--max-results", type=int, default=5, help="검색 후보 수 (기본 5)")
    p.add_argument("--output-dir", default="data/output", help="견적서 출력 폴더")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 0 <= args.discount < 1:
        print("오류: --discount 는 0 이상 1 미만이어야 합니다.")
        return 2
    return run(args)
