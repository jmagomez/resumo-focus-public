"""Calendário de publicação do Focus.

Por que este módulo existe
--------------------------
O Focus é **semanal**, e o artefato é nomeado pela **sexta-feira de coleta**
(``R20260911.pdf``), não pela data em que o relatório sai — ele é publicado na
**segunda** seguinte. Conferido de duas formas em 20/09/2026:

* os oito boletins versionados em ``data/`` são, todos, sextas-feiras;
* no portal do BCB, ``R20260911.pdf`` respondia 200 com 778 KB enquanto
  ``R20260918.pdf`` ainda respondia 401, e a própria API de Expectativas tinha
  como data mais recente ``2026-09-11``.

A consequência é que a edição mais recente passa a semana inteira
envelhecendo. Ela tem 3 dias na segunda em que sai e chega a **10 dias** na
manhã da segunda seguinte, antes da próxima publicação — 11 se essa segunda
for feriado, 12 no Carnaval.

Qualquer limiar fixo de "dias desde a coleta" fica, portanto, entre duas
opções ruins: abaixo de 10 ele dispara sozinho em pipeline saudável; acima de
12 ele demora quase duas semanas para notar uma coleta travada. O projeto
usava 8, e no domingo 20/09/2026 o vigia acusou três falhas com o pipeline
rigorosamente em dia.

A pergunta certa não é *"quantos dias tem o dado?"*, e sim *"o dado é a edição
mais recente que já deveria existir?"*. É o que este módulo responde.

Sexta-feira que é feriado
-------------------------
"Nomeado pela sexta" vale para a semana comum. Quando a sexta é feriado, o
BCB fecha a coleta no último dia útil e **data a edição por ele**: a semana de
20/11/2026 (Consciência Negra, sexta) gerou ``R20261119.pdf`` — quinta — e a
API de Expectativas também terminou em ``2026-11-19``.

Exigir a sexta literal produziu o segundo falso alarme deste módulo: de
quarta 25/11 em diante o vigia (run #71) cobrava a "edição de 2026-11-20", que
nunca vai existir, com coleta, histórico, e-mail e painel todos em dia.

A correção não modela feriados — pelo mesmo motivo que a folga de publicação
não modela: o calendário do BCB tem pontos facultativos (24/12, 31/12,
Carnaval) que nenhuma lei lista. Em vez disso, a cobrança passa a ser pela
**semana** da edição esperada: qualquer edição datada de segunda a sexta
dessa semana a satisfaz. Isso não perde poder de detecção — uma coleta
travada fica parada numa semana **anterior**, e continua reprovando no mesmo
dia em que reprovava antes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

#: ``date.weekday()``: segunda=0 … sexta=4 … domingo=6.
SEXTA = 4

#: Prazo que damos ao BCB para publicar a edição de uma sexta: até a **quarta**
#: seguinte.
#:
#: São dois dias de folga além da segunda habitual, o suficiente para absorver
#: feriado de segunda ou de terça sem modelar o calendário de feriados — a
#: mesma escolha que o downloader já faz ao recuar dia a dia em vez de saber
#: quando é 7 de setembro.
PRAZO_DE_PUBLICACAO_DIAS = 5


def _para_data(valor: str | date) -> date:
    return valor if isinstance(valor, date) else datetime.strptime(valor[:10], "%Y-%m-%d").date()


def _segunda_da_semana(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def edicao_esperada(hoje: date) -> date:
    """Sexta de coleta da edição mais recente que já deveria estar publicada.

    É a sexta **nominal** da semana cobrada — serve para nomear a edição nas
    mensagens. Se ela for feriado, a edição real virá datada de um dia antes;
    quem decide se está atrasado é `esta_atrasado`, que compara pela semana.

    >>> edicao_esperada(date(2026, 9, 20))   # domingo
    datetime.date(2026, 9, 11)
    >>> edicao_esperada(date(2026, 9, 21))   # segunda, dia da publicação
    datetime.date(2026, 9, 11)
    >>> edicao_esperada(date(2026, 9, 23))   # quarta: aí sim cobramos a nova
    datetime.date(2026, 9, 18)
    """
    limite = hoje - timedelta(days=PRAZO_DE_PUBLICACAO_DIAS)
    return limite - timedelta(days=(limite.weekday() - SEXTA) % 7)


def inicio_da_semana_esperada(hoje: date) -> date:
    """Segunda-feira da semana cuja edição já deveria estar publicada.

    Qualquer edição datada deste dia em diante satisfaz a cobrança — inclusive
    a de uma quinta, quando a sexta é feriado.

    >>> inicio_da_semana_esperada(date(2026, 11, 25))
    datetime.date(2026, 11, 16)
    """
    return _segunda_da_semana(edicao_esperada(hoje))


def esta_atrasado(edicao: str | date, hoje: date) -> bool:
    """A edição que temos ficou para trás da semana que já deveria existir?

    >>> esta_atrasado("2026-11-19", date(2026, 11, 25))  # sexta 20/11 foi feriado
    False
    >>> esta_atrasado("2026-11-13", date(2026, 11, 25))  # semana anterior: atraso real
    True
    """
    return _para_data(edicao) < inicio_da_semana_esperada(hoje)


def semanas_de_atraso(edicao: str | date, hoje: date) -> int:
    """Quantas edições semanais separam o que temos do que era esperado."""
    distancia = inicio_da_semana_esperada(hoje) - _segunda_da_semana(_para_data(edicao))
    return max(distancia.days, 0) // 7
