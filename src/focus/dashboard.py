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
from . import calendario
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


def _secao_trajetoria(obs: Sequence[Observacao], revs: Sequence[an.Revisao]) -> str:
    anos = sorted(
        {r.referencia for r in revs if r.horizonte == "anual" and r.referencia.isdigit()}
    )[:4]
    if not anos:
        return ""

    corte = sorted({o.data for o in obs})[-52:]
    desde = corte[0] if corte else None

    series = [
        Serie(
            nome=ano,
            cor=CORES_SERIE[i % len(CORES_SERIE)],
            pontos=[
                (p.data, p.valor)
                for p in an.trajetoria(obs, indicador="IPCA", referencia=ano, desde=desde)
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
            "Mediana por ano de referência, edição a edição. A linha tracejada é o "
            f"centro da meta contínua ({num(an.META_INFLACAO)}%)."
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

    itens.sort(key=lambda d: -(d.coeficiente_variacao or 0))
    linhas = [
        (
            d.indicador,
            d.referencia,
            num(d.media) if d.media is not None else "—",
            num(d.desvio_padrao) if d.desvio_padrao is not None else "—",
            f"{num(d.minimo)} – {num(d.maximo)}"
            if d.minimo is not None and d.maximo is not None
            else "—",
            f"{num((d.coeficiente_variacao or 0) * 100, 1)}%"
            if d.coeficiente_variacao is not None
            else "—",
            str(d.n_respondentes) if d.n_respondentes else "—",
        )
        for d in itens[:24]
    ]
    tabela = _tabela(
        "t-dispersao",
        ("Indicador", "Ano", "Média", "Desvio-padrão", "Mín – Máx", "CV", "Resp."),
        linhas,
        legenda="Ver dispersão entre analistas",
    )
    return (
        '<section class="secao"><h2>Dispersão entre analistas</h2>'
        '<p class="nota">Ordenado pelo coeficiente de variação (desvio-padrão sobre a '
        "média), que torna a discordância comparável entre indicadores de escalas "
        "diferentes. Dispersão em alta com mediana estável indica distribuição se "
        "abrindo antes de a mediana se mover.</p>"
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

    # O selo compara a edição que temos com a que já deveria existir, e não com
    # a data de hoje. O Focus é semanal e o boletim é nomeado pela sexta de
    # coleta: a edição corrente chega normalmente a dez dias de idade antes de
    # a próxima sair. Com o limiar fixo de 8 dias que havia aqui, o painel
    # público exibia "9 dias sem atualização" em vermelho todo fim de semana,
    # com o pipeline rigorosamente em dia — foi o que aconteceu em 20/09/2026.
    if calendario.esta_atrasado(data, hoje):
        idade = (hoje - datetime.strptime(data, "%Y-%m-%d").date()).days
        esperada = calendario.edicao_esperada(hoje).isoformat()
        selo = (
            f'<span class="selo alerta">Dados de {_rotulo_data_extensa(data)} — '
            f"{idade} dias sem atualização; a edição de "
            f"{_rotulo_data_extensa(esperada)} já deveria estar publicada</span>"
        )
    else:
        selo = f'<span class="selo">Dados de {_rotulo_data_extensa(data)}</span>'

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
