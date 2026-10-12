"""Testes do calendário de feriados nacionais.

Por que importa para os workflows: `focus-semanal`, `focus-resumo` e
`focus-enviar` chamam `python -m focus feriado` antes de fazer qualquer
trabalho numa segunda, terça ou quarta — ver `cli.cmd_feriado` e os
comentários nos três arquivos de workflow. Um feriado nacional mal
reconhecido (ou um dia comum tratado como feriado) tanto desperdiça execução
quanto, no pior caso, deixa a cadeia reprocessar a edição da semana anterior
e reenviar o e-mail. E sem o dia de recuperação (`dia_de_execucao`), uma
segunda de feriado nacional não pularia só aquele dia — pularia a semana
inteira, porque a próxima tentativa só viria na segunda seguinte.
"""

from datetime import date

import pytest

from focus import feriados
from focus.cli import main

# ── Páscoa móvel ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ano, esperada",
    [
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
    ],
)
def test_pascoa(ano, esperada):
    assert feriados.pascoa(ano) == esperada


# ── Feriados fixos e móveis ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "data, nome",
    [
        (date(2026, 1, 1), "Confraternização Universal"),
        (date(2026, 4, 3), "Sexta-feira da Paixão"),  # Páscoa 2026 = 05/04
        (date(2026, 4, 21), "Tiradentes"),
        (date(2026, 5, 1), "Dia do Trabalho"),
        (date(2026, 9, 7), "Independência do Brasil"),
        (date(2026, 10, 12), "Nossa Senhora Aparecida"),
        (date(2026, 11, 2), "Finados"),
        (date(2026, 11, 15), "Proclamação da República"),
        (date(2026, 11, 20), "Dia Nacional de Zumbi e da Consciência Negra"),
        (date(2026, 12, 25), "Natal"),
    ],
)
def test_nome_feriado(data, nome):
    assert feriados.nome_feriado(data) == nome
    assert feriados.eh_feriado_nacional(data)


def test_dia_comum_nao_e_feriado():
    assert feriados.nome_feriado(date(2026, 10, 13)) is None
    assert not feriados.eh_feriado_nacional(date(2026, 10, 13))


def test_consciencia_negra_so_e_feriado_nacional_a_partir_de_2024():
    """Lei nº 14.759/2023: antes dela, 20/11 não era feriado nacional por lei."""
    assert not feriados.eh_feriado_nacional(date(2023, 11, 20))
    assert feriados.eh_feriado_nacional(date(2024, 11, 20))


def test_carnaval_nao_e_feriado_nacional():
    """Ponto facultativo por decreto, não feriado nacional por lei — ver o
    docstring do módulo. A segunda de Carnaval de 2026 cai em 16/02."""
    assert not feriados.eh_feriado_nacional(date(2026, 2, 16))


# ── Dia de recuperação: a cadeia escorrega para o próximo dia útil ────────────


def test_segunda_comum_e_dia_de_execucao():
    assert feriados.dia_de_execucao(date(2026, 8, 31))  # segunda, sem feriado


def test_segunda_de_feriado_nao_e_dia_de_execucao():
    assert not feriados.dia_de_execucao(date(2026, 10, 12))  # Nossa Sra. Aparecida


def test_terca_apos_segunda_de_feriado_e_o_dia_de_recuperacao():
    """O caso real: 12/10/2026 (segunda) é feriado, então a cadeia escorrega
    para 13/10/2026 (terça) — em vez de esperar a segunda seguinte, uma
    semana depois de o BCB já ter publicado."""
    assert feriados.dia_de_execucao(date(2026, 10, 13))


def test_terca_apos_segunda_comum_nao_roda_de_novo():
    """01/09/2026 é terça, mas 31/08/2026 (segunda) não era feriado — a
    cadeia já rodou nela, e a terça não deve rodar de novo."""
    assert not feriados.eh_feriado_nacional(date(2026, 8, 31))
    assert not feriados.dia_de_execucao(date(2026, 9, 1))


# ── CLI: o que os workflows realmente chamam ──────────────────────────────────


def test_cli_feriado_reprova_e_nomeia_o_feriado(capsys):
    """12/10/2026 é segunda-feira e Nossa Senhora Aparecida — o caso real que
    motivou este módulo: o .txt mais recente tinha 10 dias nessa manhã porque
    o BCB simplesmente não publica em feriado nacional, não porque a coleta
    estivesse quebrada."""
    codigo = main(["feriado", "--data", "2026-10-12"])
    saida = capsys.readouterr().out

    assert codigo == 1
    assert "feriado nacional" in saida
    assert "Nossa Senhora Aparecida" in saida


def test_cli_feriado_aprova_o_dia_de_recuperacao(capsys):
    """13/10/2026 (terça) é o dia de recuperação da segunda de feriado."""
    codigo = main(["feriado", "--data", "2026-10-13"])
    saida = capsys.readouterr().out

    assert codigo == 0
    assert "[ok]" in saida


def test_cli_feriado_reprova_terca_comum_sem_repetir_a_semana(capsys):
    """Terça comum depois de segunda comum: a cadeia já rodou, não repete."""
    codigo = main(["feriado", "--data", "2026-09-01"])
    saida = capsys.readouterr().out

    assert codigo == 1
    assert "feriado nacional" not in saida
    assert "dia de recuperação" in saida
