"""Testes do cliente da API Olinda de Expectativas.

Os testes offline cobrem normalização de campos e paginação com respostas
simuladas. O teste marcado ``network`` é um **teste de contrato**: roda contra
o serviço real no CI e falha assim que o BCB renomear um campo ou mudar o
formato de ``DataReferencia`` — antes que isso chegue ao boletim de segunda.
"""

from unittest.mock import MagicMock, patch

import pytest

from focus.api import (
    BASE_5_DIAS_UTEIS,
    BASE_30_DIAS,
    CAMPOS_OBRIGATORIOS,
    ApiExpectativasError,
    expectativas_anuais,
    expectativas_mensais,
    montar_url,
)

REGISTRO_ANUAL = {
    "Indicador": "IPCA",
    "IndicadorDetalhe": "",
    "Data": "2026-09-11",
    "DataReferencia": "2026",
    "Media": 4.91,
    "Mediana": 4.90,
    "DesvioPadrao": 0.25,
    "Minimo": 4.20,
    "Maximo": 5.60,
    "numeroRespondentes": 147,
    "baseCalculo": 0,
}

REGISTRO_MENSAL = {
    **REGISTRO_ANUAL,
    "DataReferencia": "09/2026",
    "baseCalculo": 1,
    "Mediana": 0.50,
}


def _resposta(valores, status=200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = {"value": valores}
    m.text = "{}"
    return m


def test_normaliza_campos_anuais():
    with patch("focus.api.requests.get", return_value=_resposta([REGISTRO_ANUAL])):
        (registro,) = expectativas_anuais(indicadores=["IPCA"])

    assert registro.indicador == "IPCA"
    assert registro.referencia == "2026"
    assert registro.mediana == pytest.approx(4.90)
    assert registro.desvio_padrao == pytest.approx(0.25)
    assert registro.n_respondentes == 147
    assert registro.base_calculo == BASE_30_DIAS
    assert registro.horizonte == "anual"


def test_referencia_mensal_vira_iso():
    """``09/2026`` da API vira ``2026-09`` — a mesma chave que o parser usa."""
    with patch("focus.api.requests.get", return_value=_resposta([REGISTRO_MENSAL])):
        (registro,) = expectativas_mensais(indicadores=["IPCA"])
    assert registro.referencia == "2026-09"
    assert registro.base_calculo == BASE_5_DIAS_UTEIS


def test_nome_curto_do_indicador():
    registro_pib = {**REGISTRO_ANUAL, "Indicador": "PIB Total"}
    with patch("focus.api.requests.get", return_value=_resposta([registro_pib])):
        (registro,) = expectativas_anuais(indicadores=["PIB Total"])
    assert registro.indicador == "PIB"


def test_coeficiente_de_variacao():
    with patch("focus.api.requests.get", return_value=_resposta([REGISTRO_ANUAL])):
        (registro,) = expectativas_anuais(indicadores=["IPCA"])
    assert registro.coeficiente_variacao == pytest.approx(0.25 / 4.91, rel=1e-3)


@pytest.mark.parametrize("campo", ["Mediana", "Data", "DataReferencia", "Indicador"])
def test_campo_obrigatorio_ausente_levanta(campo):
    """Mudança de contrato falha alto, com o nome do campo na mensagem."""
    registro = {k: v for k, v in REGISTRO_ANUAL.items() if k != campo}
    with patch("focus.api.requests.get", return_value=_resposta([registro])):
        with pytest.raises(ApiExpectativasError, match="obrigatório"):
            expectativas_anuais(indicadores=["IPCA"])


def test_http_diferente_de_200_levanta():
    resposta = MagicMock()
    resposta.status_code = 503
    resposta.text = "Service Unavailable"
    with patch("focus.api.requests.get", return_value=resposta):
        with pytest.raises(ApiExpectativasError, match="503"):
            expectativas_anuais(indicadores=["IPCA"])


def test_resposta_sem_chave_value_levanta():
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"erro": "nada aqui"}
    with patch("focus.api.requests.get", return_value=m):
        with pytest.raises(ApiExpectativasError, match="'value'"):
            expectativas_anuais(indicadores=["IPCA"])


