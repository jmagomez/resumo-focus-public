"""HTML do e-mail semanal do Boletim Focus.

Separação de responsabilidades que a versão anterior não tinha: **o agente
escreve a prosa; o código escreve os números.** Antes, o agente redigia a
tabela HTML à mão, e é daí que vinham dois defeitos no material publicado:

* a seta ▲/▼ aparecia na coluna "Sem. passada", sugerindo que o movimento tinha
  acontecido na semana anterior, quando descreve a variação até hoje;
* a cor era atribuída por direção, não por significado — IPCA em queda saía em
  vermelho, embora recuo de inflação seja leitura favorável.

Aqui a tabela é montada a partir do histórico já validado, e a cor segue o
sentido econômico do indicador (ver ``analytics.ALTA_E_DESFAVORAVEL``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import analytics as an
from .charts import esc, num, num_sinal
from .parser import UNIDADES

MARCA = "#282f6b"
VERDE = "#0b7a3b"
VERMELHO = "#b3261e"
CINZA = "#6b7280"
BORDA = "#d9d9e3"

LOGO = "https://analisemacro.com.br/wp-content/uploads/dlm_uploads/2021/10/logo_an.png"

_MESES = (
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


@dataclass(frozen=True)
class Prosa:
    """O texto escrito pelo agente, separado dos números."""

    resumo: str
    revisoes: list[str]

    @classmethod
    def de_markdown(cls, texto: str) -> Prosa:
        """Lê o Markdown produzido pelo agente.

        Formato esperado: um parágrafo de resumo, depois uma lista com as
        principais revisões::

            O Focus de ... a mediana do IPCA para 2026 recuou para "4,90" ...

            - Selic (2026): 14,00 → 13,75. Hipótese: ...
            - IPCA (2026): 5,00 → 4,90. Hipótese: ...
        """
        linhas = texto.strip().splitlines()
        resumo: list[str] = []
        revisoes: list[str] = []
        for linha in linhas:
            despida = linha.strip()
            if not despida or despida.startswith("#"):
                continue
            if despida.startswith(("- ", "* ", "• ")):
                revisoes.append(despida[2:].strip())
            elif not revisoes:
                resumo.append(despida)
        return cls(resumo=" ".join(resumo).strip(), revisoes=revisoes)


def _data_extensa(iso: str) -> str:
    d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    return f"{d.day} de {_MESES[d.month - 1]} de {d.year}"


def _cor_do_movimento(indicador: str, delta: float | None) -> tuple[str, str]:
    """Devolve ``(seta, cor)`` segundo o **sentido econômico** do indicador."""
    if delta is None or delta == 0:
        return "→", CINZA
    subiu = delta > 0
    desfavoravel = subiu if indicador in an.ALTA_E_DESFAVORAVEL else not subiu
    return ("▲" if subiu else "▼"), (VERMELHO if desfavoravel else VERDE)


def _celula(conteudo: str, *, alinhamento: str = "center", extra: str = "") -> str:
    return (
        f'<td style="border:1px solid {BORDA};padding:7px 9px;'
        f'text-align:{alinhamento};font-size:13px;{extra}">{conteudo}</td>'
    )


def _quadro(revs: Sequence[an.Revisao], anos: Sequence[str]) -> str:
    """Quadro-resumo: mediana de hoje, variação na semana e seta junto do valor."""
    por_chave = {(r.indicador, r.referencia): r for r in revs if r.horizonte == "anual"}
    indicadores = [n for n, _, _ in _ORDEM_QUADRO if any((n, a) in por_chave for a in anos)]
    if not indicadores:
        return ""

    cabecalho = "".join(
        f'<th colspan="2" style="border:1px solid {BORDA};padding:7px 9px;'
        f'font-size:12px;color:{MARCA};">{esc(ano)}</th>'
        for ano in anos
    )
    subcabecalho = "".join(
        f'<th style="border:1px solid {BORDA};padding:5px 9px;font-size:11px;'
        f'font-weight:600;color:{CINZA};">{rotulo}</th>'
        for _ in anos
        for rotulo in ("Hoje", "Δ semana")
    )

    linhas: list[str] = []
    for nome in indicadores:
        unidade = UNIDADES.get(nome, "")
        celulas = [
            _celula(
                f"{esc(nome)}"
                + (
                    f' <span style="color:{CINZA};font-size:11px;">({esc(unidade)})</span>'
                    if unidade
                    else ""
                ),
                alinhamento="left",
            )
        ]
        for ano in anos:
            rev = por_chave.get((nome, ano))
            if rev is None:
                celulas.append(_celula("—"))
                celulas.append(_celula("—"))
                continue
            seta, cor = _cor_do_movimento(nome, rev.delta_1s)
            celulas.append(
                _celula(
                    f"<strong>{esc(num(rev.atual))}</strong> "
                    f'<span style="color:{cor};">{seta}</span>',
                )
            )
            celulas.append(
                _celula(
                    f'<span style="color:{cor};font-size:12px;">'
                    + (esc(num_sinal(rev.delta_1s)) if rev.delta_1s is not None else "—")
                    + "</span>"
                )
            )
        linhas.append("<tr>" + "".join(celulas) + "</tr>")

    return (
        f'<table role="presentation" style="border-collapse:collapse;width:100%;'
        f'margin:6px 0 18px;">'
        f'<tr><th style="border:1px solid {BORDA};padding:7px 9px;"></th>{cabecalho}</tr>'
        f'<tr><th style="border:1px solid {BORDA};padding:5px 9px;"></th>{subcabecalho}</tr>'
        + "".join(linhas)
        + "</table>"
    )


_ORDEM_QUADRO = (
    ("IPCA", "%", True),
    ("Selic", "% a.a.", True),
    ("Câmbio", "R$/US$", True),
    ("PIB", "%", False),
    ("IGP-M", "%", True),
    ("IPCA Administrados", "%", True),
    ("Resultado primário", "% do PIB", False),
    ("DLSP", "% do PIB", True),
)


def construir(
    revs: Sequence[an.Revisao],
    prosa: Prosa,
    *,
    data: str,
    url_dashboard: str | None = None,
) -> str:
    """Monta o HTML completo do e-mail."""
    anos = sorted(
        {r.referencia for r in revs if r.horizonte == "anual" and r.referencia.isdigit()}
    )[:3]

    itens_revisao = (
        "".join(f'<li style="margin-bottom:6px;">{esc(item)}</li>' for item in prosa.revisoes)
        or '<li style="color:#6b7280;">Sem revisões relevantes nesta edição.</li>'
    )

    rodape_dashboard = (
        f'<p style="margin:18px 0 0;font-size:13px;">'
        f'<a href="{esc(url_dashboard)}" style="color:{MARCA};">'
        f"Abrir o painel interativo com histórico e dispersão</a></p>"
        if url_dashboard
        else ""
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="pt-BR"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Focus {esc(data)}</title></head>"
        '<body style="margin:0;background:#f6f6f8;">'
        '<table role="presentation" width="100%" style="border-collapse:collapse;'
        'background:#f6f6f8;"><tr><td align="center" style="padding:24px 12px;">'
        '<table role="presentation" width="680" style="max-width:680px;width:100%;'
        "border-collapse:collapse;background:#ffffff;border-radius:10px;"
        'font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;">'
        '<tr><td style="padding:26px 28px;">'
        f'<img src="{LOGO}" alt="Análise Macro" style="height:44px;margin-bottom:14px;">'
        f'<h1 style="color:{MARCA};font-size:22px;margin:0 0 2px;">'
        f"Boletim Focus — {esc(_data_extensa(data))}</h1>"
        f'<p style="color:{CINZA};font-size:13px;margin:0 0 18px;">'
        "Expectativas de mercado · Banco Central do Brasil</p>"
        f'<p style="font-size:14.5px;line-height:1.6;margin:0 0 20px;">'
        f"{esc(prosa.resumo)}</p>"
        f'<h2 style="color:{MARCA};font-size:16px;margin:0 0 4px;">Quadro-resumo</h2>'
        f'<p style="color:{CINZA};font-size:12px;margin:0 0 4px;">'
        "A seta acompanha a mediana de hoje e indica a variação contra a edição "
        "anterior. Verde é leitura favorável ao cenário; vermelho, desfavorável.</p>"
        f"{_quadro(revs, anos)}"
        f'<h2 style="color:{MARCA};font-size:16px;margin:20px 0 8px;">'
        "Principais revisões da semana</h2>"
        f'<ul style="font-size:14px;line-height:1.55;margin:0;padding-left:20px;">'
        f"{itens_revisao}</ul>"
        f"{rodape_dashboard}"
        f'<p style="color:{CINZA};font-size:11.5px;margin:22px 0 0;'
        f'border-top:1px solid {BORDA};padding-top:12px;">'
        "Valores reproduzidos literalmente da pesquisa Focus do Banco Central. "
        "Nenhum número é estimado, interpolado ou arredondado além das casas "
        "publicadas pelo BCB.</p>"
        "</td></tr></table></td></tr></table></body></html>\n"
    )


def texto_alternativo(html: str) -> str:
    """Fallback em texto puro para clientes que não renderizam HTML."""
    sem_tags = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    sem_tags = re.sub(r"<br\s*/?>|</p>|</li>|</h[12]>", "\n", sem_tags, flags=re.I)
    sem_tags = re.sub(r"<[^>]+>", " ", sem_tags)
    sem_tags = re.sub(r"[ \t]+", " ", sem_tags)
    sem_tags = re.sub(r"\n\s*\n+", "\n\n", sem_tags)
    return sem_tags.strip()


def carregar_prosa(caminho: Path | str) -> Prosa:
    return Prosa.de_markdown(Path(caminho).read_text(encoding="utf-8"))
