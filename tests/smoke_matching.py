"""매칭 엔진 실호출 스모크 테스트.

실행: ./venv/bin/python tests/smoke_matching.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aladin_automation.aladin_client import AladinClient
from aladin_automation.matching import match

# (입력 도서명, 입력 저자, 기대 상태 메모)
CASES = [
    ("미움받을 용기", "기시미 이치로", "명확 → 확정 기대"),
    ("데미안", "헤르만 헤세", "개정판 다수 → 검토 가능"),
    ("어린 왕자", "", "판본 다수 → 검토 가능"),
    ("죽음의 수용소에서", "빅터 프랭클", "명확 → 확정 기대"),
    ("존재하지않는책zzxq판타지12345", "", "결과 없음 → 실패 기대"),
]


def main() -> int:
    client = AladinClient()
    for title, author, memo in CASES:
        books = client.search(title, max_results=5)
        result = match(title, author, books)
        print(f"\n[입력] {title} / {author or '-'}  ({memo})")
        print(f"  상태: {result.status.value} | 신뢰도: {result.confidence}")
        if result.book:
            print(f"  매칭: {result.book.title} / ISBN13={result.book.isbn13} / 정가={result.book.price_standard}")
        print(f"  사유: {'; '.join(result.reasons)}")
        if result.status.value == "검토필요":
            for c in result.candidates:
                print(f"    - 후보 {c.score}: {c.book.title[:40]} (제목유사 {c.title_sim}, 저자일치 {c.author_match})")
    print(f"\n총 실제 API 호출 수: {client.calls_made}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
