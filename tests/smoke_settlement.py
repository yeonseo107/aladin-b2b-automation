"""정산 리포트 실호출 스모크 테스트.

실행: ./venv/bin/python tests/smoke_settlement.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from aladin_automation.aladin_client import AladinClient
from aladin_automation.settlement import generate_settlement_excel, reconcile

DISCOUNT = 0.10
SRC = Path(__file__).resolve().parents[1] / "data" / "input" / "sample_settlement.csv"


def main() -> int:
    df = pd.read_csv(SRC, dtype=str).fillna("")
    rows = [{"isbn": r["ISBN"], "title": r["도서명"], "billed_unit": int(r["납품단가"]), "qty": int(r["수량"])}
            for _, r in df.iterrows()]

    client = AladinClient()
    lines = reconcile(rows, client, discount_rate=DISCOUNT)
    print("=== 정산 대조 ===")
    for ln in lines:
        print(f"- [{ln.status}] {ln.title} | 납품 {ln.billed_unit:,} vs 기대 {ln.expected_unit:,} (차이 {ln.diff:+,}) {ln.note}")

    out = generate_settlement_excel(lines, discount_rate=DISCOUNT, client_name="가상도서관")
    print(f"\n정산리포트: {out}")
    assert out.exists()
    sheets = pd.read_excel(out, sheet_name=None)
    print(f"시트: {list(sheets.keys())} | 이상 {len(sheets['이상'])}건 / 정상 {len(sheets['정상'])}건")
    print("스모크 테스트 통과 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
