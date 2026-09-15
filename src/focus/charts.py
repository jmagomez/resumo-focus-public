"""Gráficos SVG gerados em Python, sem dependência externa em tempo de execução.

O dashboard precisa abrir daqui a dois anos, offline, a partir de um único
arquivo. Isso descarta CDN e biblioteca de runtime: os gráficos são SVG escrito
no servidor, e a interatividade é uma camada de JavaScript de poucas linhas que
lê atributos ``data-*`` já presentes na marcação.

Decisões de codificação visual (e por que):

* **Eixo único, sempre.** Nunca dois eixos y no mesmo gráfico — duas escalas
  diferentes viram duas figuras ou uma série indexada.
* **Paleta categórica de ordem fixa**, nunca ciclada; identidade nunca é só
  cor — toda série com legenda e, até quatro séries, rótulo direto na ponta.
* **Divergente para polaridade**: revisão para cima × para baixo usa dois polos
  (vermelho/azul) com cinza neutro no meio, e a legenda diz explicitamente que
  a cor codifica **direção**, não juízo de valor.
* **Marcas finas, grade recessiva**, rótulo numérico seletivo — nunca em todos
  os pontos.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

# ── Paleta (validada para deficiência de visão de cores em ambos os modos) ────

PALETA_CSS = """
:root, .viz {
  --surface:        #fcfcfb;
  --surface-alt:    #f4f3f0;
  --borda:          #e2e0da;
  --texto:          #0b0b0b;
  --texto-2:        #52514e;
  --texto-3:        #77756e;
  --grade:          #e6e4de;
  --serie-1:        #2a78d6;
  --serie-2:        #eb6834;
  --serie-3:        #1baf7a;
  --serie-4:        #eda100;
  --pos:            #d03b3b;
  --neg:            #2a78d6;
  --neutro:         #cfcdc6;
  --bom:            #0ca30c;
  --critico:        #d03b3b;
  --banda:          rgba(42,120,214,.10);
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])), :root:where(:not([data-theme="light"])) .viz {
    --surface:      #1a1a19;
    --surface-alt:  #232321;
    --borda:        #383835;
    --texto:        #ffffff;
    --texto-2:      #c3c2b7;
    --texto-3:      #96948b;
    --grade:        #2f2f2c;
    --serie-1:      #3987e5;
    --serie-2:      #d95926;
    --serie-3:      #199e70;
    --serie-4:      #c98500;
    --pos:          #e66767;
    --neg:          #3987e5;
    --neutro:       #4a4a46;
    --bom:          #0ca30c;
    --critico:      #d03b3b;
    --banda:        rgba(57,135,229,.16);
  }
}
:root[data-theme="dark"], :root[data-theme="dark"] .viz {
  --surface:        #1a1a19;
  --surface-alt:    #232321;
  --borda:          #383835;
  --texto:          #ffffff;
  --texto-2:        #c3c2b7;
  --texto-3:        #96948b;
  --grade:          #2f2f2c;
  --serie-1:        #3987e5;
  --serie-2:        #d95926;
  --serie-3:        #199e70;
  --serie-4:        #c98500;
  --pos:            #e66767;
  --neg:            #3987e5;
  --neutro:         #4a4a46;
  --bom:            #0ca30c;
  --critico:        #d03b3b;
  --banda:          rgba(57,135,229,.16);
}
"""

CORES_SERIE = ("var(--serie-1)", "var(--serie-2)", "var(--serie-3)", "var(--serie-4)")


def esc(texto: object) -> str:
    return html.escape(str(texto), quote=True)


#: Separadores usados dentro de atributos ``data-*`` para o tooltip.
#: São caracteres de controle justamente porque nunca aparecem em texto do BCB.
# Escritos com chr() de propósito. A forma com escape unicode no literal
# sobrevive mal a ferramentas que reinterpretam escapes no caminho até o
# repositório: o separador chega vazio, e o tooltip inteiro colapsa numa
# linha só — sem erro nenhum, que é o pior modo de falha possível.
SEP_TITULO = chr(0x1F)  # separa o título do corpo do tooltip
SEP_ITEM = chr(0x1E)  # separa as linhas do corpo
ESPACO_FINO = chr(0x2009)  # espaço fino entre nome da série e valor


def num(valor: float, casas: int = 2) -> str:
    """Formata no padrão brasileiro: ponto de milhar, vírgula decimal."""
    inteiro_com_virgula = f"{valor:,.{casas}f}"
    return inteiro_com_virgula.translate(str.maketrans({",": ".", ".": ","}))


def num_sinal(valor: float, casas: int = 2) -> str:
    return ("+" if valor > 0 else "") + num(valor, casas)


# ── Escala ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Escala:
    d0: float
    d1: float
    r0: float
    r1: float

    def __call__(self, valor: float) -> float:
        if self.d1 == self.d0:
            return (self.r0 + self.r1) / 2
        return self.r0 + (valor - self.d0) / (self.d1 - self.d0) * (self.r1 - self.r0)


def _passo_agradavel(bruto: float) -> float:
    """Arredonda um intervalo para o próximo passo 1 / 2 / 2,5 / 5 × 10ⁿ."""
    import math

    if bruto <= 0:
        return 1.0
    expoente = math.floor(math.log10(bruto))
    base = 10.0**expoente
    for multiplo in (1, 2, 2.5, 5, 10):
        if bruto <= base * multiplo * 1.0000001:
            return base * multiplo
    return base * 10


def _ticks(minimo: float, maximo: float, alvo: int = 5) -> list[float]:
    """Marcas de eixo em passos '1-2-5' — legíveis, nunca em passo arbitrário.

    Devolve sempre pelo menos três marcas: um eixo com duas linhas de grade
    obriga o leitor a interpolar de cabeça.
    """
    import math

    if maximo <= minimo:
        margem = abs(minimo) * 0.1 or 1.0
        minimo, maximo = minimo - margem, maximo + margem

    for divisor in (alvo - 1, alvo, alvo + 2):
        passo = _passo_agradavel((maximo - minimo) / max(divisor, 1))
        inicio = math.floor(minimo / passo) * passo
        marcas: list[float] = []
        valor = inicio
        while valor <= maximo + passo * 1e-9:
            if valor >= minimo - passo * 1e-9:
                marcas.append(round(valor, 10))
            valor += passo
        if len(marcas) >= 3:
            return marcas
    return marcas or [minimo, (minimo + maximo) / 2, maximo]


# ── Gráfico de linhas ─────────────────────────────────────────────────────────


@dataclass
class Serie:
    nome: str
    #: ``(chave, valor)``. A **chave** é o que ordena o eixo x — use sempre uma
    #: forma ordenável lexicograficamente (ISO ``2026-09-11``, ou o ano). O
    #: rótulo exibido sai de ``rotulo_x``. Ordenar pelo texto já formatado
    #: ("11/09") embaralharia a série por dia do mês.
    pontos: list[tuple[str, float]]
    cor: str = CORES_SERIE[0]


def grafico_linhas(
    series: Sequence[Serie],
    *,
    id_grafico: str,
    titulo: str,
    subtitulo: str = "",
    unidade: str = "",
    altura: int = 300,
    largura: int = 760,
    banda: tuple[float, float] | None = None,
    linha_referencia: tuple[float, str] | None = None,
    casas: int = 2,
    rotulo_x: Callable[[str], str] = str,
) -> str:
    """Linha múltipla com crosshair e tooltip, legenda e rótulo direto na ponta."""
    if not series or not any(s.pontos for s in series):
        return _vazio(titulo, "sem dados para o período")

    eixo_x: list[str] = []
    for serie in series:
        for rotulo, _ in serie.pontos:
            if rotulo not in eixo_x:
                eixo_x.append(rotulo)
    eixo_x.sort()
    posicao = {rotulo: i for i, rotulo in enumerate(eixo_x)}

    valores = [v for s in series for _, v in s.pontos]
    if banda:
        valores += list(banda)
    if linha_referencia:
        valores.append(linha_referencia[0])
    v_min, v_max = min(valores), max(valores)
    folga = (v_max - v_min) * 0.12 or max(abs(v_max), 1) * 0.05
    marcas = _ticks(v_min - folga, v_max + folga)

    m_esq, m_dir, m_topo, m_base = 54, 96, 16, 34
    px = Escala(0, max(len(eixo_x) - 1, 1), m_esq, largura - m_dir)
    py = Escala(marcas[0], marcas[-1], altura - m_base, m_topo)

    partes: list[str] = [
        f'<svg class="grafico" id="{esc(id_grafico)}" viewBox="0 0 {largura} {altura}" '
        f'role="img" aria-label="{esc(titulo)}" preserveAspectRatio="xMidYMid meet">'
    ]

    if banda:
        # Clampada à área de plotagem: uma faixa que transborda para baixo do
        # eixo sugere que a banda continua fora do gráfico.
        topo_banda = max(min(py(banda[1]), altura - m_base), m_topo)
        base_banda = max(min(py(banda[0]), altura - m_base), m_topo)
        partes.append(
            f'<rect x="{m_esq}" y="{topo_banda:.1f}" width="{largura - m_dir - m_esq}" '
            f'height="{abs(base_banda - topo_banda):.1f}" fill="var(--banda)"/>'
        )

    for marca in marcas:
        y = py(marca)
        partes.append(
            f'<line x1="{m_esq}" y1="{y:.1f}" x2="{largura - m_dir}" y2="{y:.1f}" '
            f'stroke="var(--grade)" stroke-width="1"/>'
        )
        partes.append(
            f'<text x="{m_esq - 8}" y="{y + 3.5:.1f}" text-anchor="end" '
            f'class="eixo">{esc(num(marca, casas))}</text>'
        )

    if linha_referencia:
        valor, rotulo = linha_referencia
        y = py(valor)
        partes.append(
            f'<line x1="{m_esq}" y1="{y:.1f}" x2="{largura - m_dir}" y2="{y:.1f}" '
            f'stroke="var(--texto-3)" stroke-width="1.5" stroke-dasharray="5 4"/>'
        )
        partes.append(
            f'<text x="{largura - m_dir + 6}" y="{y + 3.5:.1f}" class="eixo-ref">'
            f"{esc(rotulo)}</text>"
        )

    passo_rotulo = max(1, len(eixo_x) // 8)
    for i, chave in enumerate(eixo_x):
        if i % passo_rotulo and i != len(eixo_x) - 1:
            continue
        ancora = "middle"
        if i == 0:
            ancora = "start"
        elif i == len(eixo_x) - 1:
            ancora = "end"
        partes.append(
            f'<text x="{px(i):.1f}" y="{altura - m_base + 18}" text-anchor="{ancora}" '
            f'class="eixo">{esc(rotulo_x(chave))}</text>'
        )

    for serie in series:
        pontos = sorted(serie.pontos, key=lambda p: p[0])
        if not pontos:
            continue
        caminho = " ".join(
            f"{'M' if i == 0 else 'L'}{px(posicao[r]):.1f},{py(v):.1f}"
            for i, (r, v) in enumerate(pontos)
        )
        partes.append(
            f'<path d="{caminho}" fill="none" stroke="{serie.cor}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        rotulo_final, valor_final = pontos[-1]
        cx, cy = px(posicao[rotulo_final]), py(valor_final)
        partes.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{serie.cor}" '
            f'stroke="var(--surface)" stroke-width="2"/>'
        )
        partes.append(
            f'<text x="{cx + 10:.1f}" y="{cy + 4:.1f}" class="rotulo-serie" '
            f'fill="{serie.cor}">{esc(serie.nome)} {esc(num(valor_final, casas))}</text>'
        )

    # Faixas invisíveis de captura para o crosshair — alvo maior que a marca.
    dados_hover: list[str] = []
    for chave in eixo_x:
        itens = []
        for serie in series:
            valor = dict(serie.pontos).get(chave)
            if valor is not None:
                itens.append(f"{serie.nome}{ESPACO_FINO}{num(valor, casas)}{unidade}")
        dados_hover.append(esc(rotulo_x(chave) + SEP_TITULO + SEP_ITEM.join(itens)))

    largura_faixa = (largura - m_dir - m_esq) / max(len(eixo_x), 1)
    partes.append(f'<g class="captura" data-pontos="{"|".join(dados_hover)}">')
    partes.append(
        f'<line class="crosshair" x1="0" y1="{m_topo}" x2="0" y2="{altura - m_base}" '
        f'stroke="var(--texto-3)" stroke-width="1" opacity="0"/>'
    )
    for i in range(len(eixo_x)):
        partes.append(
            f'<rect x="{px(i) - largura_faixa / 2:.1f}" y="{m_topo}" '
            f'width="{largura_faixa:.1f}" height="{altura - m_base - m_topo}" '
            f'fill="transparent" data-i="{i}" data-x="{px(i):.1f}"/>'
        )
    partes.append("</g></svg>")

    legenda = "".join(
        f'<span class="item-legenda"><i style="background:{s.cor}"></i>{esc(s.nome)}</span>'
        for s in series
    )

    return (
        f'<figure class="figura">'
        f"<figcaption><h3>{esc(titulo)}</h3>"
        f"{f'<p>{esc(subtitulo)}</p>' if subtitulo else ''}</figcaption>"
        f'<div class="legenda">{legenda}</div>'
        f'<div class="area-grafico">{"".join(partes)}'
        f'<div class="tooltip" hidden></div></div>'
        f"</figure>"
    )


# ── Barras divergentes ────────────────────────────────────────────────────────


@dataclass
class Barra:
    rotulo: str
    valor: float
    detalhe: str = ""


def grafico_barras_divergente(
    barras: Sequence[Barra],
    *,
    id_grafico: str,
    titulo: str,
    subtitulo: str = "",
    unidade: str = "p.p.",
    casas: int = 2,
    largura: int = 760,
) -> str:
    """Barras horizontais em torno do zero, com rótulo direto em cada barra."""
    barras = [b for b in barras if b.valor is not None]
    if not barras:
        return _vazio(titulo, "nenhuma revisão nesta edição")

    altura_barra, espaco = 22, 8
    m_esq, m_dir, m_topo = 204, 76, 12
    altura = m_topo + len(barras) * (altura_barra + espaco) + 26

    extremo = max(abs(b.valor) for b in barras) or 1.0
    px = Escala(-extremo * 1.18, extremo * 1.18, m_esq, largura - m_dir)
    zero = px(0)
    #: Abaixo desta largura o rótulo numérico não cabe dentro da barra.
    largura_minima_interna = 52.0

    partes = [
        f'<svg class="grafico" id="{esc(id_grafico)}" viewBox="0 0 {largura} {altura}" '
        f'role="img" aria-label="{esc(titulo)}" preserveAspectRatio="xMidYMid meet">'
    ]
    partes.append(
        f'<line x1="{zero:.1f}" y1="{m_topo}" x2="{zero:.1f}" '
        f'y2="{altura - 26}" stroke="var(--neutro)" stroke-width="1.5"/>'
    )

    for i, barra in enumerate(barras):
        y = m_topo + i * (altura_barra + espaco)
        x = px(barra.valor)
        cor = "var(--pos)" if barra.valor > 0 else "var(--neg)"
        detalhe_tip = esc(SEP_ITEM + barra.detalhe) if barra.detalhe else ""
        inicio, comprimento = (min(zero, x), abs(x - zero))
        # Gap de 2px contra a linha de zero para as barras não se colarem nela.
        if barra.valor >= 0:
            inicio += 2
        comprimento = max(comprimento - 2, 1)

        partes.append(
            f'<rect x="{inicio:.1f}" y="{y}" width="{comprimento:.1f}" '
            f'height="{altura_barra}" rx="4" fill="{cor}" class="barra" '
            f'data-tip="{esc(barra.rotulo)}{SEP_TITULO}'
            f'{esc(num_sinal(barra.valor, casas))} {esc(unidade)}{detalhe_tip}"/>'
        )
        partes.append(
            f'<text x="{m_esq - 12}" y="{y + altura_barra / 2 + 4:.0f}" '
            f'text-anchor="end" class="rotulo-barra">{esc(barra.rotulo)}</text>'
        )

        # O rótulo do valor vai FORA da barra quando há espaço na margem, e
        # DENTRO quando a barra é longa o bastante. Sem essa distinção, uma
        # barra que ocupa toda a metade do gráfico empurra o número para cima
        # do nome do indicador do outro lado do eixo.
        positivo = barra.valor >= 0
        if comprimento >= largura_minima_interna:
            x_texto = (x - 8) if positivo else (x + 8)
            ancora = "end" if positivo else "start"
            classe = "valor-barra dentro"
        else:
            x_texto = (x + 8) if positivo else (x - 8)
            ancora = "start" if positivo else "end"
            classe = "valor-barra"
        partes.append(
            f'<text x="{x_texto:.1f}" y="{y + altura_barra / 2 + 4:.0f}" '
            f'text-anchor="{ancora}" class="{classe}">'
            f"{esc(num_sinal(barra.valor, casas))}</text>"
        )

    partes.append(
        f'<text x="{zero:.1f}" y="{altura - 8}" text-anchor="middle" class="eixo">0</text>'
    )
    partes.append("</svg>")

    legenda = (
        '<span class="item-legenda"><i style="background:var(--pos)"></i>'
        "revisado para cima</span>"
        '<span class="item-legenda"><i style="background:var(--neg)"></i>'
        "revisado para baixo</span>"
    )

    return (
        f'<figure class="figura">'
        f"<figcaption><h3>{esc(titulo)}</h3>"
        f"{f'<p>{esc(subtitulo)}</p>' if subtitulo else ''}</figcaption>"
        f'<div class="legenda">{legenda}</div>'
        f'<div class="area-grafico">{"".join(partes)}'
        f'<div class="tooltip" hidden></div></div>'
        f"</figure>"
    )


# ── Cartões ───────────────────────────────────────────────────────────────────


@dataclass
class Cartao:
    titulo: str
    valor: str
    unidade: str = ""
    delta: float | None = None
    delta_unidade: str = "p.p."
    nota: str = ""
    inverter_cor: bool = False
    faiscas: list[float] = field(default_factory=list)


def _faisca(valores: Sequence[float], largura: int = 104, altura: int = 26) -> str:
    """Sparkline: a forma certa para 'tendência' num cartão — sem eixo, sem rótulo."""
    if len(valores) < 2:
        return ""
    v_min, v_max = min(valores), max(valores)
    px = Escala(0, len(valores) - 1, 1, largura - 1)
    py = Escala(v_min, v_max, altura - 3, 3)
    caminho = " ".join(
        f"{'M' if i == 0 else 'L'}{px(i):.1f},{py(v):.1f}" for i, v in enumerate(valores)
    )
    return (
        f'<svg class="faisca" viewBox="0 0 {largura} {altura}" aria-hidden="true">'
        f'<path d="{caminho}" fill="none" stroke="var(--texto-3)" stroke-width="1.5" '
        f'stroke-linejoin="round"/>'
        f'<circle cx="{px(len(valores) - 1):.1f}" cy="{py(valores[-1]):.1f}" r="2.5" '
        f'fill="var(--texto-2)"/></svg>'
    )


def render_cartoes(cartoes: Sequence[Cartao]) -> str:
    saida: list[str] = ['<div class="cartoes">']
    for c in cartoes:
        if c.delta is None or c.delta == 0:
            classe, seta = "neutro", "→"
        else:
            subiu = c.delta > 0
            favoravel = (not subiu) if c.inverter_cor else subiu
            classe = "bom" if favoravel else "ruim"
            seta = "▲" if subiu else "▼"
        delta_txt = (
            f'<span class="delta {classe}"><span aria-hidden="true">{seta}</span> '
            f"{esc(num_sinal(c.delta, 2))} {esc(c.delta_unidade)}</span>"
            if c.delta is not None
            else '<span class="delta neutro">sem comparação</span>'
        )
        saida.append(
            f'<article class="cartao">'
            f"<h3>{esc(c.titulo)}</h3>"
            f'<p class="valor">{esc(c.valor)}<small>{esc(c.unidade)}</small></p>'
            f"{delta_txt}"
            f"{_faisca(c.faiscas)}"
            f"{f'<p class=nota>{esc(c.nota)}</p>' if c.nota else ''}"
            f"</article>"
        )
    saida.append("</div>")
    return "".join(saida)


def _vazio(titulo: str, motivo: str) -> str:
    return (
        f'<figure class="figura vazia"><figcaption><h3>{esc(titulo)}</h3></figcaption>'
        f'<p class="nota">{esc(motivo)}</p></figure>'
    )


# ── Interatividade ────────────────────────────────────────────────────────────

JS_INTERACAO = r"""
(function () {
  var SEP = String.fromCharCode(31), ITEM = String.fromCharCode(30);

  function posiciona(tip, area, evt) {
    var caixa = area.getBoundingClientRect();
    var x = evt.clientX - caixa.left, y = evt.clientY - caixa.top;
    tip.style.left = Math.min(Math.max(x + 14, 4), caixa.width - tip.offsetWidth - 4) + 'px';
    tip.style.top = Math.max(y - tip.offsetHeight - 12, 4) + 'px';
  }

  function conteudo(bruto) {
    var partes = bruto.split(SEP);
    var corpo = (partes[1] || '').split(ITEM)
      .filter(Boolean)
      .map(function (linha) { return '<span>' + linha + '</span>'; })
      .join('');
    return '<strong>' + partes[0] + '</strong>' + corpo;
  }

  document.querySelectorAll('.area-grafico').forEach(function (area) {
    var tip = area.querySelector('.tooltip');
    if (!tip) return;

    var captura = area.querySelector('.captura');
    if (captura) {
      var pontos = (captura.dataset.pontos || '').split('|');
      var cross = captura.querySelector('.crosshair');
      captura.querySelectorAll('rect').forEach(function (faixa) {
        faixa.addEventListener('pointerenter', function (evt) {
          var i = +faixa.dataset.i;
          if (cross) {
            cross.setAttribute('x1', faixa.dataset.x);
            cross.setAttribute('x2', faixa.dataset.x);
            cross.setAttribute('opacity', '1');
          }
          tip.innerHTML = conteudo(pontos[i] || '');
          tip.hidden = false;
          posiciona(tip, area, evt);
        });
        faixa.addEventListener('pointermove', function (evt) { posiciona(tip, area, evt); });
      });
      area.addEventListener('pointerleave', function () {
        tip.hidden = true;
        if (cross) cross.setAttribute('opacity', '0');
      });
    }

    area.querySelectorAll('[data-tip]').forEach(function (marca) {
      marca.addEventListener('pointerenter', function (evt) {
        tip.innerHTML = conteudo(marca.dataset.tip);
        tip.hidden = false;
        posiciona(tip, area, evt);
      });
      marca.addEventListener('pointermove', function (evt) { posiciona(tip, area, evt); });
      marca.addEventListener('pointerleave', function () { tip.hidden = true; });
    });
  });

  document.querySelectorAll('[data-alvo-tabela]').forEach(function (botao) {
    botao.addEventListener('click', function () {
      var alvo = document.getElementById(botao.dataset.alvoTabela);
      if (!alvo) return;
      alvo.hidden = !alvo.hidden;
      botao.setAttribute('aria-expanded', String(!alvo.hidden));
      botao.textContent = alvo.hidden ? 'Ver dados em tabela' : 'Ocultar tabela';
    });
  });
})();
"""
