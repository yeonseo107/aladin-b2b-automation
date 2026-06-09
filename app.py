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

from aladin_automation.ai_parser import parse_freeform_text
from aladin_automation.aladin_client import AladinClient
from aladin_automation.cli import resolve_row
from aladin_automation.config import has_nlk_key
from aladin_automation.matching import MatchStatus
from aladin_automation.nlk_client import NLKClient
from aladin_automation.parser import InputRow, load_requests
from aladin_automation.quote import build_quote_lines, generate_quote_excel
from aladin_automation.settlement import generate_settlement_excel, reconcile

st.set_page_config(page_title="알라딘 B2B 자동화", page_icon="📚", layout="wide")
st.title("📚 알라딘 B2B 납품 자동화")
st.caption("거래처 도서목록 → 알라딘 매칭 → 견적서·정산 리포트 자동 생성 (프로토타입)")

OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "output"


@st.cache_resource
def get_client() -> AladinClient:
    return AladinClient()


@st.cache_resource
def get_nlk():
    """국중도 보강 클라이언트 (키 있을 때만). 없으면 None."""
    return NLKClient() if has_nlk_key() else None


def _save_upload(uploaded) -> Path:
    suffix = Path(uploaded.name).suffix
    tmp = Path(tempfile.mkstemp(suffix=suffix)[1])
    tmp.write_bytes(uploaded.getvalue())
    return tmp


def _render_quote(rows: list[InputRow], client_name: str, discount: float) -> None:
    """InputRow 목록 → 매칭·견적 실행 후 결과 표/지표/다운로드 렌더."""
    if not rows:
        st.warning("처리할 도서가 없습니다.")
        return
    client = get_client()
    results, prog = [], st.progress(0.0, text="매칭 중…")
    for i, row in enumerate(rows, 1):
        results.append((resolve_row(client, row, 5), row.qty))
        prog.progress(i / len(rows), text=f"매칭 중… {i}/{len(rows)}")
    prog.empty()

    nlk = get_nlk()
    if nlk:
        st.caption("📚 국립중앙도서관 서지 보강·교차검증 켜짐 (KDC·판사항·검증)")
    lines = build_quote_lines(results, discount_rate=discount, nlk_client=nlk)
    conf = sum(1 for ln in lines if ln.status == MatchStatus.CONFIRMED.value)
    rev = sum(1 for ln in lines if ln.status == MatchStatus.REVIEW.value)
    total = sum(ln.supply_amount for ln in lines if ln.status == MatchStatus.CONFIRMED.value)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 종수", len(lines))
    m2.metric("자동 확정", conf)
    m3.metric("검토 필요", rev)
    m4.metric("확정 공급가", f"{total:,}원")

    df = pd.DataFrame([{
        "상태": ln.status, "입력도서명": ln.input_title, "매칭도서명": ln.matched_title,
        "ISBN13": ln.isbn13, "정가": ln.price_standard, "공급단가": ln.supply_unit_price,
        "수량": ln.qty, "공급가": ln.supply_amount,
        "KDC": ln.kdc, "판사항": ln.edition, "국중도": ln.nlk_verified_label,
        "신뢰도": ln.confidence, "비고": ln.reasons,
    } for ln in lines])
    st.dataframe(df, use_container_width=True, hide_index=True)

    out = generate_quote_excel(lines, discount_rate=discount, client_name=client_name, output_dir=OUTPUT_DIR)
    st.download_button("📥 견적서 엑셀 다운로드", out.read_bytes(), file_name=out.name,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


tab_quote, tab_settle, tab_ai = st.tabs(["🧾 견적 생성", "🔍 정산 대조", "✉️ 메일/텍스트 파싱"])

# ---------- 견적 생성 ----------
with tab_quote:
    st.subheader("견적서 생성")
    st.write("도서명 목록(CSV/Excel)을 올리면 ISBN·정가·재고를 채우고 할인율을 적용한 견적서를 만듭니다.")
    c1, c2 = st.columns(2)
    client_name = c1.text_input("거래처명", value="가상도서관", key="q_client")
    discount = c2.slider("납품 할인율", 0.0, 0.5, 0.10, 0.01, key="q_disc")
    up = st.file_uploader("도서 요청 목록", type=["csv", "xlsx"], key="q_up")

    if up and st.button("견적 생성", type="primary", key="q_run"):
        _render_quote(load_requests(_save_upload(up)), client_name, discount)

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

# ---------- 메일/텍스트 파싱 (AI) ----------
with tab_ai:
    st.subheader("메일/자유 텍스트 → 견적")
    st.write("거래처가 보낸 자유 형식 메일을 붙여넣으면 Claude가 도서 목록을 추출하고, 바로 견적서를 만듭니다.")
    c1, c2 = st.columns(2)
    a_client = c1.text_input("거래처명", value="가상도서관", key="a_client")
    a_disc = c2.slider("납품 할인율", 0.0, 0.5, 0.10, 0.01, key="a_disc")
    text = st.text_area(
        "메일/요청 텍스트",
        height=200,
        placeholder="안녕하세요. 아래 도서 견적 부탁드립니다.\n- 미움받을 용기 5권\n- 아몬드 손원평 3부 ...",
        key="a_text",
    )

    if st.button("도서 추출 → 견적 생성", type="primary", key="a_run"):
        try:
            with st.spinner("Claude가 도서 목록을 추출 중…"):
                rows = parse_freeform_text(text)
        except RuntimeError as e:
            st.error(str(e))
            rows = []
        if rows:
            st.success(f"{len(rows)}건 추출됨")
            st.dataframe(
                pd.DataFrame([{"도서명": r.title, "저자": r.author, "수량": r.qty} for r in rows]),
                use_container_width=True, hide_index=True,
            )
            _render_quote(rows, a_client, a_disc)
        elif text.strip():
            st.warning("도서를 추출하지 못했습니다.")
