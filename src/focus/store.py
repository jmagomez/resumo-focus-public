"""Histórico longitudinal das expectativas, em CSV de formato longo.

Esta é a lacuna estrutural que o projeto tinha: cada semana era lida e
descartada. Sem histórico não há revisão, não há trajetória de expectativa e
não há dispersão ao longo do tempo — que é justamente o uso analítico do Focus.

O arquivo é **append-only e idempotente**: a chave
``(data, indicador, horizonte, referencia, base_calculo)`` é única, e reprocessar
o mesmo boletim não duplica nem altera linha. Quando o mesmo registro chega pelo
PDF e pela API, a API vence — ela traz dispersão e número de respondentes.

Formato longo (uma observação por linha) em vez de largo porque o conjunto de
períodos de referência muda a cada mês, e tabela larga com colunas móveis é
exatamente a estrutura que produziu o bug de rótulo defasado.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from .api import BASE_5_DIAS_UTEIS, BASE_30_DIAS, Expectativa
from .parser import Boletim, Tabela

log = logging.getLogger(__name__)

CAMINHO_PADRAO = Path("data/history/expectativas.csv")

COLUNAS: tuple[str, ...] = (
    "data",
    "indicador",
    "horizonte",
    "referencia",
    "base_calculo",
    "mediana",
    "media",
    "desvio_padrao",
    "minimo",
    "maximo",
    "n_respondentes",
    "fonte",
)

CHAVE = ("data", "indicador", "horizonte", "referencia", "base_calculo")

FONTE_API = "api"
FONTE_PDF = "pdf"

#: Precedência de fonte: quem tiver o número maior vence em caso de conflito.
_PRECEDENCIA = {FONTE_PDF: 0, FONTE_API: 1}


@dataclass(frozen=True)
class Observacao:
    """Uma linha do histórico."""

    data: str
    indicador: str
    horizonte: str
    referencia: str
    base_calculo: int
    mediana: float | None
    media: float | None = None
    desvio_padrao: float | None = None
    minimo: float | None = None
    maximo: float | None = None
    n_respondentes: int | None = None
    fonte: str = FONTE_API

    @property
    def chave(self) -> tuple:
        return (
            self.data,
            self.indicador,
            self.horizonte,
            self.referencia,
            int(self.base_calculo),
        )


# ── Conversões ────────────────────────────────────────────────────────────────


def de_api(registros: Iterable[Expectativa]) -> list[Observacao]:
    return [
        Observacao(
            data=r.data,
            indicador=r.indicador,
            horizonte=r.horizonte,
            referencia=r.referencia,
            base_calculo=r.base_calculo,
            mediana=r.mediana,
            media=r.media,
            desvio_padrao=r.desvio_padrao,
            minimo=r.minimo,
            maximo=r.maximo,
            n_respondentes=r.n_respondentes,
            fonte=FONTE_API,
        )
        for r in registros
    ]


def _do_quadro(tabela: Tabela, data: str) -> Iterator[Observacao]:
    for nome, indicador in tabela.indicadores.items():
        for periodo, celula in indicador.celulas.items():
            if celula.hoje.numero is not None:
                yield Observacao(
                    data=data,
                    indicador=nome,
                    horizonte=tabela.horizonte,
                    referencia=periodo,
                    base_calculo=BASE_30_DIAS,
                    mediana=celula.hoje.numero,
                    n_respondentes=celula.respondentes,
                    fonte=FONTE_PDF,
                )
            if celula.cinco_dias_uteis.numero is not None:
                yield Observacao(
                    data=data,
                    indicador=nome,
                    horizonte=tabela.horizonte,
                    referencia=periodo,
                    base_calculo=BASE_5_DIAS_UTEIS,
                    mediana=celula.cinco_dias_uteis.numero,
                    n_respondentes=celula.respondentes_5d,
                    fonte=FONTE_PDF,
                )


def de_boletim(boletim: Boletim) -> list[Observacao]:
    """Converte um boletim lido do PDF em observações do histórico.

    Serve de rede de segurança: se a API estiver fora do ar, a semana ainda
    entra no histórico — com menos colunas (sem dispersão), marcada como
    ``fonte=pdf``, e substituível depois pelo registro da API.
    """
    data = boletim.data_iso
    return list(_do_quadro(boletim.anual, data)) + list(_do_quadro(boletim.mensal, data))


# ── Leitura e escrita ─────────────────────────────────────────────────────────


def _para_float(texto: str) -> float | None:
    texto = (texto or "").strip()
    if texto in {"", "NA", "None"}:
        return None
    return float(texto)


def _para_int(texto: str) -> int | None:
    valor = _para_float(texto)
    return None if valor is None else int(valor)


def carregar(caminho: Path | str = CAMINHO_PADRAO) -> list[Observacao]:
    """Lê o histórico. Arquivo inexistente devolve lista vazia."""
    caminho = Path(caminho)
    if not caminho.exists():
        return []

    with caminho.open(encoding="utf-8", newline="") as fh:
        leitor = csv.DictReader(fh)
        faltando = set(COLUNAS) - set(leitor.fieldnames or [])
        if faltando:
            raise ValueError(
                f"{caminho} não tem a(s) coluna(s) {sorted(faltando)}. "
                "Arquivo de histórico incompatível."
            )
        return [
            Observacao(
                data=linha["data"],
                indicador=linha["indicador"],
                horizonte=linha["horizonte"],
                referencia=linha["referencia"],
                base_calculo=int(linha["base_calculo"]),
                mediana=_para_float(linha["mediana"]),
                media=_para_float(linha["media"]),
                desvio_padrao=_para_float(linha["desvio_padrao"]),
                minimo=_para_float(linha["minimo"]),
                maximo=_para_float(linha["maximo"]),
                n_respondentes=_para_int(linha["n_respondentes"]),
                fonte=linha["fonte"],
            )
            for linha in leitor
        ]


def _formatar(valor: float | int | None) -> str:
    if valor is None:
        return ""
    if isinstance(valor, int):
        return str(valor)
    return f"{valor:.6g}"


def gravar(observacoes: Sequence[Observacao], caminho: Path | str = CAMINHO_PADRAO) -> Path:
    """Grava o histórico ordenado. Sobrescreve o arquivo inteiro."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    ordenadas = sorted(observacoes, key=lambda o: o.chave)
    with caminho.open("w", encoding="utf-8", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=COLUNAS, lineterminator="\n")
        escritor.writeheader()
        for obs in ordenadas:
            linha = asdict(obs)
            for campo in ("mediana", "media", "desvio_padrao", "minimo", "maximo"):
                linha[campo] = _formatar(linha[campo])
            linha["n_respondentes"] = _formatar(linha["n_respondentes"])
            escritor.writerow(linha)

    log.info("Histórico gravado: %s (%d linhas)", caminho, len(ordenadas))
    return caminho


