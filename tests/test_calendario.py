"""Testes do calendário de publicação — e do falso alarme que ele corrige.

Defeito real, domingo 20/09/2026 (run 35528122444): o vigia acusou três
`[FALHA]` com o pipeline rigorosamente em dia. Naquele momento:

* ``R20260911.pdf`` respondia 200 com 778 KB e ``R20260918.pdf`` respondia 401;
* a data mais recente da API de Expectativas era ``2026-09-11``;
* o histórico do projeto terminava em ``2026-09-11``.

Ou seja: tínhamos tudo o que a fonte tinha. O erro era do medidor — um limiar
fixo de 8 dias aplicado a uma publicação semanal cujo artefato é nomeado pela
sexta de coleta e sai na segunda seguinte.

Num vigia, falso positivo não é incômodo menor: é o que ensina o dono a
ignorar o alerta, que foi exatamente como as seis semanas sem boletim
passaram despercebidas.

O selo do dashboard tinha o mesmo limiar, escrito à mão (``idade <= 8``). Ali
o defeito é latente, não visível: o painel é regerado toda segunda, três dias
depois da edição, então normalmente não dispara. Ele aparece justamente
quando uma coleta semanal falha ou o BCB atrasa — ou seja, soma um alarme
falso ao painel público no momento em que o dono já está preocupado.
"""

from datetime import date

import pytest
from conftest import fixture

from focus import calendario, dashboard, store
from focus.cli import main

SEG, TER, QUA, QUI, SEX, SAB, DOM = range(7)


# ── A regra ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "hoje, esperada, porque",
    [
        (date(2026, 9, 18), date(2026, 9, 11), "sexta: a edição da semana ainda é a de 11/09"),
        (date(2026, 9, 19), date(2026, 9, 11), "sábado"),
        (date(2026, 9, 20), date(2026, 9, 11), "domingo — o caso que gerou o falso alarme"),
        (date(2026, 9, 21), date(2026, 9, 11), "segunda: damos o dia inteiro ao BCB"),
        (date(2026, 9, 22), date(2026, 9, 11), "terça: folga para feriado de segunda"),
        (date(2026, 9, 23), date(2026, 9, 18), "quarta: aí sim cobramos a edição de 18/09"),
        (date(2026, 9, 24), date(2026, 9, 18), "quinta"),
    ],
)
def test_edicao_esperada_ao_longo_da_semana(hoje, esperada, porque):
    assert calendario.edicao_esperada(hoje) == esperada, porque


def test_a_edicao_corrente_chega_a_dez_dias_de_idade_sem_estar_atrasada():
    """É o número que condena qualquer limiar fixo abaixo de 10."""
    edicao = date(2026, 9, 11)
    vespera_da_proxima = date(2026, 9, 21)  # segunda seguinte, antes de publicar
    assert (vespera_da_proxima - edicao).days == 10
    assert not calendario.esta_atrasado(edicao, vespera_da_proxima)


def test_coleta_travada_continua_sendo_atraso():
    """A tolerância não pode virar cegueira: uma semana a mais e reprova."""
    assert calendario.esta_atrasado(date(2026, 9, 11), date(2026, 9, 23))
    assert calendario.semanas_de_atraso(date(2026, 9, 11), date(2026, 9, 23)) == 1
    assert calendario.semanas_de_atraso(date(2026, 9, 11), date(2026, 9, 30)) == 2


def test_aceita_data_em_texto():
    assert not calendario.esta_atrasado("2026-09-11", date(2026, 9, 20))


# ── O vigia, no cenário exato de 20/09 ─────────────────────────────────────


def _cenario(tmp_path, monkeypatch, *, edicao: str, resumo: str):
    dados = tmp_path / "data"
    saida = tmp_path / "output" / "focus"
    dados.mkdir(parents=True)
    saida.mkdir(parents=True)
    (dados / f"focus_{edicao}.txt").write_text(
        fixture("focus_bloco_vazio.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (saida / f"focus_{resumo}.html").write_text("<html></html>", encoding="utf-8")

    historico = tmp_path / "hist.csv"
    store.mesclar(
        [
            store.Observacao(
                data=d,
                indicador="IPCA",
                horizonte="anual",
                referencia="2026",
                base_calculo=0,
                mediana=v,
                media=v,
                desvio_padrao=0.25,
                n_respondentes=147,
                fonte=store.FONTE_API,
            )
            for d, v in (("2026-09-04", 5.01), (edicao, 4.90))
        ],
        historico,
    )
    monkeypatch.setattr("focus.cli.PASTA_DADOS", dados)
    monkeypatch.setattr("focus.cli.PASTA_SAIDA", saida)
    return historico


def test_domingo_com_pipeline_em_dia_nao_alarma(tmp_path, monkeypatch, capsys):
    """O caso da run 35528122444: três [FALHA] sem nada quebrado."""
    historico = _cenario(tmp_path, monkeypatch, edicao="2026-09-11", resumo="2026-09-11")

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-09-20"])
    texto = capsys.readouterr()

    assert codigo == 0, f"vigia alarmou com o pipeline em dia:\n{texto.err}"
    assert "[FALHA]" not in texto.err
    assert "dias" not in texto.err


def test_coleta_travada_e_acusada_na_quarta(tmp_path, monkeypatch, capsys):
    """Mesma edição, três dias depois: agora o atraso é real."""
    historico = _cenario(tmp_path, monkeypatch, edicao="2026-09-11", resumo="2026-09-11")

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-09-23"])
    erro = capsys.readouterr().err

    assert codigo == 1
    assert "2026-09-18" in erro, "a mensagem tem de nomear a edição que falta"
    assert "já deveria estar publicada" in erro


def test_entrega_atras_da_coleta_e_acusada_na_primeira_semana(tmp_path, monkeypatch, capsys):
    """A falha que o vigia existe para pegar — e agora sem esperar 8 dias.

    Coleta avançou para 11/09, entrega parou em 04/09. Medido contra a coleta,
    isso reprova de imediato; medido contra a data de hoje, como antes, só
    apareceria uma semana depois.
    """
    historico = _cenario(tmp_path, monkeypatch, edicao="2026-09-11", resumo="2026-09-04")

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-09-14"])
    erro = capsys.readouterr().err

    assert codigo == 1
    assert "não está entregando o boletim" in erro
    assert "2026-09-11" in erro and "2026-09-04" in erro


# ── O selo do dashboard ──────────────────────────────────────────────────


def test_selo_nao_alarma_no_domingo(tmp_path):
    """Painel regerado num domingo, com o pipeline em dia, não abre em vermelho."""
    observacoes = [
        store.Observacao(
            data=d,
            indicador="IPCA",
            horizonte="anual",
            referencia="2026",
            base_calculo=0,
            mediana=v,
            media=v,
            desvio_padrao=0.25,
            n_respondentes=147,
            fonte=store.FONTE_API,
        )
        for d, v in (("2026-09-04", 5.01), ("2026-09-11", 4.90))
    ]
    destino = tmp_path / "index.html"
    dashboard.construir(observacoes, destino=destino, hoje=date(2026, 9, 20))
    pagina = destino.read_text(encoding="utf-8")

    assert "selo alerta" not in pagina, "painel saudável não pode abrir com selo vermelho"
    assert "9 dias sem atualização" not in pagina
    assert "Dados de 11 de setembro de 2026" in pagina
