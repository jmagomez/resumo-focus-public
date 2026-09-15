"""Testes de download: validação de conteúdo e recuo por feriado."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests

from focus.pdf import (
    TAMANHO_MINIMO_BYTES,
    FocusIndisponivelError,
    baixar,
    ultima_segunda,
)

PDF_VALIDO = b"%PDF-1.4" + b"x" * TAMANHO_MINIMO_BYTES
PDF_TRUNCADO = b"%PDF-1.4 curto demais"
HTML_DE_ERRO = b"<html><body>Servico indisponivel</body></html>" * 4000


def _resposta(status: int, conteudo: bytes = b"") -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.content = conteudo
    return m


def test_ultima_segunda():
    assert ultima_segunda(date(2026, 9, 11)) == date(2026, 9, 7)  # sexta → segunda
    assert ultima_segunda(date(2026, 9, 7)) == date(2026, 9, 7)  # segunda → ela mesma


def test_baixa_na_primeira_tentativa(tmp_path):
    with patch("focus.pdf.requests.get", return_value=_resposta(200, PDF_VALIDO)) as get:
        resultado = baixar(tmp_path, inicio=date(2026, 9, 7))
    assert resultado.caminho.name == "focus_2026-09-07.pdf"
    assert resultado.data_publicacao == date(2026, 9, 7)
    assert not resultado.ja_existia
    get.assert_called_once()


def test_recua_dia_a_dia_em_feriado(tmp_path):
    efeitos = [_resposta(404), _resposta(404), _resposta(200, PDF_VALIDO)]
    with patch("focus.pdf.requests.get", side_effect=efeitos):
        resultado = baixar(tmp_path, inicio=date(2026, 9, 7))
    assert resultado.caminho.name == "focus_2026-09-05.pdf"


def test_rejeita_resposta_200_que_nao_e_pdf(tmp_path):
    """O portal do BCB às vezes devolve página de erro com HTTP 200."""
    efeitos = [_resposta(200, HTML_DE_ERRO), _resposta(200, PDF_VALIDO)]
    with patch("focus.pdf.requests.get", side_effect=efeitos):
        resultado = baixar(tmp_path, inicio=date(2026, 9, 7))
    assert resultado.caminho.name == "focus_2026-09-06.pdf"
    assert resultado.caminho.read_bytes().startswith(b"%PDF")


def test_rejeita_pdf_truncado(tmp_path):
    """Defeito que a versão anterior deixava passar: bastava começar com %PDF."""
    efeitos = [_resposta(200, PDF_TRUNCADO), _resposta(200, PDF_VALIDO)]
    with patch("focus.pdf.requests.get", side_effect=efeitos):
        resultado = baixar(tmp_path, inicio=date(2026, 9, 7))
    assert len(resultado.caminho.read_bytes()) >= TAMANHO_MINIMO_BYTES


def test_erro_de_rede_segue_para_o_dia_anterior(tmp_path):
    efeitos = [requests.ConnectionError("timeout"), _resposta(200, PDF_VALIDO)]
    with patch("focus.pdf.requests.get", side_effect=efeitos):
        resultado = baixar(tmp_path, inicio=date(2026, 9, 7))
    assert resultado.caminho.name == "focus_2026-09-06.pdf"


def test_reaproveita_arquivo_em_disco(tmp_path):
    existente = tmp_path / "focus_2026-09-07.pdf"
    existente.write_bytes(PDF_VALIDO)
    with patch("focus.pdf.requests.get") as get:
        resultado = baixar(tmp_path, inicio=date(2026, 9, 7))
    get.assert_not_called()
    assert resultado.ja_existia


def test_arquivo_em_disco_truncado_e_rebaixado(tmp_path):
    (tmp_path / "focus_2026-09-07.pdf").write_bytes(PDF_TRUNCADO)
    with patch("focus.pdf.requests.get", return_value=_resposta(200, PDF_VALIDO)):
        resultado = baixar(tmp_path, inicio=date(2026, 9, 7))
    assert not resultado.ja_existia
    assert len(resultado.caminho.read_bytes()) >= TAMANHO_MINIMO_BYTES


def test_levanta_quando_nada_e_encontrado(tmp_path):
    with patch("focus.pdf.requests.get", return_value=_resposta(404)):
        with pytest.raises(FocusIndisponivelError, match="não encontrado"):
            baixar(tmp_path, inicio=date(2026, 9, 7))
