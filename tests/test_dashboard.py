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


def _historico_saudavel(caminho):
    """Histórico como o de um pipeline funcionando: API entregando, 2+ edições.

    Antes este teste usava um histórico de uma só edição, toda vinda do PDF, e
    afirmava que aquilo era saudável. Não era: foi exatamente o estado em que o
    focus-semanal publicou um dashboard sem revisões e sem dispersão, com todos
    os passos em verde.
    """
    observacoes = []
    for data, valor in (("2026-09-04", 5.01), ("2026-09-11", 4.90)):
        observacoes.append(
            store.Observacao(
                data=data,
                indicador="IPCA",
                horizonte="anual",
                referencia="2026",
                base_calculo=0,
                mediana=valor,
                media=valor + 0.01,
                desvio_padrao=0.25,
                minimo=valor - 0.5,
                maximo=valor + 0.5,
                n_respondentes=147,
                fonte=store.FONTE_API,
            )
        )
    store.mesclar(observacoes, caminho)
    return caminho


def test_verificar_aprova_pipeline_saudavel(tmp_path, monkeypatch, capsys):
    dados = tmp_path / "data"
    saida = tmp_path / "output" / "focus"
    dados.mkdir(parents=True)
    saida.mkdir(parents=True)
    (dados / "focus_2026-09-11.txt").write_text(
        fixture("focus_bloco_vazio.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (saida / "focus_2026-09-11.html").write_text("<html></html>", encoding="utf-8")

    historico = _historico_saudavel(tmp_path / "hist.csv")

    monkeypatch.setattr("focus.cli.PASTA_DADOS", dados)
    monkeypatch.setattr("focus.cli.PASTA_SAIDA", saida)

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-09-14"])
    capsys.readouterr()
    assert codigo == 0


def test_verificar_nao_marca_ok_o_que_reprovou(tmp_path, monkeypatch, capsys):
    """O mesmo fato não pode sair como [ok] e como [FALHA] no mesmo relatório.

    Defeito real, visto no e-mail do vigia de 16/09/2026 (run 35136532569):

        [FALHA] Último resumo publicado é de 2026-07-31 (47 dias). ...
        [ok] Último resumo publicado: focus_2026-07-31.html (47 dias)

    A linha [ok] era impressa incondicionalmente, antes da checagem de idade.
    Num relatório cuja razão de existir é que uma falha passou seis semanas
    despercebida, carimbar [ok] no item quebrado destrói justamente a leitura
    que ele deveria permitir: contar quantos [ok] há.
    """
    dados = tmp_path / "data"
    saida = tmp_path / "output" / "focus"
    dados.mkdir(parents=True)
    saida.mkdir(parents=True)
    (dados / "focus_2026-09-11.txt").write_text(
        fixture("focus_bloco_vazio.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (saida / "focus_2026-07-31.html").write_text("<html></html>", encoding="utf-8")

    historico = _historico_saudavel(tmp_path / "hist.csv")

    monkeypatch.setattr("focus.cli.PASTA_DADOS", dados)
    monkeypatch.setattr("focus.cli.PASTA_SAIDA", saida)

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-09-14"])
    texto = capsys.readouterr()

    assert codigo == 1
    assert "não está entregando" in texto.err
    assert "[ok] Último resumo publicado" not in texto.out, (
        "A entrega reprovou e ainda assim saiu carimbada como [ok]:\n" + texto.out
    )


def test_verificar_reprova_historico_so_com_pdf(tmp_path, monkeypatch, capsys):
    """A fonte primária não entregou nada — e isso não pode passar em verde.

    Caso real: o focus-semanal rodou, deu verde em todos os passos e commitou
    um histórico de 120 linhas, uma só data, todas fonte=pdf, sem dispersão.
    """
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
    erro = capsys.readouterr().err
    assert codigo == 1
    assert "fonte primária não entregou" in erro


def test_verificar_reprova_historico_de_uma_data_so(tmp_path, monkeypatch, capsys):
    """Uma edição só: revisão, trajetória e amplitude saem vazias."""
    dados = tmp_path / "data"
    saida = tmp_path / "output" / "focus"
    dados.mkdir(parents=True)
    saida.mkdir(parents=True)
    (dados / "focus_2026-09-11.txt").write_text(
        fixture("focus_bloco_vazio.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (saida / "focus_2026-09-11.html").write_text("<html></html>", encoding="utf-8")

    historico = tmp_path / "hist.csv"
    store.mesclar(
        [
            store.Observacao(
                data="2026-09-11",
                indicador="IPCA",
                horizonte="anual",
                referencia="2026",
                base_calculo=0,
                mediana=4.90,
                media=4.91,
                desvio_padrao=0.25,
                n_respondentes=147,
                fonte=store.FONTE_API,
            )
        ],
        historico,
    )

    monkeypatch.setattr("focus.cli.PASTA_DADOS", dados)
    monkeypatch.setattr("focus.cli.PASTA_SAIDA", saida)

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-09-14"])
    erro = capsys.readouterr().err
    assert codigo == 1
    assert "1 data(s) apenas" in erro
