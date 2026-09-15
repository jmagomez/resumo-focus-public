"""Leitura estruturada do Boletim Focus a partir do texto extraído do PDF.

Por que este módulo foi reescrito
---------------------------------
A versão anterior extraía os valores por **índice posicional** sobre a lista de
decimais de cada linha (``_ANN_HOJ = [2, 6, 10, 13]``) e carregava os períodos
de referência **fixos no código** (``MONTHS = ["jun/2026", "jul/2026", ...]``).
Isso produzia dois defeitos silenciosos:

1. **Rótulo errado.** O boletim de 11/09/2026 traz set/out/nov 2026; o código
   continuava rotulando jun/jul/ago 2026. Três meses de defasagem, sem erro.

2. **Desalinhamento de coluna.** Quando um bloco vem vazio (``-  -  -``, caso
   real da Selic para out/2026 em 11/09/2026), todos os índices posteriores
   deslizam: o valor de novembro era publicado como se fosse de outubro.

A implementação atual é **dirigida pelo cabeçalho**: os períodos de referência
e o formato de cada bloco de colunas são lidos do próprio PDF, e a linha é
consumida por um analisador de tokens que conhece a gramática da tabela. Quando
o layout do boletim mudar, o parser levanta :class:`LayoutDesconhecidoError` em
vez de devolver número plausível e errado.

Gramática de um bloco de colunas (um período de referência)::

    VALOR VALOR VALOR [SETA] [(n)] [RESP] [VALOR_5D [RESP_5D]]
     Há4   Há1  Hoje   Comp.  sem.  Resp.   5 dias úteis

A presença das colunas "5 dias úteis" e do segundo "Resp." varia por bloco e é
determinada pela linha de subcabeçalho, não por constante no código.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# ── Erros ─────────────────────────────────────────────────────────


class LayoutDesconhecidoError(ValueError):
    """O texto não corresponde ao layout esperado do Boletim Focus.

    Levantado sempre que o parser não consegue provar que leu a tabela
    corretamente. É preferível interromper o pipeline a publicar número errado.
    """


# ── Expressões regulares ────────────────────────────────────────────

_MARCADOR_PAGINA = re.compile(r"P[áa]g\.\s*\d+\s*/\s*\d+")

_MESES_PT = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
_ABREV_MES = {
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}

_DATA_EXTENSO = re.compile(
    r"(\d{1,2})\s+de\s+(" + "|".join(_MESES_PT) + r")\s+de\s+(\d{4})",
    re.IGNORECASE,
)

_MES_ANO = re.compile(r"\b(" + "|".join(_ABREV_MES) + r")/(\d{4})\b", re.IGNORECASE)
_ANO = re.compile(r"(?<![\d/])\b(20\d{2})\b(?!/)")
_INFL_12M = re.compile(r"Infl\.?\s*12\s*m", re.IGNORECASE)

# "Há 4" marca o início de cada bloco na linha de subcabeçalho.
_INICIO_BLOCO = re.compile(r"H[áa]\s*4")

# Ordem da alternativa importa: decimal antes de inteiro (senão "5,02" viraria
# "5"), e o hífen isolado por último (senão comeria o sinal de "-60,00").
_TOKEN = re.compile(
    r"(?P<dec>-?\d+,\d+)"
    r"|(?P<paren>\((\d+)\))"
    r"|(?P<seta>[▲▼])"
    r"|(?P<inteiro>\d+)"
    r"|(?P<nulo>-)"
)

_LINHA_RODAPE = re.compile(r"^\s*\*")

ESTAVEL = "="
ALTA = "▲"
BAIXA = "▼"


# ── Estruturas de dados ────────────────────────────────────────────


@dataclass(frozen=True)
class Valor:
    """Um número do boletim, guardado como texto literal e como float.

    ``bruto`` preserva a grafia exata do relatório ("5,02", "-60,00"). É essa
    forma que deve ser citada em qualquer texto gerado — a regra absoluta do
    projeto é nunca reescrever ou arredondar um número do BCB.
    """

    bruto: str
    numero: float | None

    @property
    def ausente(self) -> bool:
        return self.numero is None

    def __str__(self) -> str:  # pragma: no cover - conveniência de depuração
        return self.bruto


AUSENTE = Valor(bruto="-", numero=None)


def _valor(texto: str) -> Valor:
    if texto in {"-", "", "—"}:
        return AUSENTE
    return Valor(bruto=texto, numero=float(texto.replace(".", "").replace(",", ".")))


@dataclass(frozen=True)
class Celula:
    """As medianas de um indicador para um período de referência."""

    ha_4_semanas: Valor = AUSENTE
    ha_1_semana: Valor = AUSENTE
    hoje: Valor = AUSENTE
    cinco_dias_uteis: Valor = AUSENTE
    comportamento: str = ESTAVEL
    semanas_comportamento: int | None = None
    respondentes: int | None = None
    respondentes_5d: int | None = None

    @property
    def vazia(self) -> bool:
        return self.hoje.ausente and self.ha_1_semana.ausente and self.ha_4_semanas.ausente

    @property
    def revisao_semanal(self) -> float | None:
        """Variação da mediana contra a semana anterior, em unidades do indicador."""
        if self.hoje.numero is None or self.ha_1_semana.numero is None:
            return None
        return round(self.hoje.numero - self.ha_1_semana.numero, 4)

    @property
    def revisao_mensal(self) -> float | None:
        """Variação da mediana contra quatro semanas atrás."""
        if self.hoje.numero is None or self.ha_4_semanas.numero is None:
            return None
        return round(self.hoje.numero - self.ha_4_semanas.numero, 4)

    @property
    def gap_5d(self) -> float | None:
        """Mediana de 5 dias úteis menos a de 30 dias.

        É o indicador antecedente da tabela: a base de 5 dias reage antes que a
        mediana de 30 dias incorpore a informação nova. Gap persistente e de um
        mesmo sinal costuma anteceder a revisão da mediana cheia.
        """
        if self.cinco_dias_uteis.numero is None or self.hoje.numero is None:
            return None
        return round(self.cinco_dias_uteis.numero - self.hoje.numero, 4)


@dataclass(frozen=True)
class Indicador:
    """Uma linha da tabela: o indicador e suas células por período."""

    nome: str
    rotulo_original: str
    celulas: dict[str, Celula] = field(default_factory=dict)

    def __getitem__(self, periodo: str) -> Celula:
        return self.celulas.get(periodo, Celula())


@dataclass(frozen=True)
class Tabela:
    """Uma das tabelas do boletim (anual ou mensal)."""

    horizonte: str  # "anual" | "mensal"
    periodos: list[str]
    indicadores: dict[str, Indicador]

    def __getitem__(self, nome: str) -> Indicador:
        return self.indicadores[nome]


@dataclass(frozen=True)
class Boletim:
    """O boletim inteiro, já estruturado."""

    data_publicacao: date
    anual: Tabela
    mensal: Tabela

    @property
    def data_iso(self) -> str:
        return self.data_publicacao.isoformat()


# ── Normalização de nomes de indicador ─────────────────────────────────

# Mapa de exibição. Não é requisito: indicadores desconhecidos são preservados
# com o rótulo do próprio PDF, de modo que uma linha nova do BCB entre no
# histórico em vez de ser descartada.
_CANONICO: dict[str, str] = {
    "ipca": "IPCA",
    "ipca administrados": "IPCA Administrados",
    "pib total": "PIB",
    "cambio": "Câmbio",
    "selic": "Selic",
    "igp-m": "IGP-M",
    "igp-di": "IGP-DI",
    "ipa-di": "IPA-DI",
    "ipca livres": "IPCA Livres",
    "conta corrente": "Conta corrente",
    "balanca comercial": "Balança comercial",
    "investimento direto no pais": "Investimento direto no país",
    "divida liquida do setor publico": "DLSP",
    "divida bruta do governo geral": "DBGG",
    "resultado primario": "Resultado primário",
    "resultado nominal": "Resultado nominal",
}

# Unidades por indicador canônico — usadas na formatação, nunca no cálculo.
UNIDADES: dict[str, str] = {
    "IPCA": "%",
    "IPCA Administrados": "%",
    "IPCA Livres": "%",
    "PIB": "%",
    "Câmbio": "R$/US$",
    "Selic": "% a.a.",
    "IGP-M": "%",
    "IGP-DI": "%",
    "IPA-DI": "%",
    "Conta corrente": "US$ bi",
    "Balança comercial": "US$ bi",
    "Investimento direto no país": "US$ bi",
    "DLSP": "% do PIB",
    "DBGG": "% do PIB",
    "Resultado primário": "% do PIB",
    "Resultado nominal": "% do PIB",
}


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _canonizar(rotulo: str) -> str:
    """Converte o rótulo do PDF no nome canônico do indicador."""
    limpo = re.sub(r"\(.*?\)", " ", rotulo)  # remove "(variação %)" etc.
    limpo = re.sub(r"\s+", " ", limpo).strip(" .·-")
    chave = _sem_acento(limpo).lower().strip()
    if chave in _CANONICO:
        return _CANONICO[chave]
    # Casamento por prefixo cobre variações de redação do BCB sem hard-code
    # de expressão regular por indicador.
    for prefixo, canonico in _CANONICO.items():
        if chave.startswith(prefixo):
            return canonico
    return limpo or rotulo.strip()


# ── Leitura do cabeçalho ──────────────────────────────────────────


@dataclass(frozen=True)
class _EsquemaBloco:
    """Formato de um bloco de colunas, lido do subcabeçalho do PDF."""

    tem_5_dias: bool
    tem_respondentes_5d: bool


def _periodos_da_linha(linha: str) -> list[str]:
    """Extrai os períodos de referência de uma linha de cabeçalho, em ordem."""
    achados: list[tuple[int, str]] = []

    for m in _MES_ANO.finditer(linha):
        mes = _ABREV_MES[m.group(1).lower()]
        achados.append((m.start(), f"{m.group(2)}-{mes:02d}"))

    if not achados:  # tabela anual: só anos
        for m in _ANO.finditer(linha):
            achados.append((m.start(), m.group(1)))

    for m in _INFL_12M.finditer(linha):
        achados.append((m.start(), "infl12m"))

    achados.sort()
    # Um mesmo período nunca se repete numa linha de cabeçalho; se repetir, é
    # outra linha (rodapé, por exemplo) e não serve como cabeçalho.
    vistos: list[str] = []
    for _, periodo in achados:
        if periodo not in vistos:
            vistos.append(periodo)
    return vistos


def _esquema_dos_blocos(linha: str) -> list[_EsquemaBloco]:
    """Deriva o formato de cada bloco a partir da linha "Há 4 | Há 1 | ...".

    A linha de subcabeçalho repete o grupo de colunas uma vez por período. O
    que varia entre blocos é a presença de "5 dias" e de um segundo "Resp.".
    """
    posicoes = [m.start() for m in _INICIO_BLOCO.finditer(linha)]
    if len(posicoes) < 2:
        return []

    limites = [*posicoes, len(linha)]
    esquemas: list[_EsquemaBloco] = []
    for inicio, fim in itertools.pairwise(limites):
        trecho = linha[inicio:fim]
        esquemas.append(
            _EsquemaBloco(
                tem_5_dias="5 dias" in trecho,
                tem_respondentes_5d=trecho.count("Resp.") >= 2,
            )
        )
    return esquemas


# ── Analisador de linha ────────────────────────────────────────────


@dataclass(frozen=True)
class _Token:
    tipo: str
    texto: str


def _tokenizar(trecho: str) -> list[_Token]:
    tokens: list[_Token] = []
    for m in _TOKEN.finditer(trecho):
        tipo = m.lastgroup
        if tipo == "paren":
            tokens.append(_Token("paren", m.group(3)))
        else:
            tokens.append(_Token(tipo or "", m.group()))
    return tokens


_VALORES = {"dec", "nulo"}


def _parsear_linha(
    linha: str,
    esquemas: list[_EsquemaBloco],
    periodos: list[str],
) -> tuple[str, dict[str, Celula]] | None:
    """Converte uma linha de dados em ``(rótulo, {período: Célula})``.

    Devolve ``None`` quando a linha não é linha de dados. Levanta
    :class:`LayoutDesconhecidoError` quando é linha de dados mas não fecha com
    a gramática esperada — o que indica mudança de layout do boletim.
    """
    if _LINHA_RODAPE.match(linha):
        return None

    primeiro_decimal = re.search(r"-?\d+,\d+", linha)
    if primeiro_decimal is None:
        return None

    rotulo = linha[: primeiro_decimal.start()].strip()
    if not rotulo or not re.match(r"[A-Za-zÀ-ÿ]", rotulo):
        return None

    tokens = _tokenizar(linha[primeiro_decimal.start() :])
    if sum(1 for t in tokens if t.tipo == "dec") < 3:
        return None

    celulas: dict[str, Celula] = {}
    i = 0

    for periodo, esquema in zip(periodos, esquemas, strict=False):
        if i >= len(tokens):
            break

        medianas: list[Valor] = []
        while len(medianas) < 3 and i < len(tokens) and tokens[i].tipo in _VALORES:
            medianas.append(_valor(tokens[i].texto))
            i += 1

        if len(medianas) < 3:
            raise LayoutDesconhecidoError(
                f"Bloco '{periodo}' do indicador '{rotulo}' tem "
                f"{len(medianas)} mediana(s) em vez de 3. "
                "O layout do boletim provavelmente mudou."
            )

        if all(v.ausente for v in medianas):
            celulas[periodo] = Celula()
            continue

        # Quando o BCB não publica a mediana "Hoje" de um período, a linha
        # inteira daquele bloco vem vazia — sem seta, sem "(n)", sem número de
        # respondentes e sem a coluna de 5 dias úteis. Consumir a cauda aqui
        # roubaria a primeira mediana do bloco seguinte (caso real: Câmbio em
        # 31/07/2026, "5,13 5,12 -    5,15 5,14 5,12 ▼").
        if medianas[2].ausente:
            celulas[periodo] = Celula(
                ha_4_semanas=medianas[0],
                ha_1_semana=medianas[1],
                hoje=AUSENTE,
            )
            continue

        comportamento = ESTAVEL
        if i < len(tokens) and tokens[i].tipo == "seta":
            comportamento = tokens[i].texto
            i += 1

        semanas = None
        if i < len(tokens) and tokens[i].tipo == "paren":
            semanas = int(tokens[i].texto)
            i += 1

        # O "(n)" de semanas no comportamento é o marcador confiável de que o
        # grupo completo de colunas existe. Sem ele, qualquer número adiante
        # pertence ao próximo bloco.
        if semanas is None:
            celulas[periodo] = Celula(
                ha_4_semanas=medianas[0],
                ha_1_semana=medianas[1],
                hoje=medianas[2],
                comportamento=comportamento,
            )
            continue

        respondentes = None
        if i < len(tokens) and tokens[i].tipo == "inteiro":
            respondentes = int(tokens[i].texto)
            i += 1

        cinco_dias = AUSENTE
        if esquema.tem_5_dias and i < len(tokens) and tokens[i].tipo in _VALORES:
            cinco_dias = _valor(tokens[i].texto)
            i += 1

        respondentes_5d = None
        if esquema.tem_respondentes_5d and i < len(tokens) and tokens[i].tipo == "inteiro":
            respondentes_5d = int(tokens[i].texto)
            i += 1

        celulas[periodo] = Celula(
            ha_4_semanas=medianas[0],
            ha_1_semana=medianas[1],
            hoje=medianas[2],
            cinco_dias_uteis=cinco_dias,
            comportamento=comportamento,
            semanas_comportamento=semanas,
            respondentes=respondentes,
            respondentes_5d=respondentes_5d,
        )

    sobra = [t for t in tokens[i:] if t.tipo in {"dec", "paren", "inteiro"}]
    if sobra:
        raise LayoutDesconhecidoError(
            f"Sobraram {len(sobra)} token(s) não consumidos na linha '{rotulo}' "
            f"(primeiro: {sobra[0].texto!r}). O layout do boletim mudou."
        )

    return rotulo, celulas


# ── Leitura de uma tabela ──────────────────────────────────────────


def _parsear_tabela(pagina: str, horizonte: str) -> Tabela:
    linhas = pagina.splitlines()

    idx_cabecalho: int | None = None
    periodos: list[str] = []
    for idx, linha in enumerate(linhas):
        candidatos = _periodos_da_linha(linha)
        if len(candidatos) >= 2 and not _INICIO_BLOCO.search(linha):
            idx_cabecalho, periodos = idx, candidatos
            break

    if idx_cabecalho is None:
        raise LayoutDesconhecidoError(
            f"Cabeçalho de períodos não encontrado na tabela {horizonte}."
        )

    esquemas: list[_EsquemaBloco] = []
    for linha in linhas[idx_cabecalho + 1 : idx_cabecalho + 6]:
        esquemas = _esquema_dos_blocos(linha)
        if esquemas:
            break

    if not esquemas:
        raise LayoutDesconhecidoError(
            f"Subcabeçalho de colunas ('Há 4 | Há 1 | ...') não encontrado na tabela {horizonte}."
        )

    if len(esquemas) != len(periodos):
        raise LayoutDesconhecidoError(
            f"Tabela {horizonte}: {len(periodos)} período(s) no cabeçalho "
            f"({', '.join(periodos)}) mas {len(esquemas)} bloco(s) de colunas. "
            "O layout do boletim mudou."
        )

    indicadores: dict[str, Indicador] = {}
    for linha in linhas[idx_cabecalho + 1 :]:
        resultado = _parsear_linha(linha, esquemas, periodos)
        if resultado is None:
            continue
        rotulo, celulas = resultado
        nome = _canonizar(rotulo)
        if nome in indicadores:  # primeira ocorrência vence
            continue
        indicadores[nome] = Indicador(nome=nome, rotulo_original=rotulo, celulas=celulas)

    if not indicadores:
        raise LayoutDesconhecidoError(
            f"Nenhuma linha de indicador reconhecida na tabela {horizonte}."
        )

    return Tabela(horizonte=horizonte, periodos=periodos, indicadores=indicadores)


def _extrair_data(texto: str) -> date:
    m = _DATA_EXTENSO.search(texto)
    if not m:
        raise LayoutDesconhecidoError(
            "Data de publicação não encontrada no texto do boletim "
            "(esperado o formato '11 de setembro de 2026')."
        )
    dia, mes_pt, ano = m.groups()
    return date(int(ano), _MESES_PT[mes_pt.lower()], int(dia))


# ── API pública ───────────────────────────────────────────────────


def parsear_texto(texto: str) -> Boletim:
    """Converte o texto extraído do PDF em um :class:`Boletim` estruturado."""
    paginas = [p for p in _MARCADOR_PAGINA.split(texto) if p.strip()]
    if len(paginas) < 2:
        raise LayoutDesconhecidoError(
            f"Esperadas ao menos 2 páginas separadas por 'Pág. n/m'; encontradas {len(paginas)}."
        )

    return Boletim(
        data_publicacao=_extrair_data(texto),
        anual=_parsear_tabela(paginas[0], "anual"),
        mensal=_parsear_tabela(paginas[1], "mensal"),
    )


def parsear_arquivo(caminho: Path | str) -> Boletim:
    """Lê e estrutura um arquivo ``.txt`` gerado por :func:`focus.pdf.extrair_texto`."""
    return parsear_texto(Path(caminho).read_text(encoding="utf-8"))
