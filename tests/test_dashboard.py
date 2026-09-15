"""Testes do dashboard estático e do diagnóstico de saúde do pipeline."""

from datetime import date

import pytest
from conftest import fixture

from focus import dashboard, store
from focus.charts import _ticks, num, num_sinal
from focus.cli import main
from focus.parser import parsear_arquivo


@pytest.fixture(scope="module")
def observacoes():
    dados: list[store.Observacao] = []
    for nome in (
        "focus_completo.txt",
        "focus_sem_hoje.txt",
        "focus_anterior.txt",
        "focus_bloco_vazio.txt",
    ):
        dados += store.de_boletim(parsear_arquivo(fixture(nome)))
    return dados


@pytest.fixture(scope="module")
def pagina(observacoes, tmp_path_factory):
    destino = tmp_path_factory.mktemp("docs") / "index.html"
    dashboard.construir(observacoes, destino=destino, hoje=date(2026, 9, 12))
    return destino.read_text(encoding="utf-8")


def test_pagina_e_autocontida(pagina):
    """Sem CDN, sem <script src>, sem <link rel=stylesheet>.

    O painel precisa abrir daqui a dois anos, offline, a partir de um arquivo.
    """
    assert "<script src" not in pagina
    assert "<link" not in pagina
    assert "cdn" not in pagina.lower()
    assert "http://" not in pagina


def test_pagina_declara_os_dois_temas(pagina):
    assert "prefers-color-scheme: dark" in pagina
    assert '[data-theme="dark"]' in pagina
    assert 'name="color-scheme"' in pagina


def test_secoes_presentes(pagina):
    for titulo in ("Revisões", "Trajetória", "Ancoragem", "Dispersão"):
        assert titulo in pagina


def test_tabela_equivalente_existe(pagina):
    """Toda figura precisa de leitura alternativa em tabela."""
    assert "Ver dados em tabela" in pagina
    assert "<table>" in pagina


def test_selo_de_frescor_alerta_quando_os_dados_envelhecem(observacoes, tmp_path):
    destino = tmp_path / "index.html"
    dashboard.construir(observacoes, destino=destino, hoje=date(2026, 11, 1))
    assert "sem atualização" in destino.read_text(encoding="utf-8")


def test_selo_normal_quando_os_dados_estao_frescos(pagina):
    assert "sem atualização" not in pagina


def test_historico_vazio_levanta(tmp_path):
    with pytest.raises(ValueError, match="sincronizar"):
        dashboard.construir([], destino=tmp_path / "x.html")


# ── Formatação e eixos ────────────────────────────────────────────────────────


def test_formato_numerico_brasileiro():
    assert num(1234.5) == "1.234,50"
    assert num(-0.11) == "-0,11"
    assert num_sinal(0.1) == "+0,10"
    assert num_sinal(-0.1) == "-0,10"


def test_eixo_tem_ao_menos_tres_marcas():
    """Um eixo com duas linhas de grade obriga o leitor a interpolar."""
    for minimo, maximo in ((1.16, 5.25), (0.0, 0.03), (-62.5, 80.1), (3.5, 3.5)):
        assert len(_ticks(minimo, maximo)) >= 3


def test_marcas_de_eixo_sao_redondas():
    marcas = _ticks(1.16, 5.25)
    assert all(abs(m - round(m, 2)) < 1e-9 for m in marcas)


# ── Diagnóstico ───────────────────────────────────────────────────────────────


def test_verificar_detecta_pipeline_parado(tmp_path, monkeypatch, capsys):
    """O modo de falha real: download funcionando, boletim não sendo publicado.

    Entre 31/07 e 11/09/2026 o repositório acumulou PDFs sem gerar um único
    resumo, e nenhum alerta disparou.
    """
    dados = tmp_path / "data"
    saida = tmp_path / "output" / "focus"
    dados.mkdir(parents=True)
    saida.mkdir(parents=True)
    (dados / "focus_2026-09-11.txt").write_text(
        fixture("focus_bloco_vazio.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (saida / "focus_2026-07-31.html").write_text("<html></html>", encoding="utf-8")

    historico = tmp_path / "hist.csv"
    store.mesclar(store.de_boletim(parsear_arquivo(fixture("focus_bloco_vazio.txt"))), historico)

    monkeypatch.setattr("focus.cli.PASTA_DADOS", dados)
    monkeypatch.setattr("focus.cli.PASTA_SAIDA", saida)

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-09-14"])
    saida_texto = capsys.readouterr()
    assert codigo == 1
    assert "não está entregando" in saida_texto.err


def test_verificar_aprova_pipeline_saudavel(tmp_path, monkeypatch, capsys):
    dados = tmp_path / "data"
    saida = tmp_path / "output" / "focus"
    dados.mkdir(parents=True)
    saida.mkdir(parents=True)
    (dados / "focus_2026-09-11.txt").write_text(
        fixture("focus_bloco_vazio.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (saida / "focus_2026-09-11.html").write_text("<html></html>", encoding="utf-8")

    historico = tmp_path / "hist.csv"
    store.mesclar(store.de_boletim(parsear_arquivo(fixture("focus_bloco_vazio.txt"))), historico)

    monkeypatch.setattr("focus.cli.PASTA_DADOS", dados)
    monkeypatch.setattr("focus.cli.PASTA_SAIDA", saida)

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-09-14"])
    capsys.readouterr()
    assert codigo == 0
