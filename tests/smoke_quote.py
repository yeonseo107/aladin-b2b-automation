"""견적서 생성 실호출 스모크 테스트.

실행: ./venv/bin/python tests/smoke_quote.py
검색→매칭→가격계산→엑셀 생성까지 엔드투엔드로 확인한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from aladin_automation.aladin_client import AladinClient
from aladin_automation.matching import match
from aladin_automation.quote import build_quote_lines, generate_quote_excel

DISCOUNT = 0.10  # 거래처 납품 할인율 10%

# (도서명, 저자, 수량)
REQUEST = [
    ("미움받을 용기", "기시미 이치로", 5),
    ("죽음의 수용소에서", "빅터 프랭클", 3),
    ("데미안", "헤르만 헤세", 2),
    ("존재하지않는책zzxq판타지12345", "", 1),
]


def main() -> int:
    client = AladinClient()
    results = []
    for title, author, qty in REQUEST:
        books = client.search(title, max_results=5)
        results.append((match(title, author, books), qty))

    lines = build_quote_lines(results, discount_rate=DISCOUNT)
    print("=== 견적 라인 ===")
    for ln in lines:
        print(f"- [{ln.status}] {ln.input_title} x{ln.qty} | 정가 {ln.price_standard} → 공급단가 {ln.supply_unit_price} | 공급가 {ln.supply_amount}")

    out = generate_quote_excel(lines, discount_rate=DISCOUNT, client_name="가상도서관")
    print(f"\n견적서 생성: {out}")
    assert out.exists(), "엑셀 파일이 생성되지 않음"

    # 읽어서 시트/요약 검증
    sheets = pd.read_excel(out, sheet_name=None)
    print(f"시트: {list(sheets.keys())}")
    summary = dict(zip(sheets["요약"]["항목"], sheets["요약"]["값"]))
    print(f"요약: 종수={summary['총 요청 종수']}, 확정={summary['자동 확정']}, "
          f"검토={summary['검토 필요']}, 실패={summary['매칭 실패']}, "
          f"확정합계={summary['확정 공급가 합계']}")

    # 가격 계산 수동 검증 (확정 라인 중 미움받을 용기: 정가 15900, 10% 할인 → 14310, x5)
    expected_unit = round(15900 * 0.9)
    miube = next(ln for ln in lines if ln.input_title == "미움받을 용기")
    assert miube.supply_unit_price == expected_unit, (miube.supply_unit_price, expected_unit)
    assert miube.supply_amount == expected_unit * 5
    print(f"가격 계산 검증 OK: 미움받을 용기 공급단가 {miube.supply_unit_price} x5 = {miube.supply_amount}")
    print("스모크 테스트 통과 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
