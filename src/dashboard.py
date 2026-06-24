"""Dashboard Streamlit para o Boletim Focus do Banco Central do Brasil."""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extractor import extract_text
from src.parser import parse_focus

_DATA_DIR = Path(__file__).parent.parent / "data"

_UNITS: dict[str, str] = {
    "IPCA":             "% a.a.",
    "PIB":              "% a.a.",
    "Câmbio":           "R$/US$",
    "Selic":            "% a.a.",
    "IGP-M":            "% a.a.",
    "IPCA Admin.":      "% a.a.",
    "Conta corrente":   "US$ bi",
    "Bal. comercial":   "US$ bi",
    "IDP":              "US$ bi",
    "DLSP":             "% PIB",
    "Result. primário": "% PIB",
    "Result. nominal":  "% PIB",
}

# (nome, unidade, delta_color)
# delta_color="inverse" → subida é vermelha (pior); "normal" → subida é verde (melhor)
_KEY_METRICS = [
    ("IPCA",   "% a.a.", "inverse"),
    ("Selic",  "% a.a.", "inverse"),
    ("Câmbio", "R$/US$", "inverse"),
    ("PIB",    "% a.a.", "normal"),
]

_MONTH_LABELS: dict[str, str] = {
    "jun/2026": "Jun/2026",
    "jul/2026": "Jul/2026",
    "ago/2026": "Ago/2026",
    "infl12m":  "Infl. 12m",
}


def _load() -> dict:
    pdfs = sorted(_DATA_DIR.glob("focus_*.pdf"), reverse=True)
    if not pdfs:
        st.error("Nenhum PDF em data/. Execute: python src/baixar_focus.py")
        st.stop()
    return parse_focus(extract_text(pdfs[0]))


def _delta(hoje: str, ha1sem: str) -> float | None:
    try:
        return round(
            float(hoje.replace(",", ".")) - float(ha1sem.replace(",", ".")), 2
        )
    except ValueError:
        return None


def _fmt_delta(d: float | None) -> str | None:
    if d is None:
        return None
    return f"{d:+.2f}".replace(".", ",")


def _cell(periods: dict, period: str) -> str:
    c = periods.get(period, {})
    hoje = c.get("hoje", "-")
    trend = c.get("trend", "")
    return f"{hoje} {trend}".strip() if hoje != "-" else "—"


def main() -> None:
    st.set_page_config(
        page_title="Boletim Focus — BCB",
        page_icon="📊",
        layout="wide",
    )

    with st.spinner("Carregando dados..."):
        data = _load()

    date_str = data["date"]
    if date_str:
        y, m, d = date_str.split("-")
        date_fmt = f"{d}/{m}/{y}"
    else:
        date_fmt = "—"

    # ── Cabeçalho ───────────────────────────────────────────────────────────
    col_title, col_date = st.columns([5, 1])
    with col_title:
        st.title("📊 Boletim Focus")
        st.caption("Banco Central do Brasil · Relatório de Mercado · Expectativas de Mercado")
    with col_date:
        st.metric("Publicação", date_fmt)

    st.divider()

    # ── Destaques 2026 ────────────────────────────────────────────────────
    st.subheader("Destaques — Expectativas para 2026")
    cols = st.columns(4)
    for col, (name, unit, delta_color) in zip(cols, _KEY_METRICS):
        entry = data["annual"].get(name, {}).get("2026", {})
        hoje  = entry.get("hoje", "-")
        ha1sem = entry.get("ha1sem", "-")
        with col:
            st.metric(
                label=f"{name} ({unit})",
                value=hoje if hoje != "-" else "—",
                delta=_fmt_delta(_delta(hoje, ha1sem)),
                delta_color=delta_color,
                help=f"Semana anterior: {ha1sem}" if ha1sem != "-" else None,
            )

    st.divider()

    # ── Tabelas ───────────────────────────────────────────────────────────
    tab_anual, tab_mensal = st.tabs(
        ["📅 Expectativas Anuais", "🗓 Expectativas Mensais"]
    )

    with tab_anual:
        years = ["2026", "2027", "2028", "2029"]
        rows = []
        for name, periods in data["annual"].items():
            row: dict = {"Indicador": name, "Unidade": _UNITS.get(name, "")}
            for yr in years:
                row[yr] = _cell(periods, yr)
            rows.append(row)

        df = pd.DataFrame(rows).set_index("Indicador")
        st.dataframe(df, use_container_width=True, height=460)
        st.caption(
            "Mediana de hoje · ▲ subiu · ▼ caiu · → estável em relação à semana anterior"
        )

    with tab_mensal:
        rows = []
        for name, periods in data["monthly"].items():
            row = {"Indicador": name}
            for key, label in _MONTH_LABELS.items():
                row[label] = _cell(periods, key)
            rows.append(row)

        df = pd.DataFrame(rows).set_index("Indicador")
        st.dataframe(df, use_container_width=True)
        st.caption(
            "Mediana de hoje · ▲ subiu · ▼ caiu · → estável em relação à semana anterior"
        )


if __name__ == "__main__":
    main()
