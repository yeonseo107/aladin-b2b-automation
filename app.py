"""Streamlit 간단 UI — 사내 운영툴 프로토타입.

실행: ./venv/bin/streamlit run app.py
거래처 도서목록 업로드 → 견적서 생성 / 납품목록 업로드 → 정산 대조.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd
import streamlit as st

from aladin_automation.aladin_client import AladinClient
from aladin_automation.cli import resolve_row
from aladin_automation.matching import MatchStatus
from aladin_automation.parser import load_requests
from aladin_automation.quote import build_quote_lines, generate_quote_excel
from aladin_automation.settlement import generate_settlement_excel, reconcile

st.set_page_config(page_title="알라딘 B2B 자동화", page_icon="📚", layout="wide")
st.title("📚 알라딘 B2B 납품 자동화")
st.caption("거래처 도서목록 → 알라딘 매칭 → 견적서·정산 리포트 자동 생성 (프로토타입)")

OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "output"


@st.cache_resource
def get_client() -> AladinClient:
    return AladinClient()


def _save_upload(uploaded) -> Path:
    suffix = Path(uploaded.name).suffix
    tmp = Path(tempfile.mkstemp(suffix=suffix)[1])
    tmp.write_bytes(uploaded.getvalue())
    return tmp


tab_quote, tab_settle = st.tabs(["🧾 견적 생성", "🔍 정산 대조"])

# ---------- 견적 생성 ----------
with tab_quote:
    st.subheader("견적서 생성")
    st.write("도서명 목록(CSV/Excel)을 올리면 ISBN·정가·재고를 채우고 할인율을 적용한 견적서를 만듭니다.")
    c1, c2 = st.columns(2)
    client_name = c1.text_input("거래처명", value="가상도서관", key="q_client")
    discount = c2.slider("납품 할인율", 0.0, 0.5, 0.10, 0.01, key="q_disc")
    up = st.file_uploader("도서 요청 목록", type=["csv", "xlsx"], key="q_up")

    if up and st.button("견적 생성", type="primary", key="q_run"):
        rows = load_requests(_save_upload(up))
        client = get_client()
        results, prog = [], st.progress(0.0, text="매칭 중…")
        for i, row in enumerate(rows, 1):
            results.append((resolve_row(client, row, 5), row.qty))
            prog.progress(i / len(rows), text=f"매칭 중… {i}/{len(rows)}")
        prog.empty()

        lines = build_quote_lines(results, discount_rate=discount)
        conf = sum(1 for ln in lines if ln.status == MatchStatus.CONFIRMED.value)
        rev = sum(1 for ln in lines if ln.status == MatchStatus.REVIEW.value)
        fail = sum(1 for ln in lines if ln.status == MatchStatus.FAILED.value)
        total = sum(ln.supply_amount for ln in lines if ln.status == MatchStatus.CONFIRMED.value)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 종수", len(lines))
        m2.metric("자동 확정", conf)
        m3.metric("검토 필요", rev)
        m4.metric("확정 공급가", f"{total:,}원")

        df = pd.DataFrame([{
            "상태": ln.status, "입력도서명": ln.input_title, "매칭도서명": ln.matched_title,
            "ISBN13": ln.isbn13, "정가": ln.price_standard, "공급단가": ln.supply_unit_price,
            "수량": ln.qty, "공급가": ln.supply_amount, "신뢰도": ln.confidence, "비고": ln.reasons,
        } for ln in lines])
        st.dataframe(df, use_container_width=True, hide_index=True)

        out = generate_quote_excel(lines, discount_rate=discount, client_name=client_name, output_dir=OUTPUT_DIR)
        st.download_button("📥 견적서 엑셀 다운로드", out.read_bytes(), file_name=out.name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------- 정산 대조 ----------
with tab_settle:
    st.subheader("정산 대조")
    st.write("납품 완료 목록(ISBN·납품단가·수량)을 알라딘 정가/재고와 대조해 가격불일치·절판·조회실패를 찾습니다.")
    c1, c2 = st.columns(2)
    s_client = c1.text_input("거래처명", value="가상도서관", key="s_client")
    s_disc = c2.slider("계약 할인율", 0.0, 0.5, 0.10, 0.01, key="s_disc")
    s_up = st.file_uploader("납품 목록 (ISBN,도서명,납품단가,수량)", type=["csv", "xlsx"], key="s_up")

    if s_up and st.button("정산 대조 실행", type="primary", key="s_run"):
        path = _save_upload(s_up)
        raw = pd.read_csv(path, dtype=str).fillna("") if path.suffix == ".csv" else pd.read_excel(path, dtype=str).fillna("")
        rows = [{"isbn": r.get("ISBN", ""), "title": r.get("도서명", ""),
                 "billed_unit": int(r.get("납품단가") or 0), "qty": int(r.get("수량") or 1)}
                for _, r in raw.iterrows()]
        client = get_client()
        with st.spinner("대조 중…"):
            lines = reconcile(rows, client, discount_rate=s_disc)

        issues = [ln for ln in lines if ln.status != "정상"]
        m1, m2, m3 = st.columns(3)
        m1.metric("총 건수", len(lines))
        m2.metric("정상", len(lines) - len(issues))
        m3.metric("이상", len(issues))

        df = pd.DataFrame([{
            "판정": ln.status, "ISBN": ln.isbn, "도서명": ln.title, "납품단가": ln.billed_unit,
            "정가": ln.standard_price, "기대단가": ln.expected_unit, "차이": ln.diff,
            "재고상태": ln.stock_status, "비고": ln.note,
        } for ln in lines])
        st.dataframe(df, use_container_width=True, hide_index=True)

        out = generate_settlement_excel(lines, discount_rate=s_disc, client_name=s_client, output_dir=OUTPUT_DIR)
        st.download_button("📥 정산 리포트 다운로드", out.read_bytes(), file_name=out.name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
