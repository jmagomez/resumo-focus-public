"""Cliente da API Olinda de Expectativas de Mercado do Banco Central.

Por que existe
--------------
O PDF do Focus é a *publicação*; a API Olinda é a *fonte*. Ela devolve, já
estruturado e com histórico completo, aquilo que o PDF só mostra em recorte:

* mediana, média, **desvio-padrão**, mínimo e máximo — dispersão, não só nível;
* número de respondentes;
* as duas bases de cálculo (30 dias corridos e 5 dias úteis);
* toda a série histórica, e não apenas "hoje" e "há 1 semana".

Usar a API como fonte primária elimina de uma vez a fragilidade de parsing
posicional, a defasagem de rótulo e a perda de informação. O PDF continua sendo
baixado e arquivado — serve de prova documental e de verificação cruzada.

Três endpoints
--------------
``ExpectativasMercadoAnuais``      projeções por ano-calendário
``ExpectativaMercadoMensais``      projeções por mês de referência
``ExpectativasMercadoInflacao12Meses``
                                   inflação acumulada nos próximos 12 meses

O terceiro tem contrato próprio: não traz ``DataReferencia`` e distingue as
observações por uma coluna ``Suavizada`` (``S``/``N``). Ver `inflacao_12_meses`.

Contrato com o serviço
----------------------
Os nomes de campo do OData do BCB são normalizados aqui (``Mediana`` →
``mediana``, ``numeroRespondentes`` → ``n_respondentes`` etc.) de forma
tolerante a maiúsculas/minúsculas. Os testes marcados ``network`` verificam o
contrato contra o serviço real no CI — se o BCB renomear um campo, a falha
aparece lá, não em produção.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote, urlencode

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"

ENDPOINT_ANUAL = "ExpectativasMercadoAnuais"
ENDPOINT_MENSAL = "ExpectativaMercadoMensais"
ENDPOINT_INFLACAO_12M = "ExpectativasMercadoInflacao12Meses"

#: Chave com que a inflação acumulada em 12 meses entra no histórico.
#:
#: É **a mesma** que o parser do PDF produz, de propósito. Como `store` dá
#: precedência à API sobre o PDF na mesma chave, a linha da API substitui a do
#: PDF e traz o que o PDF não tem: desvio-padrão, mínimo, máximo e série
#: histórica. Mudar esta constante sem mudar o parser cria duas representações
#: do mesmo número, e o dashboard passaria a mostrar as duas.
HORIZONTE_12M = "mensal"
REFERENCIA_12M = "infl12m"

#: Indicadores que o endpoint de 12 meses cobre e que o boletim publica.
INDICADORES_12M: tuple[str, ...] = ("IPCA", "IGP-M")

#: O endpoint devolve duas variantes por (indicador, data, base): ``S``
#: (suavizada) e ``N``. O quadro do Focus — e o número que o texto do boletim
#: cita — é a **suavizada**.
#:
#: Verificado contra a edição de 11/09/2026, onde as duas quase coincidem na
#: base de 30 dias e só a base de 5 dias úteis desempata::
#:
#:     PDF, IPCA 12m, 5 dias úteis ....... 4,70
#:     API, Suavizada="S" ................ 4,6986  → 4,70  ✓
#:     API, Suavizada="N" ................ 4,7103  → 4,71  ✗
#:
#: Trocar para ``"N"`` publicaria outra série sob o mesmo rótulo, sem que nada
#: falhasse — o tipo de erro que só aparece quando alguém confere na mão.
SUAVIZADA = "S"

#: ``baseCalculo`` na API do BCB.
BASE_30_DIAS = 0
BASE_5_DIAS_UTEIS = 1

#: Razão mínima média / desvio-padrão para que o CV seja publicável.
#:
#: O coeficiente de variação exige escala de razão com média estritamente
#: positiva. Numa variável que **cruza o zero** o denominador tende a zero e a
#: razão explode sem que a discordância tenha mudado nada.
#:
#: O valor não é arbitrado: é medido. Nas 37.855 observações anuais com média e
#: desvio-padrão dos últimos dois anos, a razão μ/σ se distribui assim::
#:
#:     [0,0 ; 1,0)   2780 obs   Resultado primário (2776), IGP-M (4)
#:     [1,0 ; 1,5)    198 obs   Resultado primário (163), IGP-M (35)
#:     [1,5 ; 2,0)     50 obs   IGP-M (50)
#:     [2,0 ; 2,5)      0 obs   ← vazio
#:     [2,5 ; 3,0)      8 obs   PIB (8)
#:     [3,0 ; 3,5)     53 obs   PIB (39), IGP-M (12), Balança comercial (2)
#:
#: Os indicadores que cruzam o zero chegam no máximo a 1,26 (resultado
#: primário); o menor valor entre os que nunca cruzam é 2,93 (PIB). A fronteira
#: real é a faixa **(1,26 ; 2,93)**, e há uma lacuna sem nenhuma observação
#: entre 2,0 e 2,5 — qualquer limiar ali dentro classifica igual. 2,0 fica
#: praticamente no centro da faixa, o que torna a escolha robusta em vez de
#: discricionária: 1,5 deixaria passar 50 linhas de IGP-M com média perto de
#: zero; 3,0 começaria a cortar 8 linhas legítimas de PIB.
#:
#: ``tests/test_dispersao.py`` guarda essa separação contra o histórico real.
#: Se ela deixar de valer, o teste falha — e é sinal de que o limiar precisa
#: ser remedido, não de que o teste está errado.
RAZAO_MINIMA_PARA_CV = 2.0


def coeficiente_variacao(desvio_padrao: float | None, media: float | None) -> float | None:
    """CV de uma observação, **ou ``None`` fora do domínio da medida**.

    Definição única do projeto. Existiam três cópias desta conta — aqui, em
    ``analytics.revisoes`` e em ``analytics.Dispersao`` — e só uma delas
    ganhou a guarda quando o defeito foi corrigido. Cópia de fórmula é como
    defeito volta: basta alguém ler a errada.

    Devolver ``None`` é a resposta honesta. Não é que a discordância seja
    desconhecida — o desvio-padrão está ali, na unidade original. É a
    *normalização* que não se aplica.
    """
    if desvio_padrao is None or not media:
        return None
    if media <= 0 or media < RAZAO_MINIMA_PARA_CV * desvio_padrao:
        return None
    return round(desvio_padrao / media, 4)


#: Pares ``(indicador, horizonte)`` que a API de Expectativas **não** serve e
#: que, por isso, só existem no histórico com origem no PDF.
#:
#: A Selic mensal é o caso conhecido: o quadro do Focus a publica por mês de
#: referência, mas os endpoints mensais da API cobrem preços e atividade, não a
#: trajetória de juros mês a mês.
#:
#: Existe para que o diagnóstico possa distinguir "linha sem dispersão porque a
#: fonte primária não tem esse dado" de "linha sem dispersão porque a
#: sincronização falhou". Um alerta que não pode ser resolvido é ruído, e é
#: exatamente assim que se ensina o dono do pipeline a ignorar alertas.
SEM_COBERTURA_NA_API: frozenset[tuple[str, str]] = frozenset({("Selic", "mensal")})

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": ("resumo-focus-public/2.0 (+https://github.com/jmagomez/resumo-focus-public)"),
}

_TIMEOUT = 60
_PAGINA = 10_000

#: Indicadores do quadro do Focus, na grafia que a API usa.
INDICADORES_PADRAO: tuple[str, ...] = (
    "IPCA",
    "IPCA Administrados",
    "IGP-M",
    "PIB Total",
    "Câmbio",
    "Selic",
    "Conta corrente",
    "Balança comercial",
    "Investimento direto no país",
    "Dívida líquida do setor público",
    "Resultado primário",
    "Resultado nominal",
)

#: Como cada indicador da API é chamado no restante do projeto.
NOME_CURTO: dict[str, str] = {
    "PIB Total": "PIB",
    "Dívida líquida do setor público": "DLSP",
    "Dívida bruta do governo geral": "DBGG",
}


class ApiExpectativasError(RuntimeError):
    """Falha ao consultar ou interpretar a API de Expectativas."""


@dataclass(frozen=True)
class Expectativa:
    """Uma observação da pesquisa Focus.

    ``data`` é a data da coleta (a "data do boletim"); ``referencia`` é o
    período projetado ("2026" no quadro anual, "2026-09" no mensal).
    """

    indicador: str
    detalhe: str | None
    data: str
    referencia: str
    base_calculo: int
    mediana: float | None
    media: float | None
    desvio_padrao: float | None
    minimo: float | None
    maximo: float | None
    n_respondentes: int | None
    horizonte: str

    @property
    def coeficiente_variacao(self) -> float | None:
        """Discordância entre analistas, adimensional — ver `coeficiente_variacao`.

        Devolve ``None`` onde o CV não está definido: média negativa, ou
        positiva mas próxima demais do zero para sustentar a divisão.
        """
        return coeficiente_variacao(self.desvio_padrao, self.media)


# ── Normalização de campos ──────────────────────────────────────────────

_ALIASES: dict[str, tuple[str, ...]] = {
    "indicador": ("indicador",),
    "detalhe": ("indicadordetalhe",),
    "data": ("data",),
    "referencia": ("datareferencia",),
    "base_calculo": ("basecalculo",),
    "mediana": ("mediana",),
    "media": ("media",),
    "desvio_padrao": ("desviopadrao",),
    "minimo": ("minimo",),
    "maximo": ("maximo",),
    "n_respondentes": ("numerorespondentes",),
}

CAMPOS_OBRIGATORIOS = ("indicador", "data", "referencia", "mediana", "base_calculo")


def _numero(valor: Any) -> float | None:
    if valor in (None, ""):
        return None
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _inteiro(valor: Any) -> int | None:
    n = _numero(valor)
    return None if n is None else int(n)


def _normalizar_referencia(bruto: Any, horizonte: str) -> str:
    """Converte ``DataReferencia`` para a chave usada no projeto.

    Anual: ``"2026"``. Mensal: ``"09/2026"`` → ``"2026-09"``.
    """
    texto = str(bruto or "").strip()
    if horizonte == "anual":
        return texto
    if "/" in texto:
        mes, ano = texto.split("/", 1)
        return f"{ano.strip()}-{int(mes):02d}"
    return texto


def _para_expectativa(
    registro: dict[str, Any],
    horizonte: str,
    *,
    referencia_fixa: str | None = None,
) -> Expectativa:
    """Converte um registro do OData.

    ``referencia_fixa`` existe para o endpoint de inflação em 12 meses, que
    **não tem** ``DataReferencia``: o período é sempre "os próximos 12 meses",
    e o que varia é a coluna ``Suavizada``. Nesse caso a referência vem de
    fora e deixa de ser campo obrigatório da resposta.
    """
    achatado = {str(k).lower(): v for k, v in registro.items()}

    def pegar(campo: str) -> Any:
        for alias in _ALIASES[campo]:
            if alias in achatado:
                return achatado[alias]
        return None

    obrigatorios = (
        CAMPOS_OBRIGATORIOS
        if referencia_fixa is None
        else tuple(c for c in CAMPOS_OBRIGATORIOS if c != "referencia")
    )
    faltando = [c for c in obrigatorios if pegar(c) is None]
    if faltando:
        raise ApiExpectativasError(
            "Resposta da API sem o(s) campo(s) obrigatório(s) "
            f"{', '.join(faltando)}. Campos recebidos: {sorted(achatado)}. "
            "O contrato do serviço do BCB provavelmente mudou."
        )

    indicador = str(pegar("indicador")).strip()
    return Expectativa(
        indicador=NOME_CURTO.get(indicador, indicador),
        detalhe=(str(pegar("detalhe")).strip() or None) if pegar("detalhe") else None,
        data=str(pegar("data")).strip()[:10],
        referencia=(
            referencia_fixa
            if referencia_fixa is not None
            else _normalizar_referencia(pegar("referencia"), horizonte)
        ),
        base_calculo=_inteiro(pegar("base_calculo")) or 0,
        mediana=_numero(pegar("mediana")),
        media=_numero(pegar("media")),
        desvio_padrao=_numero(pegar("desvio_padrao")),
        minimo=_numero(pegar("minimo")),
        maximo=_numero(pegar("maximo")),
        n_respondentes=_inteiro(pegar("n_respondentes")),
        horizonte=horizonte,
    )


# ── Consulta ───────────────────────────────────────────────────────────────


def _aspas(valor: str) -> str:
    return "'" + valor.replace("'", "''") + "'"


def _filtro(
    indicadores: Sequence[str],
    desde: date | None,
    ate: date | None,
    extras: Sequence[str] = (),
) -> str:
    partes: list[str] = []
    if indicadores:
        alternativas = " or ".join(f"Indicador eq {_aspas(i)}" for i in indicadores)
        partes.append(f"({alternativas})")
    if desde:
        partes.append(f"Data ge {_aspas(desde.isoformat())}")
    if ate:
        partes.append(f"Data le {_aspas(ate.isoformat())}")
    partes.extend(extras)
    return " and ".join(partes)


def montar_url(endpoint: str, params: dict[str, Any]) -> str:
    """Monta a URL da consulta codificando espaço como ``%20``, nunca como ``+``.

    Por que não usar ``requests.get(url, params=...)``
    --------------------------------------------------
    O ``requests`` monta a query string com ``urlencode``/``quote_plus``, que
    é a codificação de formulário HTML: **espaço vira ``+``**. Para quase todo
    servidor isso é equivalente a ``%20``. O OData do Olinda é a exceção: ele
    lê o ``+`` **literalmente**, como se fizesse parte do texto da expressão.

    Verificado contra o serviço real em 15/09/2026, mesmo endpoint, mudando só
    a codificação do espaço::

        $orderby=Data+asc   → HTTP 400 "'$orderby' has the not-allowed value 'Data+asc'"
        $filter=Indicador+eq+'IPCA'+and+Data+ge+'2026-09-01'
                            → HTTP 400 "The types 'Edm.Boolean' and 'Edm.String'
                                        are not compatible"
        (com os 12 indicadores)
                            → HTTP 400 "The URI is malformed."
        as mesmas três com %20
                            → HTTP 200, 10.000 registros

    Custo real do defeito: toda chamada à API falhava com 400, o pipeline caía
    na reserva (PDF) com um WARNING e publicava um histórico sem dispersão,
    sem desvio-padrão e sem trajetória — reportando sucesso. A fonte primária
    nunca funcionou em produção.

    ``safe=""`` é deliberado: sem ele, ``quote`` preservaria ``/`` — inofensivo
    aqui, mas a regra "codifique tudo que não for alfanumérico" é mais fácil de
    manter correta do que uma lista de exceções.
    """
    return f"{BASE_URL}/{endpoint}?{urlencode(params, quote_via=quote, safe='')}"


def consultar(
    endpoint: str,
    *,
    horizonte: str,
    indicadores: Sequence[str] = INDICADORES_PADRAO,
    desde: date | None = None,
    ate: date | None = None,
    session: requests.Session | None = None,
    filtros_extra: Sequence[str] = (),
    referencia_fixa: str | None = None,
) -> list[Expectativa]:
    """Consulta um endpoint OData de Expectativas, paginando até o fim."""
    http = session or requests
    filtro = _filtro(indicadores, desde, ate, filtros_extra)
    resultados: list[Expectativa] = []
    skip = 0

    while True:
        params: dict[str, Any] = {
            "$format": "json",
            "$top": _PAGINA,
            "$skip": skip,
            "$orderby": "Data asc",
        }
        if filtro:
            params["$filter"] = filtro

        # URL montada aqui, não delegada ao `params=` do requests: ver montar_url.
        url = montar_url(endpoint, params)
        try:
            resposta = http.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            raise ApiExpectativasError(f"Falha de rede ao consultar {endpoint}: {exc}") from exc

        if resposta.status_code != 200:
            raise ApiExpectativasError(
                f"{endpoint} respondeu HTTP {resposta.status_code}. "
                f"Corpo (início): {resposta.text[:300]!r}"
            )

        try:
            corpo = resposta.json()
        except ValueError as exc:
            raise ApiExpectativasError(
                f"{endpoint} não devolveu JSON válido: {resposta.text[:300]!r}"
            ) from exc

        registros = corpo.get("value")
        if registros is None:
            raise ApiExpectativasError(
                f"Resposta de {endpoint} sem a chave 'value'. Chaves: {sorted(corpo)}"
            )

        resultados.extend(
            _para_expectativa(r, horizonte, referencia_fixa=referencia_fixa) for r in registros
        )

        if len(registros) < _PAGINA:
            break
        skip += _PAGINA

    log.info("%s: %d registro(s)", endpoint, len(resultados))
    return resultados


def expectativas_anuais(
    *,
    indicadores: Sequence[str] = INDICADORES_PADRAO,
    desde: date | None = None,
    ate: date | None = None,
    session: requests.Session | None = None,
) -> list[Expectativa]:
    """Quadro anual do Focus (projeções por ano-calendário)."""
    return consultar(
        ENDPOINT_ANUAL,
        horizonte="anual",
        indicadores=indicadores,
        desde=desde,
        ate=ate,
        session=session,
    )


def expectativas_mensais(
    *,
    indicadores: Sequence[str] = ("IPCA", "IGP-M", "Câmbio", "Selic"),
    desde: date | None = None,
    ate: date | None = None,
    session: requests.Session | None = None,
) -> list[Expectativa]:
    """Quadro mensal do Focus (projeções por mês de referência)."""
    return consultar(
        ENDPOINT_MENSAL,
        horizonte="mensal",
        indicadores=indicadores,
        desde=desde,
        ate=ate,
        session=session,
    )


def inflacao_12_meses(
    *,
    indicadores: Sequence[str] = INDICADORES_12M,
    desde: date | None = None,
    ate: date | None = None,
    session: requests.Session | None = None,
) -> list[Expectativa]:
    """Inflação acumulada nos próximos 12 meses, variante suavizada.

    É o número que a meta contínua avalia — centro de 3,00% com banda de ±1,5
    p.p. sobre o acumulado em doze meses — e era o único do boletim que não
    tinha série no histórico: vinha só do PDF, uma linha por semana, sem
    dispersão e sem passado. O endpoint já estava declarado aqui desde a v2 e
    nunca era consultado.
    """
    return consultar(
        ENDPOINT_INFLACAO_12M,
        horizonte=HORIZONTE_12M,
        indicadores=indicadores,
        desde=desde,
        ate=ate,
        session=session,
        filtros_extra=[f"Suavizada eq {_aspas(SUAVIZADA)}"],
        referencia_fixa=REFERENCIA_12M,
    )


def sincronizar(
    *,
    desde: date | None = None,
    session: requests.Session | None = None,
) -> list[Expectativa]:
    """Baixa os três quadros em uma chamada só: anual, mensal e 12 meses.

    Sem ``desde``, traz os últimos dois anos — janela suficiente para todas as
    métricas de revisão do dashboard sem puxar a série inteira a cada execução.
    """
    desde = desde or (date.today() - timedelta(days=730))
    registros = expectativas_anuais(desde=desde, session=session)
    registros += expectativas_mensais(desde=desde, session=session)
    registros += inflacao_12_meses(desde=desde, session=session)
    return registros


def ultima_data(registros: Iterable[Expectativa]) -> str | None:
    datas = sorted({r.data for r in registros})
    return datas[-1] if datas else None
