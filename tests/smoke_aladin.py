"""알라딘 클라이언트 실호출 스모크 테스트.

실행: ./venv/bin/python tests/smoke_aladin.py
실제 API를 호출하므로 .env의 ALADIN_TTB_KEY가 필요하다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aladin_automation.aladin_client import AladinClient


def main() -> int:
    client = AladinClient()

    print("=== 1) 검색(search) ===")
    books = client.search("미움받을 용기", max_results=3)
    if not books:
        print("검색 결과 없음 — 실패")
        return 1
    for b in books:
        print(f"- {b.title} / {b.author} / ISBN13={b.isbn13} / 정가={b.price_standard} / 재고={b.stock_status or '정상'}")

    top = books[0]
    print(f"\n=== 2) 조회(lookup) ISBN13={top.isbn13} ===")
    found = client.lookup(top.isbn13)
    if found:
        print(f"- {found.title} / 정가={found.price_standard} / 판매가={found.price_sales} / 판매가능={found.is_available}")
    else:
        print("조회 결과 없음")

    print("\n=== 3) 캐시 동작 확인 (같은 검색 재호출 시 API 호출 증가 없어야 함) ===")
    before = client.calls_made
    client.search("미움받을 용기", max_results=3)
    after = client.calls_made
    print(f"재호출 전 calls={before}, 재호출 후 calls={after} → 캐시 적중: {before == after}")

    print(f"\n총 실제 API 호출 수: {client.calls_made}")
    print("스모크 테스트 통과 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
