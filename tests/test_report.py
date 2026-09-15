"""Testes do e-mail: semântica de cor e posição da seta.

Os dois primeiros testes correspondem a defeitos presentes no material que foi
efetivamente enviado por e-mail nas edições anteriores.
"""

import re

import pytest

from focus import analytics as an
from focus.api import BASE_30_DIAS
from focus.report import VERDE, VERMELHO, Prosa, construir, texto_alternativo
from focus.store import Observacao


def _historico(indicador: str, anterior: float, atual: float):
    return [
        Observacao(
            data=data,
            indicador=indicador,
            horizonte="anual",
            referencia="2026",
            base_calculo=BASE_30_DIAS,
            mediana=valor,
        )
        for data, valor in (("2026-09-04", anterior), ("2026-09-11", atual))
    ]


def _html(indicador: str, anterior: float, atual: float) -> str:
    revs = an.revisoes(_historico(indicador, anterior, atual), data="2026-09-11")
    prosa = Prosa(resumo="Resumo de teste.", revisoes=["Item de teste."])
    return construir(revs, prosa, data="2026-09-11")


def _celula_do_valor(html: str, valor: str) -> str:
    """Devolve o trecho da célula que contém o valor em negrito."""
    casamento = re.search(rf"<strong>{re.escape(valor)}</strong>.{{0,120}}", html)
    assert casamento, f"Valor {valor} não encontrado no HTML."
    return casamento.group()


def test_ipca_em_queda_aparece_em_verde():
    """Antes, queda do IPCA saía em vermelho — recuo de inflação é favorável."""
    trecho = _celula_do_valor(_html("IPCA", 5.00, 4.90), "4,90")
    assert VERDE in trecho
    assert VERMELHO not in trecho


def test_ipca_em_alta_aparece_em_vermelho():
    trecho = _celula_do_valor(_html("IPCA", 4.90, 5.00), "5,00")
    assert VERMELHO in trecho


def test_pib_em_queda_aparece_em_vermelho():
    """PIB tem o sentido oposto ao do IPCA: alta é leitura favorável."""
    trecho = _celula_do_valor(_html("PIB", 2.00, 1.89), "1,89")
    assert VERMELHO in trecho


def test_pib_em_alta_aparece_em_verde():
    trecho = _celula_do_valor(_html("PIB", 1.89, 2.00), "2,00")
    assert VERDE in trecho


def test_seta_acompanha_a_mediana_de_hoje():
    """Antes, a seta ficava na coluna 'Sem. passada', sugerindo o movimento errado."""
    trecho = _celula_do_valor(_html("IPCA", 5.00, 4.90), "4,90")
    assert "▼" in trecho


def test_indicador_estavel_nao_ganha_cor_de_direcao():
    trecho = _celula_do_valor(_html("Selic", 13.75, 13.75), "13,75")
    assert VERDE not in trecho and VERMELHO not in trecho
    assert "→" in trecho


def test_prosa_do_agente_aparece_no_corpo():
    html = _html("IPCA", 5.00, 4.90)
    assert "Resumo de teste." in html
    assert "Item de teste." in html


def test_prosa_de_markdown():
    prosa = Prosa.de_markdown(
        "# Focus\n\n"
        "O IPCA de 2026 recuou para 4,90.\n\n"
        "- Selic (2026): 14,00 → 13,75. Hipótese: antecipação de corte.\n"
        "- IPCA (2026): 5,00 → 4,90. Hipótese: leitura corrente benigna.\n"
    )
    assert prosa.resumo == "O IPCA de 2026 recuou para 4,90."
    assert len(prosa.revisoes) == 2
    assert prosa.revisoes[0].startswith("Selic")


def test_sem_revisoes_o_html_nao_fica_com_lista_vazia():
    revs = an.revisoes(_historico("IPCA", 4.90, 4.90), data="2026-09-11")
    html = construir(revs, Prosa(resumo="Semana sem movimento.", revisoes=[]), data="2026-09-11")
    assert "Sem revisões relevantes" in html


def test_texto_alternativo_remove_marcacao():
    texto = texto_alternativo(_html("IPCA", 5.00, 4.90))
    assert "<" not in texto
    assert "Resumo de teste." in texto


def test_link_do_dashboard_e_opcional():
    revs = an.revisoes(_historico("IPCA", 5.00, 4.90), data="2026-09-11")
    prosa = Prosa(resumo="x", revisoes=[])
    sem_link = construir(revs, prosa, data="2026-09-11")
    com_link = construir(revs, prosa, data="2026-09-11", url_dashboard="https://exemplo.test/")
    assert "exemplo.test" not in sem_link
    assert "https://exemplo.test/" in com_link


def test_valores_saem_formatados_em_padrao_brasileiro():
    html = _html("IPCA", 5.00, 4.90)
    assert "4,90" in html
    assert "4.90" not in html.replace("https://", "")


@pytest.mark.parametrize("indicador", ["IPCA", "Selic", "Câmbio", "IGP-M"])
def test_indicadores_de_alta_desfavoravel(indicador):
    assert indicador in an.ALTA_E_DESFAVORAVEL


@pytest.mark.parametrize("indicador", ["PIB", "Resultado primário", "Balança comercial"])
def test_indicadores_de_alta_favoravel(indicador):
    assert indicador not in an.ALTA_E_DESFAVORAVEL
