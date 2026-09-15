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

Contrato com o serviço
----------------------
Os nomes de campo do OData do BCB são normalizados aqui (``Mediana`` →
``mediana``, ``numeroRespondentes`` → ``n_respondentes`` etc.) de forma
tolerante a maiúsculas/minúsculas. O teste marcado ``network`` em
``tests/test_api.py`` verifica o contrato contra o serviço real no CI — se o
BCB renomear um campo, a falha aparece lá, não em produção.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"

ENDPOINT_ANUAL = "ExpectativasMercadoAnuais"
ENDPOINT_MENSAL = "ExpectativaMercadoMensais"
ENDPOINT_INFLACAO_12M = "ExpectativasMercadoInflacao12Meses"

#: ``baseCalculo`` na API do BCB.
BASE_30_DIAS = 0
BASE_5_DIAS_UTEIS = 1

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
        """Desvio-padrão sobre |média|.

        Medida de **discordância entre analistas**, comparável entre
        indicadores de escalas diferentes. Alta dispersão com mediana estável
        costuma anteceder revisão — a mediana ainda não se moveu, mas a
        distribuição já se abriu.
        """
        if self.desvio_padrao is None or not self.media:
            return None
        return round(self.desvio_padrao / abs(self.media), 4)


# ── Normalização de campos ────────────────────────────────────────────────────

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


def _para_expectativa(registro: dict[str, Any], horizonte: str) -> Expectativa:
    achatado = {str(k).lower(): v for k, v in registro.items()}

    def pegar(campo: str) -> Any:
        for alias in _ALIASES[campo]:
            if alias in achatado:
                return achatado[alias]
        return None

    faltando = [c for c in CAMPOS_OBRIGATORIOS if pegar(c) is None]
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
        referencia=_normalizar_referencia(pegar("referencia"), horizonte),
        base_calculo=_inteiro(pegar("base_calculo")) or 0,
        mediana=_numero(pegar("mediana")),
        media=_numero(pegar("media")),
        desvio_padrao=_numero(pegar("desvio_padrao")),
        minimo=_numero(pegar("minimo")),
        maximo=_numero(pegar("maximo")),
        n_respondentes=_inteiro(pegar("n_respondentes")),
        horizonte=horizonte,
    )


# ── Consulta ──────────────────────────────────────────────────────────────────


def _aspas(valor: str) -> str:
    return "'" + valor.replace("'", "''") + "'"


def _filtro(indicadores: Sequence[str], desde: date | None, ate: date | None) -> str:
    partes: list[str] = []
    if indicadores:
        alternativas = " or ".join(f"Indicador eq {_aspas(i)}" for i in indicadores)
        partes.append(f"({alternativas})")
    if desde:
        partes.append(f"Data ge {_aspas(desde.isoformat())}")
    if ate:
        partes.append(f"Data le {_aspas(ate.isoformat())}")
    return " and ".join(partes)


def consultar(
    endpoint: str,
    *,
    horizonte: str,
    indicadores: Sequence[str] = INDICADORES_PADRAO,
    desde: date | None = None,
    ate: date | None = None,
    session: requests.Session | None = None,
) -> list[Expectativa]:
    """Consulta um endpoint OData de Expectativas, paginando até o fim."""
    http = session or requests
    filtro = _filtro(indicadores, desde, ate)
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

        url = f"{BASE_URL}/{endpoint}"
        try:
            resposta = http.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
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

        resultados.extend(_para_expectativa(r, horizonte) for r in registros)

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


def sincronizar(
    *,
    desde: date | None = None,
    session: requests.Session | None = None,
) -> list[Expectativa]:
    """Baixa o quadro anual e o mensal em uma chamada só.

    Sem ``desde``, traz os últimos dois anos — janela suficiente para todas as
    métricas de revisão do dashboard sem puxar a série inteira a cada execução.
    """
    desde = desde or (date.today() - timedelta(days=730))
    registros = expectativas_anuais(desde=desde, session=session)
    registros += expectativas_mensais(desde=desde, session=session)
    return registros


def ultima_data(registros: Iterable[Expectativa]) -> str | None:
    datas = sorted({r.data for r in registros})
    return datas[-1] if datas else None
