"""Testes do terceiro endpoint: inflação acumulada em 12 meses.

Era o único número do boletim sem série no histórico. Vinha só do PDF — uma
linha por semana, sem desvio-padrão, sem mínimo/máximo e sem passado — apesar
de ser o que a meta contínua avalia. O endpoint estava declarado em `api.py`
desde a v2 e nunca era consultado.

Duas armadilhas específicas dele, cobertas aqui:

1. **não tem ``DataReferencia``.** O período é sempre "os próximos 12 meses";
   o que varia é a coluna ``Suavizada``. Sem tratamento, a conversão falharia
   por campo obrigatório ausente.
2. **tem duas variantes por (indicador, data, base)**, ``S`` e ``N``, com
   valores muito próximos. Pegar a errada publicaria outra série sob o mesmo
   rótulo sem que nada falhasse.
"""

from unittest.mock import MagicMock, patch

import pytest

from focus import api, store

REGISTRO_12M = {
    "Indicador": "IPCA",
    "Data": "2026-09-11",
    "Suavizada": "S",
    "Media": 4.6512,
    "Mediana": 4.6478,
    "DesvioPadrao": 0.5043,
    "Minimo": 3.2,
    "Maximo": 6.1,
    "numeroRespondentes": 135,
    "baseCalculo": 0,
}


def _resposta(valores):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"value": valores}
    m.text = "{}"
    return m


# ── A variante certa ──────────────────────────────────────────────────────────


def test_consulta_pede_explicitamente_a_suavizada():
    """A base de 5 dias úteis da edição de 11/09 desempata: S dá 4,70; N dá 4,71.

    O PDF publica 4,70. Se este filtro cair, o histórico passa a receber a
    série não suavizada com o rótulo da suavizada — e nada falha.
    """
    with patch("focus.api.requests.get", return_value=_resposta([REGISTRO_12M])) as get:
        api.inflacao_12_meses(indicadores=["IPCA"])

    (url,), _ = get.call_args
    assert "Suavizada%20eq%20%27S%27" in url, url
    assert api.SUAVIZADA == "S"


def test_endpoint_correto_e_sem_mais_na_url():
    with patch("focus.api.requests.get", return_value=_resposta([REGISTRO_12M])) as get:
        api.inflacao_12_meses(indicadores=["IPCA"])
    (url,), _ = get.call_args
    assert api.ENDPOINT_INFLACAO_12M in url
    assert "+" not in url


# ── A mesma chave que o PDF ───────────────────────────────────────────────────


def test_grava_na_mesma_chave_que_o_parser_do_pdf_produz():
    """Mesma chave = a linha da API substitui a do PDF, por precedência de fonte.

    Chave diferente criaria duas representações do mesmo número, e o dashboard
    mostraria as duas.
    """
    with patch("focus.api.requests.get", return_value=_resposta([REGISTRO_12M])):
        (registro,) = api.inflacao_12_meses(indicadores=["IPCA"])

    assert registro.horizonte == "mensal"
    assert registro.referencia == "infl12m"

    (observacao,) = store.de_api([registro])
    assert observacao.chave == ("2026-09-11", "IPCA", "mensal", "infl12m", 0)
    assert observacao.fonte == store.FONTE_API
    assert observacao.desvio_padrao == pytest.approx(0.5043)


def test_api_vence_o_pdf_na_mesma_chave(tmp_path):
    """O ponto de ligar o endpoint: trocar a linha sem dispersão por uma com."""
    caminho = tmp_path / "hist.csv"
    do_pdf = store.Observacao(
        data="2026-09-11",
        indicador="IPCA",
        horizonte="mensal",
        referencia="infl12m",
        base_calculo=0,
        mediana=4.65,
        media=None,
        desvio_padrao=None,
        fonte=store.FONTE_PDF,
    )
    store.mesclar([do_pdf], caminho)

    with patch("focus.api.requests.get", return_value=_resposta([REGISTRO_12M])):
        registros = api.inflacao_12_meses(indicadores=["IPCA"])
    store.mesclar(store.de_api(registros), caminho)

    linhas = [o for o in store.carregar(caminho) if o.referencia == "infl12m"]
    assert len(linhas) == 1, "a linha do PDF deveria ter sido substituída, não duplicada"
    assert linhas[0].fonte == store.FONTE_API
    assert linhas[0].desvio_padrao is not None


