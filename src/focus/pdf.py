"""Download do PDF do Boletim Focus e extração do texto.

Substitui os antigos módulos duplicados ``baixar_focus`` / ``downloader`` e
``extrair_texto`` / ``extractor``, que tinham comportamentos divergentes (um
validava o magic number ``%PDF``, o outro não; um reaproveitava arquivo em
disco, o outro rebaixava sempre).

Aqui existe uma implementação só, com o comportamento mais seguro de cada uma.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pdfplumber
import requests

log = logging.getLogger(__name__)

URL_BCB = "https://www.bcb.gov.br/content/focus/focus/R{}.pdf"

# O BCB publica na segunda-feira; em feriado nacional, escorrega para terça (ou
# mais adiante em feriados prolongados). Em vez de modelar o calendário de
# feriados, recuamos dia a dia — cobre os dois casos sem lógica especial.
MAX_LOOKBACK = 8

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; resumo-focus-public/2.0; "
        "+https://github.com/jmagomez/resumo-focus-public)"
    )
}

# Um PDF do Focus tem ~780 KB. Qualquer coisa muito menor é página de erro do
# portal servida com HTTP 200 — acontece, e é exatamente o tipo de resposta que
# um pipeline silencioso aceitaria como se fosse boletim.
TAMANHO_MINIMO_BYTES = 50_000


class FocusIndisponivelError(RuntimeError):
    """Nenhum PDF do Focus foi encontrado na janela de busca."""


@dataclass(frozen=True)
class BoletimBaixado:
    """Resultado de um download bem-sucedido."""

    data_publicacao: date
    caminho: Path
    ja_existia: bool

    @property
    def tamanho_kb(self) -> float:
        return self.caminho.stat().st_size / 1024


def ultima_segunda(hoje: date) -> date:
    """Segunda-feira mais recente, incluindo hoje quando hoje já é segunda."""
    return hoje - timedelta(days=hoje.weekday())


def baixar(
    destino: Path | str,
    *,
    inicio: date | None = None,
    max_lookback: int = MAX_LOOKBACK,
    session: requests.Session | None = None,
) -> BoletimBaixado:
    """Baixa o PDF mais recente do Focus em ``destino``.

    Parte de ``inicio`` (padrão: última segunda-feira) e recua dia a dia até
    encontrar um PDF válido. Reaproveita o arquivo se já estiver em disco.

    Levanta :class:`FocusIndisponivelError` se nada for encontrado — nunca
    devolve caminho de arquivo inexistente ou truncado.
    """
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    inicio = inicio or ultima_segunda(date.today())
    get = (session or requests).get

    for delta in range(max_lookback):
        candidata = inicio - timedelta(days=delta)
        caminho = destino / f"focus_{candidata.isoformat()}.pdf"

        if caminho.exists() and caminho.stat().st_size >= TAMANHO_MINIMO_BYTES:
            log.info("PDF já em disco: %s", caminho.name)
            return BoletimBaixado(candidata, caminho, ja_existia=True)

        url = URL_BCB.format(candidata.strftime("%Y%m%d"))
        log.debug("Tentando %s", url)

        try:
            resposta = get(url, headers=_HEADERS, timeout=30)
        except requests.RequestException as exc:
            log.warning("Erro de rede em %s: %s", url, exc)
            continue

        if resposta.status_code != 200:
            log.debug("HTTP %s — %s", resposta.status_code, url)
            continue

        conteudo = resposta.content

        if not conteudo.startswith(b"%PDF"):
            log.warning("Resposta 200 sem magic number %%PDF em %s — ignorada", url)
            continue

        if len(conteudo) < TAMANHO_MINIMO_BYTES:
            log.warning(
                "PDF suspeito em %s: %d bytes (mínimo %d) — ignorado",
                url,
                len(conteudo),
                TAMANHO_MINIMO_BYTES,
            )
            continue

        caminho.write_bytes(conteudo)
        log.info("Baixado: %s (%.1f KB)", caminho.name, len(conteudo) / 1024)
        return BoletimBaixado(candidata, caminho, ja_existia=False)

    raise FocusIndisponivelError(
        f"PDF do Focus não encontrado nos {max_lookback} dias a partir de {inicio}. "
        "Verifique https://www.bcb.gov.br/publicacoes/focus"
    )


def extrair_texto(pdf_path: Path | str, *, forcar: bool = False) -> Path:
    """Extrai o texto do PDF e grava um ``.txt`` com o mesmo nome-base.

    Usa ``layout=True`` porque o parser depende do alinhamento horizontal para
    localizar a linha de cabeçalho com os períodos de referência.
    """
    pdf_path = Path(pdf_path)
    destino = pdf_path.with_suffix(".txt")

    if destino.exists() and not forcar:
        log.info("Texto já extraído: %s", destino.name)
        return destino

    paginas: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for numero, pagina in enumerate(pdf.pages, 1):
            texto = pagina.extract_text(layout=True)
            if texto and texto.strip():
                paginas.append(texto.strip())
            log.debug("Página %d — %d caracteres", numero, len(texto or ""))

    if not paginas:
        raise ValueError(
            f"Nenhum texto extraído de {pdf_path.name}. "
            "O PDF pode estar corrompido ou ser uma digitalização sem camada de texto."
        )

    destino.write_text("\n\n".join(paginas), encoding="utf-8")
    log.info("Texto salvo: %s (%d páginas)", destino.name, len(paginas))
    return destino
