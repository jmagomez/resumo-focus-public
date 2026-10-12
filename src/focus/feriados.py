"""Feriados nacionais do Brasil.

Por que este módulo existe
--------------------------
O Focus é publicado pelo BCB às segundas-feiras; em feriado nacional de
segunda, a publicação escorrega (ver `calendario.py`, que dá dois dias de
folga exatamente por isso, sem modelar o calendário). Este módulo modela o
calendário — não para apertar aquela folga, e sim para que a própria cadeia
de publicação (os workflows `focus-semanal`, `focus-resumo` e `focus-enviar`)
saiba, de propósito, parar sem rodar numa segunda-feira que é feriado
nacional, em vez de processar dado que ainda não existe e arriscar reenviar
o e-mail da semana anterior.

Cobre os feriados nacionais fixos (Lei nº 10.607/2002) e a Sexta-feira da
Paixão, móvel, calculada a partir da Páscoa (algoritmo de Meeus/Jones/
Butcher, calendário gregoriano). O Dia Nacional de Zumbi e da Consciência
Negra (20/11) é feriado nacional **desde 2024** (Lei nº 14.759/2023) — antes
disso era ponto facultativo só em alguns estados e municípios, por isso só
entra na lista a partir desse ano.

Carnaval e Corpus Christi **não** entram aqui: são pontos facultativos
definidos por decreto a cada ano, não feriados nacionais por lei. Na prática
o BCB também não publica nesses dias, mas isso seria um alargamento
deliberado além do que foi pedido (feriado nacional) — ver os testes deste
módulo.
"""

from __future__ import annotations

from datetime import date, timedelta

# (mês, dia, nome) — feriados nacionais fixos, Lei nº 10.607/2002.
_FERIADOS_FIXOS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Confraternização Universal"),
    (4, 21, "Tiradentes"),
    (5, 1, "Dia do Trabalho"),
    (9, 7, "Independência do Brasil"),
    (10, 12, "Nossa Senhora Aparecida"),
    (11, 2, "Finados"),
    (11, 15, "Proclamação da República"),
    (12, 25, "Natal"),
)

# Feriado nacional desde 2024 (Lei nº 14.759/2023); antes disso, ponto
# facultativo em parte do país, não feriado nacional por lei.
_CONSCIENCIA_NEGRA = (11, 20, "Dia Nacional de Zumbi e da Consciência Negra")
_CONSCIENCIA_NEGRA_DESDE = 2024


def pascoa(ano: int) -> date:
    """Domingo de Páscoa pelo algoritmo de Meeus/Jones/Butcher (gregoriano).

    >>> pascoa(2024)
    datetime.date(2024, 3, 31)
    >>> pascoa(2025)
    datetime.date(2025, 4, 20)
    >>> pascoa(2026)
    datetime.date(2026, 4, 5)
    """
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    # Evita o nome clássico `l` do algoritmo: ruff (E741) marca `l` como
    # ambíguo por se confundir com `1`.
    p = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * p) // 451
    mes = (h + p - 7 * m + 114) // 31
    dia = (h + p - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> dict[date, str]:
    """Mapa data → nome de todos os feriados nacionais de um ano."""
    feriados = {date(ano, mes, dia): nome for mes, dia, nome in _FERIADOS_FIXOS}

    sexta_da_paixao = pascoa(ano) - timedelta(days=2)
    feriados[sexta_da_paixao] = "Sexta-feira da Paixão"

    if ano >= _CONSCIENCIA_NEGRA_DESDE:
        mes, dia, nome = _CONSCIENCIA_NEGRA
        feriados[date(ano, mes, dia)] = nome

    return feriados


def nome_feriado(data: date) -> str | None:
    """Nome do feriado nacional em ``data``, ou ``None`` se não houver."""
    return feriados_nacionais(data.year).get(data)


def eh_feriado_nacional(data: date) -> bool:
    """``True`` se ``data`` é feriado nacional no Brasil."""
    return data in feriados_nacionais(data.year)


def dia_de_execucao(hoje: date) -> bool:
    """Hoje é o dia de rodar a cadeia semanal?

    Normalmente é a própria segunda-feira. Mas quando a segunda é feriado
    nacional, o BCB não publica nesse dia — ele escorrega para o próximo dia
    útil (terça, ou quarta se a terça também for feriado) — e a cadeia
    precisa escorregar com ele, em vez de só pular a semana inteira e
    esperar a segunda seguinte, uma semana depois de o boletim já ter saído.

    Por isso os workflows agora são agendados de segunda a quarta: esta
    função decide qual desses dias é o certo, achando o primeiro dia (a
    partir da segunda da semana corrente) que não é feriado nacional. Dias
    depois desse primeiro dia útil devolvem ``False`` — a cadeia já rodou (ou
    já devia ter rodado) antes, e não deve rodar de novo.

    >>> dia_de_execucao(date(2026, 8, 31))   # segunda comum
    True
    >>> dia_de_execucao(date(2026, 10, 12))  # segunda, Nossa Senhora Aparecida
    False
    >>> dia_de_execucao(date(2026, 10, 13))  # terça seguinte: dia de recuperação
    True
    >>> dia_de_execucao(date(2026, 9, 1))    # terça comum, depois de segunda comum
    False
    """
    segunda = hoje - timedelta(days=hoje.weekday())
    dia = segunda
    while dia < hoje:
        if not eh_feriado_nacional(dia):
            # Já havia um dia útil (não feriado) antes de hoje nesta semana:
            # a cadeia já rodou (ou já devia ter rodado) nele, não hoje.
            return False
        dia += timedelta(days=1)
    return not eh_feriado_nacional(hoje)
