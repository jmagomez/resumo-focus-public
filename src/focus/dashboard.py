"""Dashboard estático do Boletim Focus — um único HTML autocontido.

Substitui o dashboard Streamlit, que exigia servidor em execução, tinha os anos
de referência fixos no código e não mostrava histórico. Este arquivo é gerado
pelo pipeline, versionado em ``docs/`` e servido pelo GitHub Pages: abre em
qualquer navegador, sem back-end, sem rede e sem dependência de CDN.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from pathlib import Path

from . import analytics as an
from .charts import (
    CORES_SERIE,
    JS_INTERACAO,
    PALETA_CSS,
    Barra,
    Cartao,
    Serie,
    esc,
    grafico_barras_divergente,
    grafico_linhas,
    num,
    num_sinal,
    render_cartoes,
)
from .parser import UNIDADES
from .store import Observacao

log = logging.getLogger(__name__)

DESTINO_PADRAO = Path("docs/index.html")

#: Indicadores em destaque no topo, com a unidade e o sentido "alta é ruim".
_DESTAQUE = (
    ("IPCA", "%", True),
    ("Selic", "% a.a.", True),
    ("Câmbio", "R$/US$", True),
    ("PIB", "%", False),
)

_CSS = """
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--surface);
  color: var(--texto);
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.viz { min-height: 100vh; padding-block: 28px; background: var(--surface); }
.envelope { max-width: 900px; margin: 0 auto; padding-inline: 16px; }
header.topo { border-bottom: 1px solid var(--borda); padding-bottom: 18px; margin-bottom: 26px; }
header.topo h1 { margin: 0 0 4px; font-size: 26px; letter-spacing: -.02em; }
header.topo .sub { margin: 0; color: var(--texto-2); font-size: 14px; }
.selo {
  display: inline-flex; align-items: center; gap: 6px; margin-top: 12px;
  padding: 3px 10px; border-radius: 999px; font-size: 12.5px; font-weight: 600;
  border: 1px solid var(--borda); color: var(--texto-2); background: var(--surface-alt);
}
.selo.alerta { color: var(--critico); border-color: var(--critico); }
.cartoes {
  display: grid; gap: 12px; margin-bottom: 30px;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
}
.cartao {
  border: 1px solid var(--borda); border-radius: 10px; padding: 14px 16px;
  background: var(--surface-alt);
}
.cartao h3 { margin: 0 0 6px; font-size: 12.5px; font-weight: 600; color: var(--texto-2);
  text-transform: uppercase; letter-spacing: .04em; }
.cartao .valor { margin: 0; font-size: 30px; font-weight: 650; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums; }
.cartao .valor small { font-size: 13px; font-weight: 500; color: var(--texto-3); margin-left: 5px; }
.delta { display: inline-block; margin-top: 4px; font-size: 13px; font-weight: 600;
  font-variant-numeric: tabular-nums; }
.delta.bom { color: var(--bom); }
.delta.ruim { color: var(--critico); }
.delta.neutro { color: var(--texto-3); }
.faisca { display: block; margin-top: 8px; width: 104px; height: 26px; }
.nota { margin: 6px 0 0; font-size: 12.5px; color: var(--texto-3); }
.nota.alerta-texto { color: var(--critico); font-weight: 600; }
.figura { margin: 0 0 32px; }
.figura figcaption h3 { margin: 0 0 2px; font-size: 17px; letter-spacing: -.01em; }
.figura figcaption p { margin: 0 0 10px; color: var(--texto-2); font-size: 13.5px; }
.legenda { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 8px; font-size: 12.5px;
  color: var(--texto-2); }
.item-legenda { display: inline-flex; align-items: center; gap: 6px; }
.item-legenda i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.area-grafico { position: relative; overflow-x: auto; }
.grafico { width: 100%; height: auto; display: block; min-width: 460px; }
text.eixo { fill: var(--texto-3); font-size: 11px; font-variant-numeric: tabular-nums; }
text.eixo-ref { fill: var(--texto-3); font-size: 11px; font-weight: 600; }
text.rotulo-serie { font-size: 11.5px; font-weight: 600; font-variant-numeric: tabular-nums; }
text.rotulo-barra { fill: var(--texto-2); font-size: 12px; }
text.valor-barra { fill: var(--texto-2); font-size: 11.5px; font-weight: 600;
  font-variant-numeric: tabular-nums; }
