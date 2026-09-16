"""Testes do comando `focus email` — em especial, do contrato com o agente.

O agente escreve a prosa **lendo** a saída de `email --dry-run`: CLAUDE.md diz
que todo número citado tem de aparecer literalmente ali. Enquanto o --dry-run
exigia a prosa para rodar, esse contrato era impossível de cumprir — o agente
precisava do arquivo que ainda ia escrever. Os dois testes abaixo travam os
dois lados: o --dry-run roda sem prosa, o envio real não.
"""

import pytest

from focus import store
from focus.cli import main


def _historico(caminho):
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


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    saida = tmp_path / "output" / "focus"
    saida.mkdir(parents=True)
    monkeypatch.setattr("focus.cli.PASTA_SAIDA", saida)
    return saida, _historico(tmp_path / "hist.csv")


def test_dry_run_roda_sem_prosa(ambiente, capsys):
    """Sem isto, o agente não consegue ler os números que precisa citar."""
    _, historico = ambiente

    codigo = main(["email", "--historico", str(historico), "--dry-run"])
    texto = capsys.readouterr()

    assert codigo == 0
    assert "4,90" in texto.out, "o quadro-resumo precisa sair mesmo sem prosa"
    assert "nenhuma prosa" in texto.err.lower()


def test_envio_real_recusa_sem_prosa(ambiente, capsys):
    """O --dry-run é tolerante; o envio não. Boletim sem prosa não vai ao ar."""
    _, historico = ambiente

    codigo = main(["email", "--historico", str(historico)])
    erro = capsys.readouterr().err

    assert codigo == 1
    assert "sem prosa da semana" in erro
    assert "gerar-resumo" in erro


def test_prosa_da_semana_entra_no_corpo(ambiente, capsys):
    saida, historico = ambiente
    (saida / "focus_2026-09-11.md").write_text(
        "A mediana do IPCA para 2026 recuou para 4,90%.\n\n- IPCA (2026): 5,01 → 4,90.\n",
        encoding="utf-8",
    )

    codigo = main(["email", "--historico", str(historico), "--dry-run"])
    texto = capsys.readouterr()

    assert codigo == 0
    assert "recuou para 4,90%" in texto.out
    assert "nenhuma prosa" not in texto.err.lower()
