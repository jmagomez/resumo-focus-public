"""Testes do histórico: idempotência, precedência de fonte e round-trip."""

import pytest
from conftest import fixture

from focus.api import BASE_5_DIAS_UTEIS, BASE_30_DIAS
from focus.parser import parsear_arquivo
from focus.store import (
    FONTE_API,
    FONTE_PDF,
    Observacao,
    carregar,
    de_boletim,
    gravar,
    mesclar,
)


def _obs(**kwargs) -> Observacao:
    base = dict(
        data="2026-09-11",
        indicador="IPCA",
        horizonte="anual",
        referencia="2026",
        base_calculo=BASE_30_DIAS,
        mediana=4.90,
        fonte=FONTE_API,
    )
    base.update(kwargs)
    return Observacao(**base)


def test_round_trip_preserva_valores(tmp_path):
    caminho = tmp_path / "hist.csv"
    original = _obs(media=4.91, desvio_padrao=0.12, minimo=4.5, maximo=5.4, n_respondentes=147)
    gravar([original], caminho)
    (lido,) = carregar(caminho)
    assert lido == original


def test_historico_inexistente_devolve_lista_vazia(tmp_path):
    assert carregar(tmp_path / "nao-existe.csv") == []


def test_mesclar_e_idempotente(tmp_path):
    """Reprocessar o mesmo boletim não pode duplicar nem alterar linha."""
    caminho = tmp_path / "hist.csv"
    observacoes = [_obs(), _obs(referencia="2027", mediana=4.30)]

    primeira = mesclar(observacoes, caminho)
    assert (primeira.novas, primeira.total) == (2, 2)

    segunda = mesclar(observacoes, caminho)
    assert (segunda.novas, segunda.atualizadas, segunda.inalteradas) == (0, 0, 2)
    assert segunda.total == 2


def test_api_vence_o_pdf(tmp_path):
    """Registro da API substitui o do PDF — só ele traz dispersão."""
    caminho = tmp_path / "hist.csv"
    mesclar([_obs(fonte=FONTE_PDF, n_respondentes=147)], caminho)
    mesclar([_obs(fonte=FONTE_API, desvio_padrao=0.12, media=4.91)], caminho)

    (linha,) = carregar(caminho)
    assert linha.fonte == FONTE_API
    assert linha.desvio_padrao == pytest.approx(0.12)


def test_pdf_nao_sobrescreve_a_api(tmp_path):
    caminho = tmp_path / "hist.csv"
    mesclar([_obs(fonte=FONTE_API, desvio_padrao=0.12)], caminho)
    resultado = mesclar([_obs(fonte=FONTE_PDF)], caminho)

    assert resultado.atualizadas == 0
    (linha,) = carregar(caminho)
    assert linha.fonte == FONTE_API
    assert linha.desvio_padrao == pytest.approx(0.12)


def test_bases_de_calculo_sao_linhas_distintas(tmp_path):
    caminho = tmp_path / "hist.csv"
    mesclar(
        [_obs(base_calculo=BASE_30_DIAS), _obs(base_calculo=BASE_5_DIAS_UTEIS, mediana=4.95)],
        caminho,
    )
    assert len(carregar(caminho)) == 2


def test_de_boletim_grava_as_duas_bases():
    boletim = parsear_arquivo(fixture("focus_bloco_vazio.txt"))
    observacoes = de_boletim(boletim)

    trinta = [
        o
        for o in observacoes
        if o.indicador == "IPCA" and o.referencia == "2026" and o.base_calculo == BASE_30_DIAS
    ]
    cinco = [
        o
        for o in observacoes
        if o.indicador == "IPCA" and o.referencia == "2026" and o.base_calculo == BASE_5_DIAS_UTEIS
    ]
    assert trinta[0].mediana == pytest.approx(4.90)
    assert cinco[0].mediana == pytest.approx(4.95)
    assert all(o.fonte == FONTE_PDF for o in observacoes)


def test_de_boletim_omite_celulas_ausentes():
    """Célula sem mediana não vira linha — nunca entra NaN nem zero no lugar."""
    boletim = parsear_arquivo(fixture("focus_bloco_vazio.txt"))
    observacoes = de_boletim(boletim)
    outubro = [
        o
        for o in observacoes
        if o.indicador == "Selic" and o.horizonte == "mensal" and o.referencia == "2026-10"
    ]
    assert outubro == []
    assert all(o.mediana is not None for o in observacoes)
