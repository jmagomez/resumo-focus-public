"""Testes do parser dirigido por cabeçalho.

Cada teste aqui corresponde a um defeito real do parser anterior. Não são
casos hipotéticos: as fixtures são boletins publicados pelo BCB.
"""

from datetime import date

import pytest
from conftest import fixture

from focus.parser import (
    ALTA,
    BAIXA,
    ESTAVEL,
    LayoutDesconhecidoError,
    parsear_arquivo,
    parsear_texto,
)


@pytest.fixture(scope="module")
def completo():
    return parsear_arquivo(fixture("focus_completo.txt"))


@pytest.fixture(scope="module")
def bloco_vazio():
    return parsear_arquivo(fixture("focus_bloco_vazio.txt"))


@pytest.fixture(scope="module")
def sem_hoje():
    return parsear_arquivo(fixture("focus_sem_hoje.txt"))


# ── Períodos lidos do cabeçalho, não do código ────────────────────────────────


def test_periodos_mensais_vem_do_cabecalho(bloco_vazio):
    """O defeito mais grave da versão anterior.

    ``MONTHS`` era uma constante ``["jun/2026", "jul/2026", "ago/2026"]``. O
    boletim de 11/09/2026 traz set/out/nov — três meses de defasagem no rótulo,
    sem nenhum erro emitido.
    """
    assert bloco_vazio.mensal.periodos == ["2026-09", "2026-10", "2026-11", "infl12m"]


def test_periodos_mensais_acompanham_a_edicao(completo, bloco_vazio):
    assert completo.mensal.periodos[:3] == ["2026-07", "2026-08", "2026-09"]
    assert bloco_vazio.mensal.periodos[:3] == ["2026-09", "2026-10", "2026-11"]


def test_periodos_anuais(completo):
    assert completo.anual.periodos == ["2026", "2027", "2028", "2029"]


def test_data_de_publicacao(bloco_vazio):
    assert bloco_vazio.data_publicacao == date(2026, 9, 11)


# ── Alinhamento de colunas ────────────────────────────────────────────────────


def test_bloco_vazio_nao_desloca_as_colunas_seguintes(bloco_vazio):
    """Caso real: Selic mensal em 11/09/2026 traz ``- - -`` para outubro.

    O parser posicional atribuía a mediana de **novembro** à coluna de
    **outubro** e devolvia "-" para novembro. Aqui outubro fica ausente e
    novembro fica com o próprio valor.
    """
    selic = bloco_vazio.mensal["Selic"]
    assert selic["2026-09"].hoje.bruto == "13,75"
    assert selic["2026-10"].hoje.ausente
    assert selic["2026-11"].hoje.bruto == "13,75"


def test_bloco_sem_hoje_nao_consome_o_bloco_seguinte(sem_hoje):
    """Caso real: Câmbio mensal em 31/07/2026 — ``5,13 5,12 -`` e nada depois.

    Sem tratamento, a mediana de 5 dias úteis do bloco seguinte era consumida
    como se pertencesse ao bloco incompleto, e o bloco seguinte ficava com duas
    medianas em vez de três.
    """
    cambio = sem_hoje.mensal["Câmbio"]
    assert cambio["2026-07"].hoje.ausente
    assert cambio["2026-07"].ha_4_semanas.bruto == "5,13"
    assert cambio["2026-08"].hoje.bruto == "5,12"
    assert cambio["2026-09"].hoje.bruto == "5,15"


def test_colunas_de_5_dias_e_respondentes(completo):
    ipca = completo.anual["IPCA"]["2026"]
    assert ipca.hoje.bruto == "5,15"
    assert ipca.ha_1_semana.bruto == "5,16"
    assert ipca.ha_4_semanas.bruto == "5,33"
    assert ipca.cinco_dias_uteis.bruto == "5,17"
    assert ipca.respondentes == 146
    assert ipca.respondentes_5d == 50


def test_valores_negativos_preservam_o_sinal(bloco_vazio):
    conta = bloco_vazio.anual["Conta corrente"]["2026"]
    assert conta.hoje.bruto == "-60,00"
    assert conta.hoje.numero == pytest.approx(-60.0)


def test_indicadores_reconhecidos(bloco_vazio):
    esperados = {
        "IPCA",
        "PIB",
        "Câmbio",
        "Selic",
        "IGP-M",
        "IPCA Administrados",
        "Conta corrente",
        "Balança comercial",
        "Investimento direto no país",
        "DLSP",
        "Resultado primário",
        "Resultado nominal",
    }
    assert esperados <= set(bloco_vazio.anual.indicadores)


