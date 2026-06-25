"""Envia o resumo HTML do Boletim Focus por e-mail via SMTP do Gmail.

Credenciais lidas exclusivamente de variáveis de ambiente — nunca do código:
  FOCUS_SMTP_USER         – endereço Gmail do remetente
  FOCUS_SMTP_APP_PASSWORD – senha de app gerada no Google (não a senha normal)
  FOCUS_EMAIL_DEST        – destinatários separados por vírgula
  FOCUS_EMAIL_BCC         – (opcional) endereços em cópia oculta
"""

import argparse
import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Pasta onde o agente salva os HTMLs gerados
_PASTA_OUTPUT = Path(__file__).parent.parent / "output" / "focus"

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 465  # SSL nativo; não usar STARTTLS (porta 587)


def _html_mais_recente() -> Path | None:
    """Retorna o HTML mais recente em output/focus/, ou None se não houver."""
    htmls = sorted(_PASTA_OUTPUT.glob("focus_*.html"), reverse=True)
    return htmls[0] if htmls else None


def _assunto_do_nome(caminho: Path) -> str:
    """Deriva o assunto a partir do nome do arquivo.

    focus_2026-06-23.html → 'Resumo Focus - 2026-06-23'
    """
    # O stem é 'focus_2026-06-23'; extrai a data após o primeiro underscore
    partes = caminho.stem.split("_", 1)
    data = partes[1] if len(partes) == 2 else caminho.stem
    return f"Resumo Focus - {data}"


def _texto_fallback(html: str) -> str:
    """Gera fallback em texto puro para clientes que não renderizam HTML."""
    # Remove todas as tags e normaliza espaços em branco
    texto = re.sub(r"<[^>]+>", " ", html)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def enviar(
    html_path: Path,
    destinatarios: list[str],
    assunto: str | None = None,
    bcc: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    """Monta e envia o e-mail HTML via SMTP do Gmail com SSL.

    Em dry_run=True exibe o e-mail no terminal sem enviar
    e sem exigir que as variáveis de credencial estejam definidas.
    """
    html_path = Path(html_path)
    html = html_path.read_text(encoding="utf-8")

    assunto_final = assunto or _assunto_do_nome(html_path)
    remetente = os.environ.get("FOCUS_SMTP_USER", "remetente@gmail.com")

    # Monta mensagem multipart/alternative (texto puro + HTML)
    mensagem = MIMEMultipart("alternative")
    mensagem["Subject"] = assunto_final
    mensagem["From"] = remetente
    mensagem["To"] = ", ".join(destinatarios)
    if bcc:
        mensagem["Bcc"] = ", ".join(bcc)

    # RFC 2046: a última parte tem precedência — HTML deve vir por último
    mensagem.attach(MIMEText(_texto_fallback(html), "plain", "utf-8"))
    mensagem.attach(MIMEText(html, "html", "utf-8"))

    if dry_run:
        print("=== DRY-RUN — e-mail NÃO foi enviado ===")
        print(f"De:      {mensagem['From']}")
        print(f"Para:    {mensagem['To']}")
        if bcc:
            print(f"Cco:     {mensagem['Bcc']}")
        print(f"Assunto: {mensagem['Subject']}")
        print(f"Arquivo: {html_path}  ({len(html):,} chars)")
        print("\n--- Início do corpo HTML ---")
        # Exibe apenas as primeiras 40 linhas para não poluir o terminal
        linhas = html.splitlines()
        for linha in linhas[:40]:
            print(linha)
        if len(linhas) > 40:
            print(f"... ({len(linhas) - 40} linhas omitidas)")
        return

    # Lê credenciais das variáveis de ambiente — nunca hardcoded
    usuario = os.environ.get("FOCUS_SMTP_USER")
    senha = os.environ.get("FOCUS_SMTP_APP_PASSWORD")

    if not usuario:
        print("Erro: variável FOCUS_SMTP_USER não definida.", file=sys.stderr)
        sys.exit(1)
    if not senha:
        print("Erro: variável FOCUS_SMTP_APP_PASSWORD não definida.", file=sys.stderr)
        sys.exit(1)

    # Envelope SMTP inclui To + Bcc (Bcc não aparece no cabeçalho, mas é entregue)
    todos = destinatarios + (bcc or [])

    with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT) as smtp:
        smtp.login(usuario, senha)
        smtp.sendmail(usuario, todos, mensagem.as_bytes())

    print(f"E-mail enviado para: {', '.join(todos)}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Envia o resumo HTML do Focus por e-mail via Gmail SMTP."
    )
    parser.add_argument(
        "--html",
        type=Path,
        default=None,
        help="Caminho do arquivo HTML (padrão: mais recente em output/focus/).",
    )
    parser.add_argument(
        "--dest",
        default=None,
        help="Destinatários separados por vírgula (padrão: FOCUS_EMAIL_DEST).",
    )
    parser.add_argument(
        "--assunto",
        default=None,
        help="Assunto personalizado (padrão: derivado do nome do arquivo).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Monta e exibe o e-mail sem enviar. Não exige credenciais.",
    )
    args = parser.parse_args()

    # Resolve o arquivo HTML a usar
    if args.html:
        html_path = args.html
        if not html_path.exists():
            print(f"Erro: arquivo não encontrado: {html_path}", file=sys.stderr)
            sys.exit(1)
    else:
        html_path = _html_mais_recente()
        if html_path is None:
            print(
                "Nenhum HTML encontrado em output/focus/. "
                "Execute o agente de resumo primeiro.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Resolve destinatários (--dest tem prioridade sobre a variável de ambiente)
    dest_str = args.dest or os.environ.get("FOCUS_EMAIL_DEST", "")
    destinatarios = [e.strip() for e in dest_str.split(",") if e.strip()]
    if not destinatarios:
        print(
            "Erro: informe destinatários via --dest ou defina FOCUS_EMAIL_DEST.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve BCC opcional
    bcc_str = os.environ.get("FOCUS_EMAIL_BCC", "")
    bcc = [e.strip() for e in bcc_str.split(",") if e.strip()] or None

    enviar(
        html_path=html_path,
        destinatarios=destinatarios,
        assunto=args.assunto,
        bcc=bcc,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
