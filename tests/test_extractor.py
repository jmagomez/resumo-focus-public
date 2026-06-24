import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.extractor import extract_text


def _mock_pdf(pages_text: list[str | None]):
    def _page(text):
        m = MagicMock()
        m.extract_text.return_value = text
        return m

    pdf = MagicMock()
    pdf.pages = [_page(t) for t in pages_text]
    pdf.__enter__ = MagicMock(return_value=pdf)
    pdf.__exit__ = MagicMock(return_value=False)
    return pdf


# ── helpers ──────────────────────────────────────────────────────────────────

SAMPLE = "IPCA  4,0\nSelic 13,75"


def _make_pdf(tmp_path: Path, name: str = "focus_2026-06-22.pdf") -> Path:
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4 fake")
    return p


# ── testes ───────────────────────────────────────────────────────────────────

def test_saves_txt_beside_pdf(tmp_path):
    pdf = _make_pdf(tmp_path)
    with patch("src.extractor.pdfplumber.open", return_value=_mock_pdf([SAMPLE, "Fim"])):
        result = extract_text(pdf)

    assert result == tmp_path / "focus_2026-06-22.txt"
    content = result.read_text(encoding="utf-8")
    assert SAMPLE in content
    assert "Fim" in content


def test_pages_joined_by_double_newline(tmp_path):
    pdf = _make_pdf(tmp_path)
    with patch("src.extractor.pdfplumber.open", return_value=_mock_pdf(["Pág1", "Pág2"])):
        result = extract_text(pdf)

    assert result.read_text(encoding="utf-8") == "Pág1\n\nPág2"


def test_skips_empty_and_none_pages(tmp_path):
    pdf = _make_pdf(tmp_path)
    with patch("src.extractor.pdfplumber.open", return_value=_mock_pdf(["Conteúdo", None, "   ", "Fim"])):
        result = extract_text(pdf)

    content = result.read_text(encoding="utf-8")
    assert content == "Conteúdo\n\nFim"


def test_returns_existing_txt_without_reopening_pdf(tmp_path):
    pdf = _make_pdf(tmp_path)
    txt = tmp_path / "focus_2026-06-22.txt"
    txt.write_text("já extraído", encoding="utf-8")

    with patch("src.extractor.pdfplumber.open") as mock_open:
        result = extract_text(pdf)

    mock_open.assert_not_called()
    assert result == txt


def test_raises_when_all_pages_empty(tmp_path):
    pdf = _make_pdf(tmp_path)
    with patch("src.extractor.pdfplumber.open", return_value=_mock_pdf([None, "   "])):
        with pytest.raises(ValueError, match="Nenhum texto extraído"):
            extract_text(pdf)


def test_txt_is_utf8(tmp_path):
    pdf = _make_pdf(tmp_path)
    texto = "Mediana: 4,50% — projeção: R$ 5,30 / US$"
    with patch("src.extractor.pdfplumber.open", return_value=_mock_pdf([texto])):
        result = extract_text(pdf)

    assert result.read_text(encoding="utf-8") == texto