@dataclass(frozen=True)
class ResultadoMerge:
    novas: int
    atualizadas: int
    inalteradas: int
    total: int

    def __str__(self) -> str:
        return (
            f"{self.novas} nova(s), {self.atualizadas} atualizada(s), "
            f"{self.inalteradas} inalterada(s) — total {self.total}"
        )


def mesclar(
    novas: Iterable[Observacao],
    caminho: Path | str = CAMINHO_PADRAO,
) -> ResultadoMerge:
    """Incorpora observações ao histórico, sem duplicar e sem perder dados.

    Em conflito de chave, vence a fonte de maior precedência (API > PDF); em
    empate de fonte, vence o registro novo.
    """
    caminho = Path(caminho)
    atual = {obs.chave: obs for obs in carregar(caminho)}

    contagem = {"novas": 0, "atualizadas": 0, "inalteradas": 0}
    for obs in novas:
        existente = atual.get(obs.chave)
        if existente is None:
            atual[obs.chave] = obs
            contagem["novas"] += 1
            continue
        if _PRECEDENCIA.get(obs.fonte, 0) < _PRECEDENCIA.get(existente.fonte, 0):
            contagem["inalteradas"] += 1
            continue
        if existente == obs:
            contagem["inalteradas"] += 1
            continue
        atual[obs.chave] = obs
        contagem["atualizadas"] += 1

    gravar(list(atual.values()), caminho)
    return ResultadoMerge(total=len(atual), **contagem)