text.valor-barra.dentro { fill: #ffffff; }
.barra { cursor: default; }
.tooltip {
  position: absolute; pointer-events: none; z-index: 5; max-width: 260px;
  background: var(--surface); border: 1px solid var(--borda); border-radius: 8px;
  padding: 7px 10px; font-size: 12.5px; line-height: 1.45; color: var(--texto);
  box-shadow: 0 6px 20px rgba(0,0,0,.14); font-variant-numeric: tabular-nums;
}
.tooltip strong { display: block; margin-bottom: 3px; }
.tooltip span { display: block; color: var(--texto-2); }
button.alternar {
  border: 1px solid var(--borda); background: var(--surface-alt); color: var(--texto-2);
  border-radius: 7px; padding: 5px 11px; font-size: 12.5px; cursor: pointer; font: inherit;
  font-size: 12.5px;
}
button.alternar:hover { color: var(--texto); }
table { border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 10px;
  font-variant-numeric: tabular-nums; }
th, td { text-align: right; padding: 6px 9px; border-bottom: 1px solid var(--borda); }
th:first-child, td:first-child { text-align: left; }
thead th { color: var(--texto-2); font-weight: 600; font-size: 12px;
  text-transform: uppercase; letter-spacing: .03em; }
tbody tr:hover { background: var(--surface-alt); }
.secao { margin-bottom: 36px; }
.secao > h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em;
  color: var(--texto-3); margin: 0 0 14px; padding-bottom: 6px;
  border-bottom: 1px solid var(--borda); }
footer { margin-top: 40px; padding-top: 18px; border-top: 1px solid var(--borda);
  color: var(--texto-3); font-size: 12.5px; }
