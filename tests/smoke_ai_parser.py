"""AI 파서 실호출 스모크 테스트 (ANTHROPIC_API_KEY 필요).

실행: ./venv/bin/python tests/smoke_ai_parser.py
키가 없으면 건너뛴다.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()

from aladin_automation.ai_parser import parse_freeform_text

SAMPLE = """안녕하세요, 가상도서관 김사서입니다.
다음 도서들 납품 견적 부탁드립니다.
- 미움받을 용기 (기시미 이치로) 5권
- 아몬드 손원평 3부
- 달러구트 꿈 백화점 2권요
납기는 언제쯤 가능할까요? 감사합니다."""


def main() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 없음 → 스모크 건너뜀 (오프라인 테스트는 pytest로 검증)")
        return 0
    rows = parse_freeform_text(SAMPLE)
    print(f"추출된 도서 {len(rows)}건:")
    for r in rows:
        print(f"- {r.title} / {r.author or '-'} / {r.qty}권")
    assert rows, "도서를 추출하지 못함"
    print("스모크 테스트 통과 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
