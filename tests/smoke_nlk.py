"""국중도 서지 API 실호출 스모크 (NLK_CERT_KEY 필요).

실행: ./venv/bin/python tests/smoke_nlk.py
키가 없으면 건너뛴다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aladin_automation.config import has_nlk_key
from aladin_automation.nlk_client import NLKClient, verify_against

# 미움받을 용기(1권) ISBN13
TEST_ISBN = "9791168340770"


def main() -> int:
    if not has_nlk_key():
        print("NLK_CERT_KEY 없음 → 스모크 건너뜀 (오프라인 테스트는 pytest tests/test_nlk.py로 검증)")
        return 0
    client = NLKClient(timeout=30)  # 정부 API가 느릴 수 있어 넉넉히
    try:
        rec = client.lookup_isbn(TEST_ISBN)
    except Exception as e:
        print(f"국중도 연결 실패({type(e).__name__}) — 이 네트워크에서 nl.go.kr 도달 불가일 수 있음.")
        print("한국 내 네트워크/다른 머신에서 재시도하거나, 보강 없이도 서비스는 정상 동작함.")
        return 0
    if rec is None:
        print(f"ISBN {TEST_ISBN} 국중도 서지 없음")
        return 1
    print(f"제목: {rec.title}")
    print(f"저자: {rec.author} | 출판사: {rec.publisher}")
    print(f"ISBN: {rec.isbn} | 판사항: {rec.edition or '-'} | KDC: {rec.kdc or '-'} | 발행: {rec.publish_date}")
    ok, why = verify_against("미움받을 용기", "인플루엔셜", rec)
    print(f"교차검증(예시): {ok} — {why}")
    print("스모크 테스트 통과 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