footer a { color: inherit; }
@media (max-width: 640px) {
  .cartao .valor { font-size: 25px; }
  header.topo h1 { font-size: 21px; }
}
"""


def _rotulo_data(iso: str) -> str:
    d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    return f"{d.day:02d}/{d.month:02d}"


def _rotulo_data_extensa(iso: str) -> str:
    meses = (
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    )
    d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    return f"{d.day} de {meses[d.month - 1]} de {d.year}"


#: Nomes longos encurtados para caber na margem do gráfico de barras. O nome
#: completo continua na tabela e no tooltip — abreviar é decisão de layout,
#: nunca de conteúdo.
_ABREVIACAO = {
    "Investimento direto no país": "Inv. direto no país",
    "IPCA Administrados": "IPCA Administr.",
    "Balança comercial": "Balança com.",
    "Resultado primário": "Result. primário",
    "Resultado nominal": "Result. nominal",
}


def _curto(nome: str) -> str:
    return _ABREVIACAO.get(nome, nome)


def _ano_corrente(refs: Iterable[str]) -> str | None:
    anos = sorted(r for r in refs if r.isdigit() and len(r) == 4)
    return anos[0] if anos else None


def _tabela(
    id_tabela: str,
    cabecalho: Sequence[str],
    linhas: Sequence[Sequence[str]],
    *,
    legenda: str = "Ver dados em tabela",
) -> str:
    cabecalho_html = "".join(f"<th scope=col>{esc(c)}</th>" for c in cabecalho)
    corpo = "".join(
        "<tr>" + "".join(f"<td>{esc(celula)}</td>" for celula in linha) + "</tr>"
        for linha in linhas
    )
    return (
        f'<button class="alternar" type="button" aria-expanded="false" '
        f'data-alvo-tabela="{esc(id_tabela)}">{esc(legenda)}</button>'
        f'<div id="{esc(id_tabela)}" hidden><table>'
        f"<thead><tr>{cabecalho_html}</tr></thead><tbody>{corpo}</tbody></table></div>"
    )


# ── Seções ─────────────────────────────────────────────────────────────────


def _cartoes(obs: Sequence[Observacao], data: str, revs: Sequence[an.Revisao]) -> str:
    ano = _ano_corrente(r.referencia for r in revs if r.horizonte == "anual")
    if ano is None:
        return ""

    por_indicador = {r.indicador: r for r in revs if r.horizonte == "anual" and r.referencia == ano}

    cartoes: list[Cartao] = []
    for nome, unidade, alta_ruim in _DESTAQUE:
        rev = por_indicador.get(nome)
        if rev is None:
            continue
        serie = an.trajetoria(obs, indicador=nome, referencia=ano)[-16:]
        cartoes.append(
            Cartao(
                titulo=f"{nome} · {ano}",
                valor=num(rev.atual, 2),
                unidade=unidade,
                delta=rev.delta_1s,
                delta_unidade="p.p." if unidade != "R$/US$" else "R$",
                nota=(
                    f"{rev.n_respondentes} respondentes"
                    if rev.n_respondentes
                    else "mediana agregada"
                ),
                inverter_cor=alta_ruim,
                faiscas=[p.valor for p in serie],
            )
        )
    return render_cartoes(cartoes)


def _secao_revisoes(revs: Sequence[an.Revisao], data: str) -> str:
    anuais = [r for r in revs if r.horizonte == "anual"]
    com_movimento = [r for r in anuais if r.delta_1s]
    if not com_movimento:
        return ""

    #  Um gráfico por família de unidade: revisão em p.p. e revisão em US$ bi
    #  não dividem eixo. Misturá-las colocaria a balança comercial, medida em
    #  dezenas de bilhões, permanentemente no topo do ranking.
    graficos: list[str] = []
    notas_curtas: list[str] = []
    for unidade, grupo in an.por_familia(com_movimento):
        grupo = sorted(grupo, key=lambda r: -abs(r.delta_1s or 0))[:10]
        barras = sorted(
            (
                Barra(
                    rotulo=f"{_curto(r.indicador)} · {r.referencia}",
                    valor=r.delta_1s or 0.0,
                    detalhe=(
                        f"de {num(r.ha_1_semana or 0)} para {num(r.atual)} "
                        f"{UNIDADES.get(r.indicador, '')}".strip()
                        + (
                            ""
                            if r.comparacao_exata
                            else f" · comparado com a edição de {_rotulo_data(r.data_1_semana or '')}"
                        )
                    ),
                )
                for r in grupo
            ),
            key=lambda b: b.valor,
        )
        rotulo_familia = {
            "p.p.": "juros, inflação e atividade",
            "R$": "câmbio",
            "US$ bi": "contas externas",
        }.get(unidade, unidade)

        # Menos de três barras não justifica um gráfico: uma frase informa
        # melhor e ocupa menos espaço do que um eixo com uma marca só.
        if len(barras) < 3:
            itens = "; ".join(f"{b.rotulo}: {num_sinal(b.valor)} {unidade}" for b in barras)
            notas_curtas.append(
                f"<strong>{esc(rotulo_familia.capitalize())}</strong> — {esc(itens)}."
            )
            continue

        graficos.append(
            grafico_barras_divergente(
                barras,
                id_grafico=f"g-revisoes-{len(graficos)}",
                titulo=f"Revisões da semana — {rotulo_familia}",
                subtitulo=(
                    f"Variação da mediana em {unidade} contra a edição anterior. "
                    "A cor indica a direção da revisão, não juízo sobre o cenário."
                ),
                unidade=unidade,
            )
        )

    inexatas = {r.data_1_semana for r in anuais if r.data_1_semana and not r.comparacao_exata}
    if inexatas:
        notas_curtas.append(
            "A edição imediatamente anterior não está no histórico; a comparação "
            "semanal usa a edição de " + ", ".join(sorted(_rotulo_data(d) for d in inexatas)) + "."
        )
    nota = "".join(f'<p class="nota">{item}</p>' for item in notas_curtas)

    tabela = _tabela(
        "t-revisoes",
        ("Indicador", "Ano", "Unid.", "Hoje", "1 sem.", "4 sem.", "13 sem.", "Resp."),
        [
            (
                r.indicador,
                r.referencia,
                r.unidade,
                num(r.atual),
                num_sinal(r.delta_1s) if r.delta_1s is not None else "—",
                num_sinal(r.delta_4s) if r.delta_4s is not None else "—",
                num_sinal(r.delta_13s) if r.delta_13s is not None else "—",
                str(r.n_respondentes) if r.n_respondentes else "—",
            )
            for r in sorted(anuais, key=lambda r: (r.indicador, r.referencia))
        ],
    )
    return f'<section class="secao"><h2>Revisões</h2>{"".join(graficos)}{nota}{tabela}</section>'


#: Janela dos gráficos de série temporal, em **semanas de calendário**.
#:
#: Dois anos, que é exatamente o que `api.sincronizar` coleta. Encurtar para um
#: ano foi cogitado por legibilidade e medido antes de ser descartado — os
#: números dizem que a janela curta destrói informação nos dois gráficos:
#:
#: *Meta contínua.* Em 104 semanas a série vai de 3,92% a 5,87% e passa 36
#: semanas acima do teto da banda, a primeira em 06/12/2024. Em 52 semanas o
#: máximo cai para 4,65% e sobram 4 semanas acima. A janela curta faria a
#: expectativa parecer estar furando o teto pela primeira vez, quando na
#: verdade é uma **volta** — para quem acompanha política monetária, é outra
#: história.
#:
#: *Trajetória.* O IPCA de 2029 só entra na pesquisa em 01/2025: em 52 semanas
#: sua amplitude é **0,00** — uma reta morta ocupando uma das quatro cores. Em
#: 104 semanas ela é 0,50.
#:
#: A densidade não é problema: são ~105 marcas em 760 px de largura, e é linha,
#: não marcador.
JANELA_SEMANAS = 104


def _secao_meta_continua(obs: Sequence[Observacao], data: str) -> str:
    """A expectativa de 12 meses contra a banda — o número que a meta avalia.

    Esta seção vem primeiro entre os gráficos porque, desde janeiro de 2025, é
    ela que o CMN afere: mês a mês, sobre o IPCA acumulado em doze meses. As
    seções por ano-calendário que vêm depois são úteis, mas nenhuma delas é o
    número que a meta contínua olha.

    A série estava no histórico desde que o terceiro endpoint foi ligado, com
    504 pontos e desvio-padrão, e o painel não a desenhava em lugar nenhum.
    """
    leitura = an.expectativa_12_meses(obs, data=data)
    if leitura is None:
        return ""

    pontos = an.serie_12_meses(obs, desde=an.desde_semanas(obs, JANELA_SEMANAS))
    if len(pontos) < 2:
        return ""

    grafico = grafico_linhas(
        [
            Serie(
                nome="IPCA 12 meses", cor=CORES_SERIE[0], pontos=[(p.data, p.valor) for p in pontos]
            )
        ],
        id_grafico="g-meta-12m",
        titulo="Expectativa de IPCA para os próximos 12 meses",
        subtitulo=(
            "Mediana suavizada da pesquisa Focus, uma marca por semana. A faixa é a "
            f"banda da meta contínua ({num(leitura.piso)}% a {num(leitura.teto)}%) e a "
            f"linha tracejada, o centro ({num(an.META_INFLACAO)}%). É sobre este "
            "horizonte — e não sobre o ano-calendário — que a meta é avaliada."
        ),
        unidade="%",
        banda=(leitura.piso, leitura.teto),
        linha_referencia=(an.META_INFLACAO, "meta"),
        altura=300,
        rotulo_x=_rotulo_data,
    )

    if leitura.dentro_da_banda:
        veredito = (
            f"A expectativa está <strong>{esc(leitura.situacao)}</strong>, a "
            f"{num_sinal(leitura.desvio)} p.p. do centro."
        )
        classe = "nota"
    else:
        veredito = (
            f"A expectativa está <strong>{esc(leitura.situacao)}</strong>: "
            f"{num(leitura.expectativa)}% contra um teto de {num(leitura.teto)}%, "
            f"um excesso de {num(leitura.excesso)} p.p."
        )
        classe = "nota alerta-texto"

    dispersao_txt = (
        f" Desvio-padrão entre os {leitura.n_respondentes} respondentes: "
        f"{num(leitura.desvio_padrao)} p.p."
        if leitura.desvio_padrao is not None and leitura.n_respondentes
        else ""
    )

    return (
        '<section class="secao"><h2>Meta contínua</h2>'
        f"{grafico}"
        f'<p class="{classe}">{veredito}{esc(dispersao_txt)}</p>'
        "</section>"
    )


def _secao_trajetoria(obs: Sequence[Observacao], revs: Sequence[an.Revisao]) -> str:
    anos = sorted(
        {r.referencia for r in revs if r.horizonte == "anual" and r.referencia.isdigit()}
    )[:4]
    if not anos:
        return ""

    # A janela é de CALENDÁRIO, nunca de contagem de datas disponíveis.
    #
    # Aqui havia `sorted({o.data for o in obs})[-52:]`, escrito como se o
    # histórico fosse semanal. Ele é diário: 505 datas em dois anos, das quais
    # 101 são sextas. O gráfico rotulado como um ano cobria 72 dias corridos —
    # o projeto baixava 730 dias de história e desenhava 72.
    desde = an.desde_semanas(obs, JANELA_SEMANAS)

    series = [
        Serie(
            nome=ano,
            cor=CORES_SERIE[i % len(CORES_SERIE)],
            pontos=[
                (p.data, p.valor)
                for p in an.amostrar_semanal(
                    an.trajetoria(obs, indicador="IPCA", referencia=ano, desde=desde)
                )
            ],
        )
        for i, ano in enumerate(anos)
    ]
    series = [s for s in series if s.pontos]
    if not series:
        return ""

    grafico = grafico_linhas(
        series,
        id_grafico="g-trajetoria",
        titulo="Trajetória das expectativas de IPCA",
        subtitulo=(
            f"Mediana por ano de referência, uma marca por semana, {JANELA_SEMANAS // 52} "
            "anos de história. A linha tracejada é o centro da meta contínua "
            f"({num(an.META_INFLACAO)}%)."
        ),
        unidade="%",
        linha_referencia=(an.META_INFLACAO, "meta"),
        altura=320,
        rotulo_x=_rotulo_data,
    )
    return f'<section class="secao"><h2>Trajetória</h2>{grafico}</section>'


def _secao_ancoragem(obs: Sequence[Observacao], data: str) -> str:
    pontos = an.ancoragem(obs, data=data)
    pontos = [p for p in pontos if p.referencia.isdigit()]
    if len(pontos) < 2:
        return ""

    serie = Serie(
        nome="IPCA",
        cor=CORES_SERIE[0],
        pontos=[(p.referencia, p.expectativa) for p in pontos],
    )
    grafico = grafico_linhas(
        [serie],
        id_grafico="g-ancoragem",
        titulo="Ancoragem — expectativa de IPCA por horizonte",
        subtitulo=(
            f"Meta contínua de {num(an.META_INFLACAO)}% com banda de "
            f"±{num(an.BANDA_META, 1)} p.p. Convergência ao centro nos anos longos é a "
            "medida de credibilidade; o ano corrente já está largamente determinado."
        ),
        unidade="%",
        banda=(an.META_INFLACAO - an.BANDA_META, an.META_INFLACAO + an.BANDA_META),
        linha_referencia=(an.META_INFLACAO, "meta"),
        altura=260,
    )
    tabela = _tabela(
        "t-ancoragem",
        ("Ano", "Expectativa (%)", "Desvio do centro (p.p.)", "Situação"),
        [(p.referencia, num(p.expectativa), num_sinal(p.desvio), p.situacao) for p in pontos],
    )
    return f'<section class="secao"><h2>Ancoragem</h2>{grafico}{tabela}</section>'


def _secao_gap(revs: Sequence[an.Revisao]) -> str:
    com_gap = [
        r
        for r in revs
        if r.horizonte == "anual" and r.gap_5d not in (None, 0.0) and r.unidade == "p.p."
    ]
    com_gap.sort(key=lambda r: -abs(r.gap_5d or 0))
    selecionadas = com_gap[:10]
    if not selecionadas:
        return ""

    barras = sorted(
        (
            Barra(
                rotulo=f"{_curto(r.indicador)} · {r.referencia}",
                valor=r.gap_5d or 0.0,
                detalhe=f"mediana de 30 dias: {num(r.atual)}",
            )
            for r in selecionadas
        ),
        key=lambda b: b.valor,
    )
    grafico = grafico_barras_divergente(
        barras,
        id_grafico="g-gap",
        titulo="Gap entre a base de 5 dias úteis e a de 30 dias",
        subtitulo=(
            "Apenas indicadores medidos em p.p. A base curta incorpora informação "
            "nova antes da mediana cheia; gap do mesmo sinal por várias semanas "
            "costuma anteceder a revisão da mediana."
        ),
        unidade="p.p.",
    )
    return f'<section class="secao"><h2>Indicador antecedente</h2>{grafico}</section>'


def _secao_dispersao(obs: Sequence[Observacao], data: str) -> str:
    itens = [
        d
        for d in an.dispersao(obs, data=data)
        if d.desvio_padrao is not None and d.referencia.isdigit()
    ]
    if not itens:
        return (
            '<section class="secao"><h2>Dispersão</h2>'
            '<p class="nota">Dispersão disponível apenas para semanas coletadas pela API '
            "de Expectativas do BCB — as edições lidas somente do PDF não trazem "
            "desvio-padrão, mínimo e máximo.</p></section>"
        )

    # Ordenar por CV era o defeito: o CV explode quando a média se aproxima de
    # zero, e as nove primeiras linhas da tabela eram "Resultado primário" —
    # média de 0,0556% do PIB, CV de 1.026% — enquanto o IPCA caía para a 35ª
    # posição de 75. Não era discordância grande; era denominador pequeno.
    #
    # A ordenação continua sendo por CV, porque o CV é a única medida aqui que
    # é adimensional e, por isso, a única que pode ordenar indicadores de
    # escalas diferentes sem violar a regra de não misturar unidades. O que
    # mudou é o domínio: só entram no ranking as linhas em que o CV está
    # definido. As demais não somem — vão para o fim, com o desvio-padrão na
    # unidade original, que é a informação honesta sobre elas.
    com_cv = sorted(
        (d for d in itens if d.coeficiente_variacao is not None),
        key=lambda d: -(d.coeficiente_variacao or 0.0),
    )
    sem_cv = sorted(
        (d for d in itens if d.coeficiente_variacao is None),
        key=lambda d: (d.indicador, d.referencia),
    )

    def _linha(d: an.Dispersao) -> tuple[str, ...]:
        return (
            d.indicador,
            d.referencia,
            d.unidade,
            num(d.media) if d.media is not None else "—",
            num(d.desvio_padrao) if d.desvio_padrao is not None else "—",
            # Três casas: a variação do desvio-padrão é pequena por natureza, e
            # com duas casas metade da coluna saía como "-0,00".
            num_sinal(d.variacao_desvio, 3) if d.variacao_desvio is not None else "—",
            f"{num(d.minimo)} – {num(d.maximo)}"
            if d.minimo is not None and d.maximo is not None
            else "—",
            f"{num((d.coeficiente_variacao or 0) * 100, 1)}%"
            if d.coeficiente_variacao is not None
            else "—",
            str(d.n_respondentes) if d.n_respondentes else "—",
        )

    tabela = _tabela(
        "t-dispersao",
        (
            "Indicador",
            "Ano",
            "Unid.",
            "Média",
            "Desvio-padrão",
            "Δ 4 sem.",
            "Mín – Máx",
            "CV",
            "Resp.",
        ),
        [_linha(d) for d in (*com_cv[:20], *sem_cv[:8])],
        legenda="Ver dispersão entre analistas",
    )

    abrindo = [d for d in com_cv if (d.variacao_desvio or 0) > 0]
    resumo_abertura = (
        f"Nesta edição, {len(abrindo)} de {len(com_cv)} distribuições se abriram em quatro semanas."
        if com_cv
        else ""
    )
    nota_cv = (
        f" O CV fica em branco em {len(sem_cv)} linhas: são indicadores cuja média "
        "cruza o zero — resultado primário, resultado nominal, conta corrente — e "
        "para os quais a divisão pela média não mede discordância, só a "
        "proximidade do denominador a zero. Nessas linhas, leia o desvio-padrão na "
        "unidade da coluna."
        if sem_cv
        else ""
    )
    return (
        '<section class="secao"><h2>Dispersão entre analistas</h2>'
        '<p class="nota">Ordenado pelo coeficiente de variação (desvio-padrão sobre a '
        "média), única medida adimensional da tabela e, por isso, a única que "
        f"compara indicadores de escalas diferentes.{esc(nota_cv)}</p>"
        '<p class="nota">A coluna <strong>Δ 4 sem.</strong> é a variação do próprio '
        "desvio-padrão: dispersão em alta com mediana estável indica a distribuição "
        f"se abrindo antes de a mediana se mover. {esc(resumo_abertura)}</p>"
        f"{tabela}</section>"
    )


# ── Montagem ───────────────────────────────────────────────────────────────


def construir(
    obs: Sequence[Observacao],
    *,
    destino: Path | str = DESTINO_PADRAO,
    hoje: date | None = None,
) -> Path:
    """Gera o dashboard a partir do histórico e grava em ``destino``."""
    observacoes = list(obs)
    if not observacoes:
        raise ValueError(
            "Histórico vazio: rode `python -m focus sincronizar` antes de gerar o dashboard."
        )

    data = an.ultima_data(observacoes)
    assert data is not None
    revs = an.revisoes(observacoes, data=data)
    hoje = hoje or date.today()

    idade = (hoje - datetime.strptime(data, "%Y-%m-%d").date()).days
    if idade <= 8:
        selo = f'<span class="selo">Dados de {_rotulo_data_extensa(data)}</span>'
    else:
        selo = (
            f'<span class="selo alerta">Dados de {_rotulo_data_extensa(data)} — '
            f"{idade} dias sem atualização</span>"
        )

    amplitudes = an.amplitude([r for r in revs if r.horizonte == "anual"])
    resumo_amplitude = ", ".join(
        f"{a.indicador} {a.subiram}↑/{a.cairam}↓" for a in amplitudes if a.subiram or a.cairam
    )

    corpo = "".join(
        [
            '<div class="viz"><div class="envelope">',
            "<header class=topo>",
            "<h1>Boletim Focus — expectativas de mercado</h1>",
            '<p class="sub">Banco Central do Brasil · pesquisa Focus · '
            "medianas agregadas e dispersão entre respondentes</p>",
            selo,
            "</header>",
            _cartoes(observacoes, data, revs),
            _secao_meta_continua(observacoes, data),
            _secao_revisoes(revs, data),
            _secao_trajetoria(observacoes, revs),
            _secao_ancoragem(observacoes, data),
            _secao_gap(revs),
            _secao_dispersao(observacoes, data),
            "<footer>",
            f"<p><strong>Amplitude das revisões nesta edição:</strong> "
            f"{esc(resumo_amplitude or 'sem revisões')}.</p>",
            "<p>Fonte primária: "
            '<a href="https://dadosabertos.bcb.gov.br/dataset/expectativas-mercado">'
            "API de Expectativas de Mercado do Banco Central</a>; o PDF do "
            '<a href="https://www.bcb.gov.br/publicacoes/focus">Focus — Relatório de '
            "Mercado</a> é arquivado como prova documental. Nenhum valor desta página "
            "é estimado, interpolado ou arredondado além das casas publicadas pelo "
            "BCB.</p>",
            f"<p>Gerado em {esc(hoje.strftime('%d/%m/%Y'))} · {len(observacoes):,}".replace(
                ",", "."
            )
            + " observações no histórico.</p>",
            "</footer></div></div>",
        ]
    )

    pagina = (
        "<!DOCTYPE html>\n"
        '<html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Boletim Focus — expectativas de mercado</title>"
        '<meta name="color-scheme" content="light dark">'
        f"<style>{PALETA_CSS}{_CSS}</style></head><body>"
        f"{corpo}"
        f"<script>{JS_INTERACAO}</script>"
        "</body></html>\n"
    )

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(pagina, encoding="utf-8")
    log.info("Dashboard gerado: %s (%.0f KB)", destino, destino.stat().st_size / 1024)
    return destino
