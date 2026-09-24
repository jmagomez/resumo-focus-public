"""Camada analítica sobre o histórico de expectativas.

As métricas aqui são as que um analista usa para ler o Focus — e que a versão
anterior do projeto não conseguia calcular por não guardar histórico:

**Revisão** (1, 4 e 13 semanas)
    Variação da mediana. Uma semana é ruído amostral com frequência; quatro
    semanas já é sinal; treze semanas cobre o intervalo entre reuniões do Copom.

**Amplitude de revisão** (*breadth*)
    Proporção de períodos de referência revisados para cima contra para baixo.
    Revisão difusa e revisão concentrada em um horizonte têm leituras opostas.

**Gap 5 dias × 30 dias**
    A base de 5 dias úteis reage antes. Gap persistente de um mesmo sinal
    costuma anteceder o movimento da mediana cheia.

**Dispersão** (desvio-padrão, sua variação em 4 semanas e o CV)
    Discordância entre analistas. Mediana parada com dispersão subindo indica
    distribuição se abrindo antes de a mediana se mover — leitura que exige a
    *variação* do desvio-padrão, não só o seu nível. O CV normaliza pela média
    e por isso só vale onde a média é positiva e folgada: ver
    ``RAZAO_MINIMA_PARA_CV``.

**Meta contínua** (expectativa de 12 meses)
    O horizonte que o CMN de fato avalia, mês a mês, desde janeiro de 2025 —
    e não o ano-calendário.

**Ancoragem**
    Distância entre a expectativa de IPCA e a meta, por horizonte. Sob o regime
    de **meta contínua** (vigente desde janeiro de 2025), a meta é 3,00% com
    banda de ±1,5 p.p., e o horizonte relevante de política monetária são os
    anos mais distantes — a expectativa de 2026 já está largamente determinada;
    a de 2028/2029 é que mede credibilidade.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import api
from .api import BASE_5_DIAS_UTEIS, BASE_30_DIAS
from .store import Observacao

#: Centro da meta de inflação sob o regime de meta contínua (CMN).
META_INFLACAO = 3.00
#: Banda de tolerância, em pontos percentuais.
BANDA_META = 1.50

#: Indicadores em que "para cima" é leitura desfavorável ao cenário de inflação.
#: Usado só para colorir e redigir — nunca altera número.
ALTA_E_DESFAVORAVEL: frozenset[str] = frozenset(
    {"IPCA", "IPCA Administrados", "IGP-M", "Selic", "Câmbio", "DLSP", "DBGG"}
)

#: Família de unidade de cada indicador.
#:
#: Existe para impedir um erro de leitura fácil de cometer: uma revisão de
#: +1,67 **US$ bi** na balança comercial e uma de +0,10 **p.p.** no IPCA não
#: são comparáveis, e ordená-las juntas por magnitude coloca o saldo comercial
#: acima da inflação em qualquer ranking. Gráficos e destaques agrupam por
#: família; nunca misturam escalas num mesmo eixo.
FAMILIA_UNIDADE: dict[str, str] = {
    "IPCA": "p.p.",
    "IPCA Administrados": "p.p.",
    "IPCA Livres": "p.p.",
    "IGP-M": "p.p.",
    "IGP-DI": "p.p.",
    "IPA-DI": "p.p.",
    "PIB": "p.p.",
    "Selic": "p.p.",
    "DLSP": "p.p.",
    "DBGG": "p.p.",
    "Resultado primário": "p.p.",
    "Resultado nominal": "p.p.",
    "Câmbio": "R$",
    "Conta corrente": "US$ bi",
    "Balança comercial": "US$ bi",
    "Investimento direto no país": "US$ bi",
}

#: Ordem de apresentação das famílias: a de política monetária vem primeiro.
ORDEM_FAMILIAS: tuple[str, ...] = ("p.p.", "R$", "US$ bi")


def familia(indicador: str) -> str:
    """Família de unidade do indicador; 'p.p.' para desconhecidos."""
    return FAMILIA_UNIDADE.get(indicador, "p.p.")


def _para_data(texto: str) -> date:
    return datetime.strptime(texto[:10], "%Y-%m-%d").date()


def datas_disponiveis(obs: Iterable[Observacao]) -> list[str]:
    return sorted({o.data for o in obs})


def desde_semanas(obs: Iterable[Observacao], semanas: int) -> str | None:
    """Data de corte ``semanas`` antes da última edição — em **calendário**.

    Recortar janela por *contagem de datas disponíveis* (``datas[-52:]``) é
    errado aqui e o erro é silencioso. A API de Expectativas entrega dado
    **diário**, não semanal: o histórico tem 505 datas em dois anos, das quais
    só 101 são sextas-feiras. ``datas[-52:]`` rendia 72 dias corridos num
    gráfico rotulado como um ano.

    A janela é do calendário, nunca do índice. Quantas observações caem dentro
    dela é consequência, não parâmetro.
    """
    ultima = ultima_data(obs)
    if ultima is None:
        return None
    return (_para_data(ultima) - timedelta(weeks=semanas)).isoformat()


def ultima_data(obs: Iterable[Observacao]) -> str | None:
    datas = datas_disponiveis(obs)
    return datas[-1] if datas else None


def _indexar(
    obs: Iterable[Observacao], base_calculo: int
) -> dict[tuple[str, str, str], dict[str, Observacao]]:
    """``(indicador, horizonte, referencia) -> {data: Observacao}``."""
    indice: dict[tuple[str, str, str], dict[str, Observacao]] = {}
    for o in obs:
        if o.base_calculo != base_calculo or o.mediana is None:
            continue
        indice.setdefault((o.indicador, o.horizonte, o.referencia), {})[o.data] = o
    return indice


def _data_mais_proxima(datas: Sequence[str], alvo: date, tolerancia_dias: int = 10) -> str | None:
    """Data disponível mais próxima de ``alvo``, dentro da tolerância.

    O Focus é semanal mas escorrega em feriados; casar data exata perderia
    semanas legítimas. A tolerância de 10 dias cobre o escorregamento sem
    permitir que "há 4 semanas" vire "há 8 semanas" silenciosamente.
    """
    melhor: tuple[int, str] | None = None
    for texto in datas:
        distancia = abs((_para_data(texto) - alvo).days)
        if distancia <= tolerancia_dias and (melhor is None or distancia < melhor[0]):
            melhor = (distancia, texto)
    return None if melhor is None else melhor[1]


# ── Revisões ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Revisao:
    indicador: str
    horizonte: str
    referencia: str
    atual: float
    ha_1_semana: float | None
    ha_4_semanas: float | None
    ha_13_semanas: float | None
    n_respondentes: int | None
    coeficiente_variacao: float | None
    gap_5d: float | None
    #: Datas efetivamente usadas em cada comparação. O Focus escorrega em
    #: feriados e edições faltam; dizer "contra a semana anterior" quando a
    #: edição comparada é de duas semanas atrás seria impreciso, então a data
    #: real fica registrada e aparece na interface.
    data: str = ""
    data_1_semana: str | None = None
    data_4_semanas: str | None = None
    data_13_semanas: str | None = None

    @property
    def unidade(self) -> str:
        return familia(self.indicador)

    @property
    def comparacao_exata(self) -> bool:
        """Falso quando a edição usada como "semana anterior" não é de 7 dias."""
        if not self.data or not self.data_1_semana:
            return False
        dias = abs((_para_data(self.data) - _para_data(self.data_1_semana)).days)
        return dias == 7

    def _delta(self, anterior: float | None) -> float | None:
        return None if anterior is None else round(self.atual - anterior, 4)

    @property
    def delta_1s(self) -> float | None:
        return self._delta(self.ha_1_semana)

    @property
    def delta_4s(self) -> float | None:
        return self._delta(self.ha_4_semanas)

    @property
    def delta_13s(self) -> float | None:
        return self._delta(self.ha_13_semanas)

    @property
    def magnitude(self) -> float:
        """Usada só para ordenar destaques; nunca aparece como número citado."""
        return abs(self.delta_1s or 0.0)


def revisoes(
    obs: Iterable[Observacao],
    *,
    data: str | None = None,
    horizonte: str | None = None,
) -> list[Revisao]:
    """Calcula as revisões de todos os indicadores na data indicada."""
    observacoes = list(obs)
    data = data or ultima_data(observacoes)
    if data is None:
        return []

    indice_30 = _indexar(observacoes, BASE_30_DIAS)
    indice_5 = _indexar(observacoes, BASE_5_DIAS_UTEIS)
    referencia = _para_data(data)

    resultado: list[Revisao] = []
    for (indicador, horiz, ref), serie in indice_30.items():
        if horizonte and horiz != horizonte:
            continue
        atual = serie.get(data)
        if atual is None or atual.mediana is None:
            continue

        datas = sorted(serie)

        def anterior(semanas: int, _datas=datas, _serie=serie) -> tuple[float | None, str | None]:
            alvo = referencia - timedelta(weeks=semanas)
            achada = _data_mais_proxima(_datas, alvo)
            if achada is None:
                return None, None
            return _serie[achada].mediana, achada

        valor_1s, data_1s = anterior(1)
        valor_4s, data_4s = anterior(4)
        valor_13s, data_13s = anterior(13)

        cinco = indice_5.get((indicador, horiz, ref), {}).get(data)
        gap = (
            round(cinco.mediana - atual.mediana, 4)
            if cinco is not None and cinco.mediana is not None
            else None
        )

        # Terceira cópia da mesma conta, e a que ninguém lia: nenhum consumidor
        # do projeto usava `Revisao.coeficiente_variacao`. Campo morto com a
        # fórmula sem guarda é armadilha armada — quem for usá-lo amanhã herda
        # o defeito corrigido hoje em outro lugar. Passa pela definição única.
        cv = api.coeficiente_variacao(atual.desvio_padrao, atual.media)

        resultado.append(
            Revisao(
                indicador=indicador,
                horizonte=horiz,
                referencia=ref,
                atual=atual.mediana,
                ha_1_semana=valor_1s,
                ha_4_semanas=valor_4s,
                ha_13_semanas=valor_13s,
                n_respondentes=atual.n_respondentes,
                coeficiente_variacao=cv,
                gap_5d=gap,
                data=data,
                data_1_semana=data_1s,
                data_4_semanas=data_4s,
                data_13_semanas=data_13s,
            )
        )

    resultado.sort(key=lambda r: (r.indicador, r.horizonte, r.referencia))
    return resultado


def destaques(
    revs: Sequence[Revisao],
    *,
    quantidade: int = 3,
    unidade: str | None = "p.p.",
) -> list[Revisao]:
    """As maiores revisões semanais em módulo — o que merece ser comentado.

    Restringe a uma família de unidade por padrão (``p.p.``), porque ordenar
    magnitudes de escalas diferentes num mesmo ranking colocaria a balança
    comercial, medida em dezenas de US$ bilhões, sistematicamente à frente do
    IPCA. Passe ``unidade=None`` para ignorar o agrupamento.
    """
    com_movimento = [
        r
        for r in revs
        if r.delta_1s not in (None, 0.0) and (unidade is None or r.unidade == unidade)
    ]
    com_movimento.sort(key=lambda r: (-r.magnitude, r.referencia))
    return com_movimento[:quantidade]


def por_familia(revs: Sequence[Revisao]) -> list[tuple[str, list[Revisao]]]:
    """Agrupa revisões por família de unidade, na ordem de apresentação."""
    grupos: dict[str, list[Revisao]] = {}
    for r in revs:
        grupos.setdefault(r.unidade, []).append(r)
    ordenadas = sorted(
        grupos.items(),
        key=lambda item: (
            ORDEM_FAMILIAS.index(item[0]) if item[0] in ORDEM_FAMILIAS else 99,
            item[0],
        ),
    )
    return ordenadas


# ── Amplitude ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Amplitude:
    """Quantos períodos foram revisados para cada lado, por indicador."""

    indicador: str
    subiram: int
    cairam: int
    estaveis: int

    @property
    def total(self) -> int:
        return self.subiram + self.cairam + self.estaveis

    @property
    def saldo(self) -> float | None:
        """(subiram − caíram) / total. Varia de −1 a +1."""
        if self.total == 0:
            return None
        return round((self.subiram - self.cairam) / self.total, 3)


def amplitude(revs: Sequence[Revisao]) -> list[Amplitude]:
    agregado: dict[str, list[int]] = {}
    for r in revs:
        delta = r.delta_1s
        if delta is None:
            continue
        linha = agregado.setdefault(r.indicador, [0, 0, 0])
        if delta > 0:
            linha[0] += 1
        elif delta < 0:
            linha[1] += 1
        else:
            linha[2] += 1
    return [
        Amplitude(indicador=nome, subiram=v[0], cairam=v[1], estaveis=v[2])
        for nome, v in sorted(agregado.items())
    ]


# ── Trajetórias ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Ponto:
    data: str
    valor: float
    minimo: float | None = None
    maximo: float | None = None


def trajetoria(
    obs: Iterable[Observacao],
    *,
    indicador: str,
    referencia: str,
    horizonte: str = "anual",
    base_calculo: int = BASE_30_DIAS,
    desde: str | None = None,
) -> list[Ponto]:
    """Série temporal da mediana para um par (indicador, período de referência).

    É este o gráfico que mostra *como a expectativa foi sendo revisada* — a
    leitura central do Focus, e a que o projeto não conseguia produzir.
    """
    pontos = [
        Ponto(data=o.data, valor=o.mediana, minimo=o.minimo, maximo=o.maximo)
        for o in obs
        if o.indicador == indicador
        and o.horizonte == horizonte
        and o.referencia == referencia
        and o.base_calculo == base_calculo
        and o.mediana is not None
        and (desde is None or o.data >= desde)
    ]
    pontos.sort(key=lambda p: p.data)
    return pontos


def amostrar_semanal(pontos: Sequence[Ponto]) -> list[Ponto]:
    """Um ponto por semana ISO — o último, que é a edição de sexta.

    A série diária da API tem cinco pontos por semana para um relatório que é
    semanal. Desenhá-la inteira não acrescenta informação: engrossa a linha com
    o vaivém intrassemanal da janela móvel de 30 dias e força o eixo a escolher
    entre densidade ilegível e janela curta.

    Ficar com o último ponto de cada semana reproduz a cadência do próprio
    Focus e permite desenhar dois anos de história com ~100 marcas.
    """
    por_semana: dict[tuple[int, int], Ponto] = {}
    for ponto in sorted(pontos, key=lambda p: p.data):
        ano, semana, _ = _para_data(ponto.data).isocalendar()
        por_semana[(ano, semana)] = ponto
    return [por_semana[chave] for chave in sorted(por_semana)]


def curva(
    obs: Iterable[Observacao],
    *,
    indicador: str,
    data: str,
    horizonte: str = "anual",
    base_calculo: int = BASE_30_DIAS,
) -> list[tuple[str, float]]:
    """Expectativa por horizonte numa data — a "curva" de expectativas.

    Para o IPCA, a inclinação desta curva é a leitura de ancoragem: convergência
    rumo a 3,00% nos anos longos indica credibilidade da meta.
    """
    pares = [
        (o.referencia, o.mediana)
        for o in obs
        if o.indicador == indicador
        and o.horizonte == horizonte
        and o.data == data
        and o.base_calculo == base_calculo
        and o.mediana is not None
    ]
    pares.sort()
    return pares


# ── Ancoragem ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Ancoragem:
    referencia: str
    expectativa: float
    desvio: float
    dentro_da_banda: bool

    @property
    def situacao(self) -> str:
        if not self.dentro_da_banda:
            lado = "acima" if self.desvio > 0 else "abaixo"
            return f"fora da banda ({lado})"
        if abs(self.desvio) < 0.05:
            return "no centro da meta"
        return "acima do centro" if self.desvio > 0 else "abaixo do centro"


def ancoragem(
    obs: Iterable[Observacao],
    *,
    data: str,
    indicador: str = "IPCA",
    meta: float = META_INFLACAO,
    banda: float = BANDA_META,
) -> list[Ancoragem]:
    """Desvio da expectativa de inflação em relação à meta, por horizonte."""
    return [
        Ancoragem(
            referencia=ref,
            expectativa=valor,
            desvio=round(valor - meta, 4),
            dentro_da_banda=abs(valor - meta) <= banda,
        )
        for ref, valor in curva(obs, indicador=indicador, data=data)
    ]


# ── O horizonte que a meta contínua avalia ────────────────────────────────
#
# A meta contínua não é avaliada por ano-calendário. Desde janeiro de 2025 o
# CMN a afere **mês a mês sobre o IPCA acumulado em doze meses** — e o Focus
# publica exatamente essa expectativa, na série `infl12m`, suavizada.
#
# É o número mais importante do boletim para quem acompanha política monetária,
# e era o único que o projeto coletava sem nunca exibir.

#: Chave da série de inflação acumulada em 12 meses no histórico longo.
HORIZONTE_12M = "mensal"
REFERENCIA_12M = "infl12m"


@dataclass(frozen=True)
class Meta12Meses:
    """Leitura da expectativa de 12 meses contra a banda da meta contínua."""

    data: str
    expectativa: float
    desvio: float
    piso: float
    teto: float
    desvio_padrao: float | None = None
    n_respondentes: int | None = None

    @property
    def dentro_da_banda(self) -> bool:
        return self.piso <= self.expectativa <= self.teto

    @property
    def situacao(self) -> str:
        if self.expectativa > self.teto:
            return "acima do teto da banda"
        if self.expectativa < self.piso:
            return "abaixo do piso da banda"
        if abs(self.desvio) < 0.05:
            return "no centro da meta"
        return "acima do centro" if self.desvio > 0 else "abaixo do centro"

    @property
    def excesso(self) -> float:
        """Quanto a expectativa passa da banda, em p.p. Zero se dentro."""
        if self.expectativa > self.teto:
            return round(self.expectativa - self.teto, 4)
        if self.expectativa < self.piso:
            return round(self.piso - self.expectativa, 4)
        return 0.0


def expectativa_12_meses(
    obs: Iterable[Observacao],
    *,
    data: str,
    indicador: str = "IPCA",
    base_calculo: int = BASE_30_DIAS,
    meta: float = META_INFLACAO,
    banda: float = BANDA_META,
) -> Meta12Meses | None:
    """A expectativa de 12 meses na data, posicionada contra a banda."""
    for o in obs:
        if (
            o.data == data
            and o.indicador == indicador
            and o.horizonte == HORIZONTE_12M
            and o.referencia == REFERENCIA_12M
            and o.base_calculo == base_calculo
            and o.mediana is not None
        ):
            return Meta12Meses(
                data=o.data,
                expectativa=o.mediana,
                desvio=round(o.mediana - meta, 4),
                piso=round(meta - banda, 4),
                teto=round(meta + banda, 4),
                desvio_padrao=o.desvio_padrao,
                n_respondentes=o.n_respondentes,
            )
    return None


def serie_12_meses(
    obs: Iterable[Observacao],
    *,
    indicador: str = "IPCA",
    base_calculo: int = BASE_30_DIAS,
    desde: str | None = None,
) -> list[Ponto]:
    """Trajetória da expectativa de 12 meses — uma marca por semana."""
    return amostrar_semanal(
        trajetoria(
            obs,
            indicador=indicador,
            referencia=REFERENCIA_12M,
            horizonte=HORIZONTE_12M,
            base_calculo=base_calculo,
            desde=desde,
        )
    )


# ── Dispersão ───────────────────────────────────────────────────────────


#: Reexportados de `api`, que é onde mora a definição única do CV.
#:
#: O defeito que isto corrige: o resultado primário de 2030 tinha média de
#: 0,0556% do PIB e desvio-padrão de 0,5705, o que dava CV de 1.026% — nove das
#: dez primeiras linhas da tabela de dispersão eram esse artefato, e o IPCA
#: aparecia na 35ª posição de 75. A justificativa empírica do limiar está no
#: docstring de `api.RAZAO_MINIMA_PARA_CV`.
RAZAO_MINIMA_PARA_CV = api.RAZAO_MINIMA_PARA_CV


@dataclass(frozen=True)
class Dispersao:
    indicador: str
    referencia: str
    media: float | None
    desvio_padrao: float | None
    minimo: float | None
    maximo: float | None
    n_respondentes: int | None
    #: Desvio-padrão da mesma chave há quatro semanas, quando disponível.
    desvio_padrao_4s: float | None = None

    @property
    def unidade(self) -> str:
        return familia(self.indicador)

    @property
    def coeficiente_variacao(self) -> float | None:
        """CV, **ou ``None`` quando a média não sustenta a divisão**."""
        return api.coeficiente_variacao(self.desvio_padrao, self.media)

    @property
    def variacao_desvio(self) -> float | None:
        """Quanto o desvio-padrão se abriu (ou fechou) em quatro semanas.

        É o número que faltava para a leitura que o painel já prometia em
        texto: *dispersão em alta com mediana estável indica a distribuição se
        abrindo antes de a mediana se mover*. Sem ele a tabela era um retrato
        estático e a frase, uma promessa que o artefato não cumpria.
        """
        if self.desvio_padrao is None or self.desvio_padrao_4s is None:
            return None
        return round(self.desvio_padrao - self.desvio_padrao_4s, 4)

    @property
    def amplitude_total(self) -> float | None:
        if self.minimo is None or self.maximo is None:
            return None
        return round(self.maximo - self.minimo, 4)


def dispersao(
    obs: Iterable[Observacao],
    *,
    data: str,
    horizonte: str = "anual",
    base_calculo: int = BASE_30_DIAS,
) -> list[Dispersao]:
    """Medidas de discordância entre analistas na data indicada.

    Só a API traz desvio-padrão, mínimo e máximo; registros vindos do PDF
    devolvem ``None`` nesses campos, e a interface deve exibir "—" em vez de
    inventar valor.
    """
    observacoes = list(obs)
    no_horizonte = [
        o for o in observacoes if o.horizonte == horizonte and o.base_calculo == base_calculo
    ]

    # Desvio-padrão de quatro semanas atrás, pela mesma regra de casamento de
    # data que as revisões usam: alvo no calendário, tolerância para feriado.
    datas = sorted({o.data for o in no_horizonte})
    referencia_4s = _data_mais_proxima(datas, _para_data(data) - timedelta(weeks=4))
    antes = {
        (o.indicador, o.referencia): o.desvio_padrao
        for o in no_horizonte
        if o.data == referencia_4s
    }

    resultado = [
        Dispersao(
            indicador=o.indicador,
            referencia=o.referencia,
            media=o.media,
            desvio_padrao=o.desvio_padrao,
            minimo=o.minimo,
            maximo=o.maximo,
            n_respondentes=o.n_respondentes,
            desvio_padrao_4s=antes.get((o.indicador, o.referencia)),
        )
        for o in no_horizonte
        if o.data == data
    ]
    resultado.sort(key=lambda d: (d.indicador, d.referencia))
    return resultado
