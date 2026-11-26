"""Semana em que a sexta-feira é feriado — dois defeitos com a mesma raiz.

A sexta 20/11/2026 foi o Dia da Consciência Negra. O BCB fechou a coleta na
quinta e datou a edição por ela: ``R20261119.pdf``; a API de Expectativas
também terminou em ``2026-11-19``. O projeto supunha "edição = sexta" em dois
lugares, e os dois quebraram:

1. **Vigia — falso positivo.** De quarta 25/11 em diante, ``verificar``
   cobrava a "edição de 2026-11-20", que nunca vai existir (run #71), com
   coleta, histórico, e-mail e painel todos em dia.

2. **Revisões — número errado publicado.** A comparação "há 1 semana" mirava
   ``19/11 − 7 dias = 12/11`` e, como a API entrega dado diário, achava a
   quinta 12/11 — um dia útil qualquer, não a edição de 13/11. Das 144 séries
   anuais, 88 saíram com a revisão semanal diferente da do boletim e 19
   trocaram de sinal: Selic 2027 +0,50 em vez de +0,25; IPCA 2026 +0,05 em
   vez de +0,04. Foi para o painel e para o e-mail de 23/11.

Os números abaixo são os do histórico real (IPCA 2026, base de 30 dias).
"""

from datetime import date

import pytest
from test_calendario import _cenario

from focus import analytics, calendario, dashboard, store
from focus.cli import main


def _obs(data, mediana, *, desvio_padrao=0.15, indicador="IPCA", referencia="2026"):
    return store.Observacao(
        data=data,
        indicador=indicador,
        horizonte="anual",
        referencia=referencia,
        base_calculo=0,
        mediana=mediana,
        media=mediana,
        desvio_padrao=desvio_padrao,
        n_respondentes=147,
        fonte=store.FONTE_API,
    )


#: Série diária real em torno do feriado: a API não tem 20/11.
DIARIO_NOV = (
    ("2026-11-12", 5.10),
    ("2026-11-13", 5.1082),
    ("2026-11-16", 5.10),
    ("2026-11-17", 5.10),
    ("2026-11-18", 5.1082),
    ("2026-11-19", 5.1505),
)


# ── 1. Vigia ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("dia", [25, 26, 27, 28, 29, 30])
def test_edicao_de_quinta_satisfaz_a_semana_da_sexta_feriado(dia):
    assert not calendario.esta_atrasado("2026-11-19", date(2026, 11, dia))


def test_semana_seguinte_sem_edicao_continua_reprovando():
    """A tolerância é de semana, não de dias: em 02/12 cobra-se a de 27/11."""
    assert not calendario.esta_atrasado("2026-11-19", date(2026, 12, 1))
    assert calendario.esta_atrasado("2026-11-19", date(2026, 12, 2))


def test_coleta_travada_na_semana_anterior_ainda_e_acusada():
    assert calendario.esta_atrasado("2026-11-13", date(2026, 11, 25))
    assert calendario.semanas_de_atraso("2026-11-13", date(2026, 11, 25)) == 1


def test_atraso_contado_em_semanas_mesmo_com_edicao_de_quinta():
    assert calendario.semanas_de_atraso("2026-11-19", date(2026, 12, 9)) == 2


def test_vigia_nao_alarma_na_quarta_depois_da_sexta_feriado(tmp_path, monkeypatch, capsys):
    """O cenário exato da run #71."""
    historico = _cenario(tmp_path, monkeypatch, edicao="2026-11-19", resumo="2026-11-19")

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-11-25"])
    erro = capsys.readouterr().err

    assert codigo == 0, f"vigia alarmou com o pipeline em dia:\n{erro}"
    assert "2026-11-20" not in erro


def test_selo_do_painel_nao_alarma_na_semana_da_sexta_feriado(tmp_path):
    destino = tmp_path / "index.html"
    observacoes = [_obs(d, v) for d, v in DIARIO_NOV]
    dashboard.construir(observacoes, destino=destino, hoje=date(2026, 11, 25))

    assert "selo alerta" not in destino.read_text(encoding="utf-8")


# ── 2. Revisões ─────────────────────────────────────────────────────────────


def test_semana_anterior_e_a_edicao_de_13_11_e_nao_o_dia_12_11():
    (rev,) = analytics.revisoes([_obs(d, v) for d, v in DIARIO_NOV], data="2026-11-19")

    assert rev.data_1_semana == "2026-11-13"
    assert rev.delta_1s == pytest.approx(0.0423)
    assert rev.comparacao_exata, "13/11 é a edição imediatamente anterior"


def test_semana_seguinte_ao_feriado_compara_com_a_edicao_de_quinta():
    observacoes = [_obs(d, v) for d, v in DIARIO_NOV]
    observacoes += [_obs(d, 5.12) for d in ("2026-11-23", "2026-11-24", "2026-11-27")]

    (rev,) = analytics.revisoes(observacoes, data="2026-11-27")

    assert rev.data_1_semana == "2026-11-19"
    assert rev.comparacao_exata


def test_semana_comum_continua_comparando_sexta_com_sexta():
    observacoes = [
        _obs(d, v)
        for d, v in (
            ("2026-11-02", 5.30),
            ("2026-11-03", 5.28),
            ("2026-11-06", 5.25),
            ("2026-11-09", 5.24),
            ("2026-11-13", 5.1082),
        )
    ]

    (rev,) = analytics.revisoes(observacoes, data="2026-11-13")

    assert rev.data_1_semana == "2026-11-06"
    assert rev.delta_1s == pytest.approx(-0.1418)


def test_edicao_faltante_nao_vira_comparacao_exata():
    observacoes = [_obs("2026-10-30", 5.30), _obs("2026-11-13", 5.1082)]

    (rev,) = analytics.revisoes(observacoes, data="2026-11-13")

    assert rev.data_1_semana is None or not rev.comparacao_exata


def test_dispersao_de_4_semanas_usa_a_edicao_e_nao_o_dia():
    observacoes = [
        _obs("2026-10-22", 5.0, desvio_padrao=0.10),
        _obs("2026-10-23", 5.0, desvio_padrao=0.12),
        _obs("2026-11-19", 5.1505, desvio_padrao=0.15),
    ]

    (linha,) = analytics.dispersao(observacoes, data="2026-11-19")

    assert linha.desvio_padrao_4s == 0.12