# ── Ausência de DataReferencia ────────────────────────────────────────────────


def test_registro_sem_datareferencia_converte():
    """O endpoint não manda DataReferencia — e isso não pode ser erro aqui."""
    assert "DataReferencia" not in REGISTRO_12M
    with patch("focus.api.requests.get", return_value=_resposta([REGISTRO_12M])):
        (registro,) = api.inflacao_12_meses(indicadores=["IPCA"])
    assert registro.referencia == "infl12m"


def test_datareferencia_continua_obrigatoria_nos_outros_quadros():
    """A tolerância vale só para o endpoint de 12 meses, não para os demais."""
    sem_referencia = {k: v for k, v in REGISTRO_12M.items() if k != "Suavizada"}
    with patch("focus.api.requests.get", return_value=_resposta([sem_referencia])):
        with pytest.raises(api.ApiExpectativasError, match="obrigatório"):
            api.expectativas_anuais(indicadores=["IPCA"])


# ── sincronizar passa a trazer os três ────────────────────────────────────────


def test_sincronizar_consulta_os_tres_endpoints():
    with patch("focus.api.requests.get", return_value=_resposta([])) as get:
        api.sincronizar()

    urls = " ".join(chamada.args[0] for chamada in get.call_args_list)
    for endpoint in (api.ENDPOINT_ANUAL, api.ENDPOINT_MENSAL, api.ENDPOINT_INFLACAO_12M):
        assert endpoint in urls, f"{endpoint} não foi consultado"


# ── Contrato com o serviço real ───────────────────────────────────────────────


@pytest.mark.network
def test_contrato_do_endpoint_de_12_meses():
    """Falha se o BCB renomear campo, sumir com a coluna Suavizada ou com os S."""
    from datetime import date, timedelta

    registros = api.inflacao_12_meses(indicadores=["IPCA"], desde=date.today() - timedelta(days=60))
    assert registros, "a API não devolveu nenhum registro suavizado de IPCA em 12 meses."

    for registro in registros[:20]:
        assert registro.referencia == "infl12m"
        assert registro.horizonte == "mensal"
        assert registro.mediana is not None
        assert registro.base_calculo in (api.BASE_30_DIAS, api.BASE_5_DIAS_UTEIS)

    assert any(r.desvio_padrao is not None for r in registros), (
        "Nenhum registro trouxe desvio-padrão — era justamente o que o PDF não dava."
    )


@pytest.mark.network
def test_as_duas_variantes_existem_e_diferem():
    """Se S e N coincidissem, o filtro não importaria. Eles não coincidem."""
    from datetime import date, timedelta

    desde = date.today() - timedelta(days=60)
    suavizada = api.inflacao_12_meses(indicadores=["IPCA"], desde=desde)
    crua = api.consultar(
        api.ENDPOINT_INFLACAO_12M,
        horizonte=api.HORIZONTE_12M,
        indicadores=["IPCA"],
        desde=desde,
        filtros_extra=["Suavizada eq 'N'"],
        referencia_fixa=api.REFERENCIA_12M,
    )
    assert suavizada and crua

    por_chave = {(r.data, r.base_calculo): r.mediana for r in crua}
    diferencas = [
        abs(r.mediana - por_chave[(r.data, r.base_calculo)])
        for r in suavizada
        if (r.data, r.base_calculo) in por_chave and r.mediana is not None
    ]
    assert diferencas, "não deu para parear as duas variantes"
    assert max(diferencas) > 0, "S e N vieram idênticas — o filtro deixaria de importar"
