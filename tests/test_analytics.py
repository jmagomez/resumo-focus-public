"""Testes da camada analítica."""

import pytest

from focus import analytics as an
from focus.api import BASE_5_DIAS_UTEIS, BASE_30_DIAS
from focus.store import Observacao


def _serie(indicador, referencia, pares, base=BASE_30_DIAS, horizonte="anual", **extra):
    return [
        Observacao(
            data=data,
            indicador=indicador,
            horizonte=horizonte,
            referencia=referencia,
            base_calculo=base,
            mediana=valor,
            **extra,
        )
        for data, valor in pares
    ]


SEMANAS = [
    ("2026-06-12", 5.30),
    ("2026-06-19", 5.20),
    ("2026-06-26", 5.10),
    ("2026-07-03", 5.05),
    ("2026-07-10", 5.00),
    ("2026-07-17", 5.02),
    ("2026-07-24", 4.95),
    ("2026-07-31", 4.90),
]


@pytest.fixture
def historico():
    dados = _serie("IPCA", "2026", SEMANAS)
    dados += _serie("IPCA", "2029", [(d, 3.50) for d, _ in SEMANAS])
    dados += _serie("IPCA", "2026", [("2026-07-31", 4.85)], base=BASE_5_DIAS_UTEIS)
    dados += _serie("Balança comercial", "2026", [("2026-07-24", 76.0), ("2026-07-31", 78.0)])
    return dados


def test_revisao_de_uma_semana(historico):
    (rev,) = [
        r
        for r in an.revisoes(historico, data="2026-07-31")
        if r.indicador == "IPCA" and r.referencia == "2026"
    ]
    assert rev.atual == pytest.approx(4.90)
    assert rev.delta_1s == pytest.approx(-0.05)
    assert rev.data_1_semana == "2026-07-24"
    assert rev.comparacao_exata


def test_revisao_de_quatro_e_treze_semanas(historico):
    (rev,) = [
        r
        for r in an.revisoes(historico, data="2026-07-31")
        if r.indicador == "IPCA" and r.referencia == "2026"
    ]
    assert rev.ha_4_semanas == pytest.approx(5.05)  # 2026-07-03
    assert rev.delta_4s == pytest.approx(-0.15)
    # Não há edição a 13 semanas no histórico de teste.
    assert rev.ha_13_semanas is None
    assert rev.delta_13s is None


def test_comparacao_inexata_e_sinalizada():
    """Quando a edição de 7 dias atrás falta, a data real fica registrada."""
    dados = _serie("IPCA", "2026", [("2026-08-28", 5.01), ("2026-09-11", 4.90)])
    (rev,) = an.revisoes(dados, data="2026-09-11")
    assert rev.delta_1s == pytest.approx(-0.11)
    assert rev.data_1_semana == "2026-08-28"
    assert not rev.comparacao_exata


def test_gap_de_cinco_dias(historico):
    (rev,) = [
        r
        for r in an.revisoes(historico, data="2026-07-31")
        if r.indicador == "IPCA" and r.referencia == "2026"
    ]
    assert rev.gap_5d == pytest.approx(-0.05)


def test_destaques_nao_misturam_unidades(historico):
    """Uma revisão de +2,00 US$ bi não pode superar o IPCA num ranking de p.p.

    Era esse o efeito de ordenar todos os indicadores por magnitude absoluta.
    """
    top = an.destaques(an.revisoes(historico, data="2026-07-31"), quantidade=3)
    assert all(r.unidade == "p.p." for r in top)
    assert "Balança comercial" not in {r.indicador for r in top}


def test_familia_de_unidade():
    assert an.familia("IPCA") == "p.p."
    assert an.familia("Câmbio") == "R$"
    assert an.familia("Balança comercial") == "US$ bi"


def test_por_familia_agrupa_e_ordena(historico):
    grupos = dict(an.por_familia(an.revisoes(historico, data="2026-07-31")))
    assert set(grupos) == {"p.p.", "US$ bi"}
    assert next(u for u, _ in an.por_familia(an.revisoes(historico, data="2026-07-31"))) == "p.p."


def test_trajetoria_ordenada_por_data(historico):
    pontos = an.trajetoria(historico, indicador="IPCA", referencia="2026")
    assert [p.data for p in pontos] == [d for d, _ in SEMANAS]
    assert pontos[-1].valor == pytest.approx(4.90)


def test_curva_por_horizonte(historico):
    curva = an.curva(historico, indicador="IPCA", data="2026-07-31")
    assert curva == [("2026", pytest.approx(4.90)), ("2029", pytest.approx(3.50))]


def test_ancoragem_contra_a_meta_continua(historico):
    pontos = {a.referencia: a for a in an.ancoragem(historico, data="2026-07-31")}
    assert pontos["2029"].desvio == pytest.approx(0.50)
    assert pontos["2029"].dentro_da_banda
    assert pontos["2026"].desvio == pytest.approx(1.90)
    assert not pontos["2026"].dentro_da_banda
    assert "fora da banda" in pontos["2026"].situacao


def test_amplitude_conta_direcoes(historico):
    amplitudes = {a.indicador: a for a in an.amplitude(an.revisoes(historico, data="2026-07-31"))}
    ipca = amplitudes["IPCA"]
    assert ipca.cairam == 1  # 2026 caiu
    assert ipca.estaveis == 1  # 2029 parado
    assert ipca.saldo == pytest.approx(-0.5)


def test_coeficiente_de_variacao():
    dados = [
        Observacao(
            data="2026-09-11",
            indicador="IPCA",
            horizonte="anual",
            referencia="2026",
            base_calculo=BASE_30_DIAS,
            mediana=4.90,
            media=5.00,
            desvio_padrao=0.25,
        )
    ]
    (disp,) = an.dispersao(dados, data="2026-09-11")
    assert disp.coeficiente_variacao == pytest.approx(0.05)


def test_dispersao_sem_desvio_nao_inventa_valor():
    dados = [
        Observacao(
            data="2026-09-11",
            indicador="IPCA",
            horizonte="anual",
            referencia="2026",
            base_calculo=BASE_30_DIAS,
            mediana=4.90,
        )
    ]
    (disp,) = an.dispersao(dados, data="2026-09-11")
    assert disp.coeficiente_variacao is None
    assert disp.amplitude_total is None
