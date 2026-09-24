"""Interface de linha de comando do pipeline.

    python -m focus baixar          # PDF do BCB → data/
    python -m focus extrair         # PDF → .txt
    python -m focus sincronizar     # API Olinda (+ PDF como reserva) → histórico
    python -m focus dashboard       # histórico → docs/index.html
    python -m focus email           # prosa do agente + números → e-mail
    python -m focus verificar       # diagnóstico de saúde do pipeline

Todo comando devolve código de saída diferente de zero quando o passo falha,
para que o GitHub Actions interrompa a cadeia em vez de publicar dado velho.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import analytics as an
from . import api, dashboard, mail, pdf, report, store
from .parser import LayoutDesconhecidoError, parsear_arquivo

log = logging.getLogger("focus")

PASTA_DADOS = Path("data")
PASTA_SAIDA = Path("output/focus")

#: Além disso, o boletim é considerado velho e o pipeline alerta.
IDADE_MAXIMA_DIAS = 8


def _configurar_log(verboso: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verboso else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )


def _txt_mais_recente(pasta: Path | None = None) -> Path | None:
    """Último ``.txt`` da pasta de dados.

    ``pasta=None`` resolve ``PASTA_DADOS`` **na chamada**, não na importação.
    Com o valor amarrado como argumento padrão (``pasta: Path = PASTA_DADOS``),
    trocar ``focus.cli.PASTA_DADOS`` não tinha efeito nenhum: os testes de
    diagnóstico apontavam para um ``tmp_path`` e liam, sem saber, a ``data/``
    real do repositório. Passavam pelo motivo errado — a edição versionada é
    recente e parseável, então nenhuma checagem de idade chegava a disparar.
    """
    alvo = PASTA_DADOS if pasta is None else pasta
    arquivos = sorted(alvo.glob("focus_*.txt"), reverse=True)
    return arquivos[0] if arquivos else None


def _data_do_nome(caminho: Path) -> date | None:
    try:
        return datetime.strptime(caminho.stem.split("_", 1)[1], "%Y-%m-%d").date()
    except (IndexError, ValueError):
        return None


def _erro(mensagem: str) -> None:
    """Escreve em stderr, depois de esvaziar o stdout.

    Nos workflows os dois streams caem no mesmo lugar (``> relatorio.txt 2>&1``,
    ou o log do Actions). ``stdout`` tem buffer e ``stderr`` não, então sem este
    flush as linhas de erro aparecem **antes** das linhas normais que as
    precederam — e a ordem muda de uma execução para outra, conforme o buffer
    enche.

    Dois casos reais: o e-mail do vigia (run 35136532569) chegou com o
    ``[FALHA]`` no topo e a evidência embaixo; o log do envio (run 35164311085)
    mostrou ``HTML gravado:`` **depois** do traceback que o interrompeu, o que
    sugere uma ordem de eventos que não aconteceu.
    """
    sys.stdout.flush()
    print(mensagem, file=sys.stderr)


# ── Comandos ──────────────────────────────────────────────────────────────────


def cmd_baixar(args: argparse.Namespace) -> int:
    resultado = pdf.baixar(args.destino)
    print(f"{resultado.caminho}  ({resultado.tamanho_kb:.1f} KB)")
    if not args.sem_extrair:
        print(pdf.extrair_texto(resultado.caminho))
    return 0


def cmd_extrair(args: argparse.Namespace) -> int:
    caminho = args.pdf
    if caminho is None:
        pdfs = sorted(PASTA_DADOS.glob("focus_*.pdf"), reverse=True)
        if not pdfs:
            _erro("Nenhum PDF em data/. Rode antes: python -m focus baixar")
            return 1
        caminho = pdfs[0]
    print(pdf.extrair_texto(caminho, forcar=args.forcar))
    return 0


def cmd_sincronizar(args: argparse.Namespace) -> int:
    """Atualiza o histórico. A API é a fonte; o PDF é a reserva."""
    desde = date.today() - timedelta(days=args.dias)
    novas: list[store.Observacao] = []

    try:
        registros = api.sincronizar(desde=desde)
        novas = store.de_api(registros)
        log.info("API de Expectativas: %d registro(s) desde %s", len(novas), desde)
    except api.ApiExpectativasError as exc:
        log.warning("API de Expectativas indisponível (%s). Usando o PDF como reserva.", exc)
        if args.exigir_api:
            _erro(f"ERRO: {exc}")
            return 2

    txt = _txt_mais_recente()
    if txt is not None:
        try:
            novas += store.de_boletim(parsear_arquivo(txt))
        except LayoutDesconhecidoError as exc:
            log.error("Falha ao ler %s: %s", txt.name, exc)
            if not novas:
                _erro(f"ERRO: {exc}")
                return 2

    if not novas:
        _erro("ERRO: nem a API nem o PDF forneceram dados. Histórico não alterado.")
        return 2

    resultado = store.mesclar(novas, args.historico)
    print(f"Histórico: {resultado}")
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    observacoes = store.carregar(args.historico)
    if not observacoes:
        _erro("Histórico vazio. Rode antes: python -m focus sincronizar")
        return 1
    destino = dashboard.construir(observacoes, destino=args.destino)
    print(destino)
    return 0


def cmd_email(args: argparse.Namespace) -> int:
    observacoes = store.carregar(args.historico)
    if not observacoes:
        _erro("Histórico vazio. Rode antes: python -m focus sincronizar")
        return 1

    data = an.ultima_data(observacoes)
    assert data is not None

    # A prosa é obrigatória para ENVIAR e dispensável para o --dry-run.
    #
    # Não é conveniência: é o que torna a cadeia possível. O agente escreve a
    # prosa lendo os números desta saída — CLAUDE.md diz, literalmente, que
    # todo valor citado tem de aparecer em `email --dry-run`. Enquanto o
    # --dry-run exigia a prosa para rodar, o agente precisava do arquivo que
    # ele ainda ia escrever, e a etapa era impossível de cumprir. Foi assim
    # que o elo do meio nunca saiu do papel e o pipeline passou seis semanas
    # coletando sem publicar.
    caminho_prosa = args.prosa
    if caminho_prosa is None:
        candidatos = sorted(PASTA_SAIDA.glob("focus_*.md"), reverse=True)
        caminho_prosa = candidatos[0] if candidatos else None

    if caminho_prosa is None:
        prosa = report.Prosa(resumo="", revisoes=[])
    else:
        prosa = report.carregar_prosa(caminho_prosa)

    if not prosa.resumo and not args.dry_run:
        origem = caminho_prosa or "output/focus/*.md"
        _erro(
            f"ERRO: sem prosa da semana ({origem}). O agente de resumo precisa "
            "rodar antes do envio — veja `.claude/commands/gerar-resumo.md`."
        )
        return 1

    if not prosa.resumo:
        _erro(
            "AVISO: nenhuma prosa encontrada. Mostrando só os números, que é o "
            "que o agente usa para escrevê-la."
        )

    revs = an.revisoes(observacoes, data=data)
    html = report.construir(revs, prosa, data=data, url_dashboard=args.url_dashboard)
    texto = report.texto_alternativo(html)
    assunto = f"Boletim Focus — {data}"

    destino_html = PASTA_SAIDA / f"focus_{data}.html"
    destino_html.parent.mkdir(parents=True, exist_ok=True)
    destino_html.write_text(html, encoding="utf-8")
    print(f"HTML gravado: {destino_html}")

    if args.dry_run:
        print("--- DRY-RUN: e-mail não enviado ---")
        print(texto[:1200])
        return 0

    destino = mail.destino_do_ambiente(destinatarios=args.dest)
    mail.enviar(mail.montar(assunto, html, texto, destino), destino)
    return 0


def cmd_verificar(args: argparse.Namespace) -> int:
    """Diagnóstico: responde 'o pipeline está entregando?' com código de saída.

    Existe porque a falha real do projeto foi silenciosa: o download continuou
    rodando por seis semanas enquanto nenhum resumo era publicado, e o único
    alerta configurado cobria apenas a etapa de download.

    Contrato do relatório: cada assunto verificado produz **um** veredito. Um
    item que reprovou nunca aparece também como ``[ok]`` — quem lê o e-mail do
    vigia precisa poder contar os ``[ok]`` e confiar na conta.
    """
    hoje = args.hoje or date.today()
    problemas: list[str] = []
    avisos: list[str] = []
    aprovados: list[str] = []

    txt = _txt_mais_recente()
    if txt is None:
        problemas.append("Nenhum .txt em data/ — o workflow de download não rodou.")
    else:
        locais: list[str] = []
        data_txt = _data_do_nome(txt)
        if data_txt is None:
            locais.append(f"Nome de arquivo fora do padrão: {txt.name}")
        else:
            idade = (hoje - data_txt).days
            if idade > IDADE_MAXIMA_DIAS:
                locais.append(
                    f"Último boletim extraído é de {data_txt} ({idade} dias). "
                    "O download pode estar quebrado."
                )
        try:
            boletim = parsear_arquivo(txt)
            resumo_parser = (
                f"Parser: {txt.name} → anual {boletim.anual.periodos}, "
                f"mensal {boletim.mensal.periodos}"
            )
        except LayoutDesconhecidoError as exc:
            locais.append(f"Parser falhou em {txt.name}: {exc}")
            resumo_parser = None

        if locais:
            problemas.extend(locais)
        elif resumo_parser:
            aprovados.append(resumo_parser)

    observacoes = store.carregar(args.historico)
    if not observacoes:
        problemas.append("Histórico vazio — rode `python -m focus sincronizar`.")
    else:
        locais = []
        ultima = an.ultima_data(observacoes) or ""
        idade_hist = (hoje - datetime.strptime(ultima, "%Y-%m-%d").date()).days
        resumo_hist = f"Histórico: {len(observacoes)} observações, última em {ultima}"
        if idade_hist > IDADE_MAXIMA_DIAS:
            locais.append(f"Histórico parado em {ultima} ({idade_hist} dias sem atualização).")
        # Saúde da FONTE, não só da entrega.
        #
        # Este bloco existe por causa de uma execução real: o focus-semanal
        # rodou, todos os passos deram verde, o commit saiu — e o histórico
        # publicado tinha 120 linhas de uma única data, todas fonte=pdf, sem
        # uma linha de dispersão. A API de Expectativas, que é a fonte
        # PRIMÁRIA, não entregou nada, e nada no pipeline reclamou.
        #
        # `cmd_sincronizar` cai para o PDF de propósito, para o boletim de
        # segunda não morrer por indisponibilidade momentânea do BCB. Mas
        # "caiu para a reserva" é estado de exceção: se ninguém verifica, o
        # projeto volta a ser o que era antes desta reestruturação — um
        # pipeline que roda, não falha, e publica menos do que deveria.
        da_api = sum(1 for o in observacoes if o.fonte == store.FONTE_API)
        do_pdf = len(observacoes) - da_api

        if da_api == 0:
            locais.append(
                "Nenhuma observação veio da API de Expectativas — a fonte "
                "primária não entregou nada e o histórico está inteiro na "
                "reserva (PDF), sem dispersão. Rode "
                "`python -m focus sincronizar --exigir-api` para ver o erro."
            )
        elif do_pdf:
            # Nem toda linha vinda do PDF é sintoma.
            #
            # A Selic mensal não existe na API de Expectativas: só o quadro do
            # PDF a publica. Contá-la como anomalia produzia um `[aviso]`
            # permanente, que aparecia em toda execução e nunca podia ser
            # resolvido — a mesma patologia do falso positivo que o vigia já
            # tinha no cálculo de atraso. Alerta que não limpa ensina o dono a
            # parar de ler os alertas.
            inesperadas = [
                o
                for o in observacoes
                if o.fonte == store.FONTE_PDF
                and (o.indicador, o.horizonte) not in api.SEM_COBERTURA_NA_API
            ]
            if inesperadas:
                chaves = sorted({f"{o.indicador}/{o.horizonte}" for o in inesperadas})
                avisos.append(
                    f"{len(inesperadas)} observação(ões) vieram do PDF sem que a API "
                    f"devesse estar faltando: {', '.join(chaves)}. Essas linhas não "
                    "têm dispersão."
                )

        # Uma só data no histórico significa que revisão, trajetória e
        # amplitude saem vazias — o painel abre e não diz nada.
        datas = an.datas_disponiveis(observacoes)
        if len(datas) < 2:
            locais.append(
                f"Histórico com {len(datas)} data(s) apenas. Sem ao menos duas "
                "edições não há revisão, trajetória nem amplitude: o dashboard "
                "sai vazio mesmo com o pipeline reportando sucesso."
            )

        if locais:
            problemas.extend(locais)
        else:
            aprovados.append(resumo_hist)

    htmls = sorted(PASTA_SAIDA.glob("focus_*.html"), reverse=True)
    if not htmls:
        problemas.append("Nenhum resumo em output/focus/ — o agente nunca publicou.")
    else:
        data_html = _data_do_nome(htmls[0])
        if data_html is not None:
            idade = (hoje - data_html).days
            if idade > IDADE_MAXIMA_DIAS:
                problemas.append(
                    f"Último resumo publicado é de {data_html} ({idade} dias). "
                    "O pipeline baixa dados mas não está entregando o boletim."
                )
            else:
                aprovados.append(f"Último resumo publicado: {htmls[0].name} ({idade} dias)")

    for aprovado in aprovados:
        print(f"[ok] {aprovado}")
    for aviso in avisos:
        print(f"[aviso] {aviso}")
    for problema in problemas:
        _erro(f"[FALHA] {problema}")

    return 1 if problemas else 0


# ── Argumentos ────────────────────────────────────────────────────────────────


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="focus", description=__doc__)
    p.add_argument("-v", "--verboso", action="store_true", help="log em nível DEBUG")
    sub = p.add_subparsers(dest="comando", required=True)

    b = sub.add_parser("baixar", help="baixa o PDF mais recente do Focus")
    b.add_argument("--destino", type=Path, default=PASTA_DADOS)
    b.add_argument("--sem-extrair", action="store_true", help="não extrai o texto depois")
    b.set_defaults(func=cmd_baixar)

    e = sub.add_parser("extrair", help="extrai o texto de um PDF")
    e.add_argument("--pdf", type=Path, default=None)
    e.add_argument("--forcar", action="store_true", help="reextrai mesmo se o .txt existir")
    e.set_defaults(func=cmd_extrair)

    s = sub.add_parser("sincronizar", help="atualiza o histórico de expectativas")
    s.add_argument("--historico", type=Path, default=store.CAMINHO_PADRAO)
    s.add_argument("--dias", type=int, default=730, help="janela retroativa (padrão: 730)")
    s.add_argument(
        "--exigir-api",
        action="store_true",
        help="falha se a API do BCB estiver indisponível, em vez de cair para o PDF",
    )
    s.set_defaults(func=cmd_sincronizar)

    d = sub.add_parser("dashboard", help="gera o dashboard estático")
    d.add_argument("--historico", type=Path, default=store.CAMINHO_PADRAO)
    d.add_argument("--destino", type=Path, default=dashboard.DESTINO_PADRAO)
    d.set_defaults(func=cmd_dashboard)

    m = sub.add_parser("email", help="monta e envia o e-mail semanal")
    m.add_argument("--historico", type=Path, default=store.CAMINHO_PADRAO)
    m.add_argument("--prosa", type=Path, default=None, help="Markdown escrito pelo agente")
    m.add_argument("--dest", default=None, help="destinatários (padrão: FOCUS_EMAIL_DEST)")
    m.add_argument("--url-dashboard", default=None)
    m.add_argument("--dry-run", action="store_true", help="monta sem enviar")
    m.set_defaults(func=cmd_email)

    v = sub.add_parser("verificar", help="diagnóstico de saúde do pipeline")
    v.add_argument("--historico", type=Path, default=store.CAMINHO_PADRAO)
    v.add_argument(
        "--hoje",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="sobrescreve a data de hoje (para testes)",
    )
    v.set_defaults(func=cmd_verificar)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _configurar_log(args.verboso)
    try:
        return args.func(args)
    except (
        pdf.FocusIndisponivelError,
        LayoutDesconhecidoError,
        api.ApiExpectativasError,
        mail.CredenciaisAusentesError,
    ) as exc:
        _erro(f"ERRO: {exc}")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
