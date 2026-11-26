"""Errata: reenviar uma edição com o quadro corrigido, sem apagar o registro.

O e-mail de 19/11/2026 saiu com 16 das 24 variações semanais do quadro-resumo
erradas (comparadas com o dia 12/11, não com a edição de 13/11 — ver
``test_feriado_na_sexta.py``). A prosa estava certa; o quadro, não. A correção
precisa: ir com um assunto que o leitor reconheça como errata; dizer o que
mudou antes do quadro; e não sobrescrever o HTML do envio original, que é o
registro do que foi efetivamente mandado.
"""

import pytest

from focus import report, store
from focus.cli import main

PROSA = "A mediana do IPCA para 2026 recuou para 4,90%.\n\n- IPCA (2026): 5,01 → 4,90.\n"
ERRATA = (
    "O quadro-resumo enviado comparou com a edição errada.\n\n- IPCA (2026): -0,11, e não -0,10.\n"
)


def _historico(caminho):
    store.mesclar(
        [
            store.Observacao(
                data=data,
                indicador="IPCA",
                horizonte="anual",
                referencia="2026",
                base_calculo=0,
                mediana=valor,
                media=valor,
                desvio_padrao=0.25,
                n_respondentes=147,
                fonte=store.FONTE_API,
            )
            for data, valor in (("2026-09-04", 5.01), ("2026-09-11", 4.90))
        ],
        caminho,
    )
    return caminho


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    saida = tmp_path / "output" / "focus"
    saida.mkdir(parents=True)
    (saida / "focus_2026-09-11.md").write_text(PROSA, encoding="utf-8")
    monkeypatch.setattr("focus.cli.PASTA_SAIDA", saida)
    return saida, _historico(tmp_path / "hist.csv")


def test_errata_exige_o_texto_da_correcao(ambiente, capsys):
    _, historico = ambiente

    codigo = main(["email", "--historico", str(historico), "--errata", "--dry-run"])

    assert codigo == 1
    assert "errata_2026-09-11.md" in capsys.readouterr().err


def test_errata_aparece_antes_do_quadro(ambiente, capsys):
    saida, historico = ambiente
    (saida / "errata_2026-09-11.md").write_text(ERRATA, encoding="utf-8")

    codigo = main(["email", "--historico", str(historico), "--errata", "--dry-run"])
    texto = capsys.readouterr().out

    assert codigo == 0
    assert texto.index("Errata") < texto.index("Quadro-resumo")
    assert "e não -0,10" in texto


def test_envio_da_errata_preserva_o_html_original(ambiente, monkeypatch):
    saida, historico = ambiente
    (saida / "errata_2026-09-11.md").write_text(ERRATA, encoding="utf-8")
    original = saida / "focus_2026-09-11.html"
    original.write_text("<html>enviado em 14/09</html>", encoding="utf-8")

    enviados = []
    monkeypatch.setattr("focus.mail.destino_do_ambiente", lambda destinatarios=None: "destino")
    monkeypatch.setattr("focus.mail.montar", lambda assunto, *resto: assunto)
    monkeypatch.setattr("focus.mail.enviar", lambda mensagem, destino: enviados.append(mensagem))

    codigo = main(["email", "--historico", str(historico), "--errata"])

    assert codigo == 0
    assert enviados == ["ERRATA — Boletim Focus — 2026-09-11"]
    assert original.read_text(encoding="utf-8") == "<html>enviado em 14/09</html>"
    assert (saida / "errata_2026-09-11.html").exists()
    # O vigia procura `focus_*.html`: a errata não pode se passar por edição nova.
    assert [p.name for p in saida.glob("focus_*.html")] == ["focus_2026-09-11.html"]


def test_sem_errata_o_email_nao_muda():
    html = report.construir([], report.Prosa(resumo="Texto.", revisoes=[]), data="2026-09-11")

    assert "Errata" not in html