# ── Valor literal e derivados ─────────────────────────────────────────────────


def test_bruto_preserva_a_grafia_do_boletim(bloco_vazio):
    """A regra absoluta do projeto: citar o número exatamente como publicado."""
    ipca = bloco_vazio.anual["IPCA"]["2026"]
    assert ipca.hoje.bruto == "4,90"
    assert ipca.hoje.numero == pytest.approx(4.90)


def test_revisao_semanal(bloco_vazio):
    ipca = bloco_vazio.anual["IPCA"]["2026"]
    assert ipca.revisao_semanal == pytest.approx(-0.10)
    assert ipca.comportamento == BAIXA


def test_gap_5_dias(bloco_vazio):
    ipca = bloco_vazio.anual["IPCA"]["2026"]
    assert ipca.gap_5d == pytest.approx(0.05)


def test_comportamento_estavel_sem_seta(bloco_vazio):
    selic = bloco_vazio.anual["Selic"]["2027"]
    assert selic.comportamento == ESTAVEL
    assert selic.semanas_comportamento == 13


def test_comportamento_de_alta(bloco_vazio):
    igpm = bloco_vazio.anual["IGP-M"]["2026"]
    assert igpm.comportamento == ALTA


# ── Falha alta ────────────────────────────────────────────────────────────────


def test_texto_sem_paginas_levanta():
    with pytest.raises(LayoutDesconhecidoError, match="2 páginas"):
        parsear_texto("qualquer coisa sem marcador de página")


def test_cabecalho_com_periodos_a_menos_que_blocos_levanta():
    """Simula mudança de layout: 4 blocos de colunas mas só 2 períodos."""
    texto = (
        "Expectativas de Mercado  11 de setembro de 2026\n"
        "                 2026            2027\n"
        "   Há 4 Há 1 Comp. Resp. 5 dias Resp. Há 4 Há 1 Comp. Resp. 5 dias Resp. "
        "Há 4 Há 1 Comp. Resp. Há 4 Há 1 Comp. Resp.\n"
        "  IPCA (variação %) 5,02 5,00 4,90 (3) 147 4,95 111 4,24 4,29 4,30 (5) 147 "
        "4,31 111 3,80 3,80 3,80 (7) 117 3,50 3,50 3,50 (54) 110\n"
        "Pág. 1/2\n"
        "                 2026-09\n"
        "   Há 4 Há 1 Comp. Resp. 5 dias Há 4 Há 1 Comp. Resp. 5 dias\n"
        "  IPCA (variação %) 0,51 0,53 0,50 (1) 142 0,50 0,33 0,33 0,33 (4) 142 0,34\n"
        "Pág. 2/2\n"
    )
    with pytest.raises(LayoutDesconhecidoError, match="bloco"):
        parsear_texto(texto)


def test_linha_com_medianas_faltando_levanta():
    """Um bloco com menos de três medianas indica layout desconhecido."""
    texto = (
        "Expectativas de Mercado  11 de setembro de 2026\n"
        "                 2026            2027\n"
        "   Há 4 Há 1 Comp. Resp. 5 dias Há 4 Há 1 Comp. Resp. 5 dias\n"
        "  IPCA (variação %) 5,02 5,00 4,90 (3) 147 4,95 4,24 (5) 147 4,31\n"
        "Pág. 1/2\n"
        "                 2026-09          2026-10\n"
        "   Há 4 Há 1 Comp. Resp. 5 dias Há 4 Há 1 Comp. Resp. 5 dias\n"
        "  IPCA (variação %) 0,51 0,53 0,50 (1) 142 0,50 0,33 0,33 0,33 (4) 142 0,34\n"
        "Pág. 2/2\n"
    )
    with pytest.raises(LayoutDesconhecidoError):
        parsear_texto(texto)


def test_nunca_devolve_valor_silenciosamente_errado(bloco_vazio, completo, sem_hoje):
    """Toda célula preenchida tem correspondência literal no texto de origem."""
    for boletim, nome in (
        (bloco_vazio, "focus_bloco_vazio.txt"),
        (completo, "focus_completo.txt"),
        (sem_hoje, "focus_sem_hoje.txt"),
    ):
        origem = fixture(nome).read_text(encoding="utf-8")
        for tabela in (boletim.anual, boletim.mensal):
            for indicador in tabela.indicadores.values():
                for celula in indicador.celulas.values():
                    for valor in (celula.hoje, celula.ha_1_semana, celula.cinco_dias_uteis):
                        if not valor.ausente:
                            assert valor.bruto in origem