def test_json_invalido_levanta():
    m = MagicMock()
    m.status_code = 200
    m.json.side_effect = ValueError("nao e json")
    m.text = "<html>erro</html>"
    with patch("focus.api.requests.get", return_value=m):
        with pytest.raises(ApiExpectativasError, match="JSON"):
            expectativas_anuais(indicadores=["IPCA"])


# ── Codificação da query string ───────────────────────────────────────────
#
# Defeito real, corrigido em 15/09/2026: a URL era delegada ao `params=` do
# requests, que codifica espaço como `+`. O OData do Olinda lê o `+` como
# caractere literal e devolve HTTP 400. Efeito observado em produção (run #2 do
# workflow "Coleta semanal do Focus"): toda consulta falhava, o pipeline caía na
# reserva do PDF e publicava histórico sem dispersão — reportando sucesso.


def test_url_codifica_espaco_como_pct20_e_nunca_como_mais():
    url = montar_url(
        "ExpectativasMercadoAnuais",
        {"$orderby": "Data asc", "$filter": "Indicador eq 'IPCA' and Data ge '2026-09-01'"},
    )
    assert "+" not in url, (
        f"Espaço codificado como '+' na URL: {url}. O Olinda responde HTTP 400 "
        "('has the not-allowed value', 'The URI is malformed') quando isso acontece."
    )
    assert "Data%20asc" in url
    assert "Indicador%20eq%20%27IPCA%27" in url


def test_consultar_passa_url_pronta_e_nao_params():
    """A montagem da URL não pode voltar a ser delegada ao requests."""
    with patch("focus.api.requests.get", return_value=_resposta([REGISTRO_ANUAL])) as get:
        expectativas_anuais(indicadores=["IPCA"])

    (url,), kwargs = get.call_args
    assert "params" not in kwargs, (
        "consultar() voltou a usar params= do requests, que codifica espaço como '+'."
    )
    assert url.startswith("https://olinda.bcb.gov.br/")
    assert "?" in url and "+" not in url


def test_indicador_com_acento_e_aspas_sobrevive_a_codificacao():
    """'Câmbio' e as aspas do OData precisam sair percent-encoded, não cru."""
    url = montar_url("X", {"$filter": "Indicador eq 'Câmbio'"})
    assert "C%C3%A2mbio" in url
    assert "%27" in url and "'" not in url


# ── Contrato com o serviço real ───────────────────────────────────────────


@pytest.mark.network
def test_contrato_da_api_anual():
    """Roda no CI. Falha se o BCB mudar nomes de campo ou formato de data."""
    registros = expectativas_anuais(indicadores=["IPCA"], desde=_recente())
    assert registros, "A API não devolveu nenhum registro de IPCA."

    for registro in registros[:20]:
        assert registro.referencia.isdigit() and len(registro.referencia) == 4
        assert registro.mediana is not None
        assert registro.base_calculo in (BASE_30_DIAS, BASE_5_DIAS_UTEIS)
        assert len(registro.data) == 10

    assert any(r.desvio_padrao is not None for r in registros), (
        "Nenhum registro trouxe desvio-padrão — o campo pode ter sido renomeado."
    )


@pytest.mark.network
def test_contrato_da_api_mensal():
    registros = expectativas_mensais(indicadores=["IPCA"], desde=_recente())
    assert registros
    for registro in registros[:20]:
        ano, mes = registro.referencia.split("-")
        assert len(ano) == 4 and len(mes) == 2


@pytest.mark.network
def test_campos_obrigatorios_documentados():
    assert set(CAMPOS_OBRIGATORIOS) == {
        "indicador",
        "data",
        "referencia",
        "mediana",
        "base_calculo",
    }


def _recente():
    from datetime import date, timedelta

    return date.today() - timedelta(days=60)
