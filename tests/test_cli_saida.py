"""Testes da SAÍDA da CLI: ordem dos streams e coerência dos vereditos.

Dois defeitos reais, ambos de relatório e não de cálculo — o pipeline fazia a
coisa certa e contava errado.
"""

import io
import sys

from conftest import fixture

from focus import cli, store
from focus.cli import main
from focus.parser import parsear_arquivo

# ── Ordem entre stdout e stderr ───────────────────────────────────────────────


class _Fluxo(io.StringIO):
    """StringIO que anota, num registro compartilhado, a ordem dos eventos."""

    def __init__(self, registro, nome):
        super().__init__()
        self._registro = registro
        self._nome = nome

    def write(self, s):
        if s.strip():
            self._registro.append(f"{self._nome}:{s.strip()}")
        return super().write(s)

    def flush(self):
        self._registro.append("flush")


def test_erro_esvazia_stdout_antes_de_escrever_em_stderr(monkeypatch):
    """Sem o flush, a linha de erro chega ao arquivo antes das que a precederam.

    Nos workflows os dois streams caem no mesmo destino (``2>&1``). stdout tem
    buffer, stderr não. Foi assim que o e-mail do vigia (run 35136532569) chegou
    com o ``[FALHA]`` no topo e a evidência embaixo, e que o log do envio
    (run 35164311085) mostrou ``HTML gravado:`` depois do traceback que o
    interrompeu.
    """
    registro: list[str] = []
    monkeypatch.setattr(sys, "stdout", _Fluxo(registro, "out"))
    monkeypatch.setattr(sys, "stderr", _Fluxo(registro, "err"))

    print("evidência")
    cli._erro("[FALHA] conclusão")

    assert registro == ["out:evidência", "flush", "err:[FALHA] conclusão"], (
        f"ordem observada: {registro}"
    )


def test_nenhum_print_direto_em_stderr_sobrou(monkeypatch):
    """Guarda de regressão: todo caminho de erro passa pelo _erro.

    Um único `print(..., file=sys.stderr)` esquecido reintroduz a desordem
    exatamente no lugar onde ela importa — a mensagem que explica a falha.
    """
    fonte = (cli.__file__ or "").replace(".pyc", ".py")
    with open(fonte, encoding="utf-8") as arquivo:
        linhas = arquivo.read().splitlines()

    culpadas = [
        f"{n}: {linha.strip()}"
        for n, linha in enumerate(linhas, 1)
        # A única ocorrência legítima é a de dentro do próprio _erro.
        if "file=sys.stderr" in linha and n > 40 and "stream=sys.stderr" not in linha
    ]
    assert len(culpadas) == 1, "esperado só o print de dentro de _erro:\n" + "\n".join(culpadas)


# ── Um veredito por assunto ───────────────────────────────────────────────────
#
# O caso central — o mesmo arquivo saindo como [ok] e como [FALHA] — está em
# tests/test_dashboard.py, junto dos outros testes do diagnóstico. Aqui ficam
# os dois lados que faltavam: o que passou precisa aparecer, e o que reprovou
# não pode aparecer, em assuntos diferentes.
#
# Estes dois casos só passaram a testar o que dizem depois da correção do
# `_txt_mais_recente`: com a PASTA_DADOS amarrada na importação, o monkeypatch
# não tinha efeito e o comando lia a data/ real do repositório.


def _historico_saudavel(caminho):
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


def test_verificar_aprova_o_que_passou(tmp_path, monkeypatch, capsys):
    """O contrário também: assunto que passou tem de aparecer como [ok]."""
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
    texto = capsys.readouterr()

    assert codigo == 0
    assert "[ok] Parser:" in texto.out
    assert "[ok] Histórico:" in texto.out
    assert "[ok] Último resumo publicado" in texto.out
    assert "[FALHA]" not in texto.err


def test_parser_reprovado_nao_vira_ok(tmp_path, monkeypatch, capsys):
    """Boletim velho reprova o assunto 'parser' — que então não sai como [ok]."""
    dados = tmp_path / "data"
    saida = tmp_path / "output" / "focus"
    dados.mkdir(parents=True)
    saida.mkdir(parents=True)
    (dados / "focus_2026-07-31.txt").write_text(
        fixture("focus_bloco_vazio.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (saida / "focus_2026-09-11.html").write_text("<html></html>", encoding="utf-8")

    historico = _historico_saudavel(tmp_path / "hist.csv")
    monkeypatch.setattr("focus.cli.PASTA_DADOS", dados)
    monkeypatch.setattr("focus.cli.PASTA_SAIDA", saida)

    codigo = main(["verificar", "--historico", str(historico), "--hoje", "2026-09-14"])
    texto = capsys.readouterr()

    assert codigo == 1
    assert "download pode estar quebrado" in texto.err
    assert "[ok] Parser:" not in texto.out


def test_parsear_arquivo_continua_sendo_a_fonte_do_resumo():
    """Sanidade: o resumo do parser vem do boletim real, não de literal fixo."""
    boletim = parsear_arquivo(fixture("focus_bloco_vazio.txt"))
    assert boletim.anual.periodos and boletim.mensal.periodos
