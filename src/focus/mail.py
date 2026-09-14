"""Envio do e-mail semanal via SMTP do Gmail.

Credenciais vêm exclusivamente de variáveis de ambiente — nunca do código,
nunca de arquivo versionado:

``FOCUS_SMTP_USER``          endereço Gmail do remetente
``FOCUS_SMTP_APP_PASSWORD``  senha de app gerada no Google (não a senha da conta)
``FOCUS_EMAIL_DEST``         destinatários separados por vírgula
``FOCUS_EMAIL_BCC``          (opcional) cópia oculta
"""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

log = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL nativo; a porta 587 (STARTTLS) exige outro fluxo


class CredenciaisAusentesError(RuntimeError):
    """Faltou variável de ambiente obrigatória para o envio."""


@dataclass(frozen=True)
class Destino:
    remetente: str
    para: list[str]
    bcc: list[str]

    @property
    def envelope(self) -> list[str]:
        return self.para + self.bcc


def _lista(bruto: str | None) -> list[str]:
    return [e.strip() for e in (bruto or "").split(",") if e.strip()]


def destino_do_ambiente(*, destinatarios: str | None = None) -> Destino:
    remetente = os.environ.get("FOCUS_SMTP_USER", "").strip()
    para = _lista(destinatarios or os.environ.get("FOCUS_EMAIL_DEST"))
    if not remetente:
        raise CredenciaisAusentesError("FOCUS_SMTP_USER não definida.")
    if not para:
        raise CredenciaisAusentesError(
            "Nenhum destinatário: defina FOCUS_EMAIL_DEST ou use --dest."
        )
    return Destino(remetente=remetente, para=para, bcc=_lista(os.environ.get("FOCUS_EMAIL_BCC")))


def montar(assunto: str, html: str, texto: str, destino: Destino) -> EmailMessage:
    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = f"Boletim Focus <{destino.remetente}>"
    mensagem["To"] = ", ".join(destino.para)
    if destino.bcc:
        mensagem["Bcc"] = ", ".join(destino.bcc)
    mensagem.set_content(texto)
    mensagem.add_alternative(html, subtype="html")
    return mensagem


def enviar(mensagem: EmailMessage, destino: Destino) -> None:
    senha = os.environ.get("FOCUS_SMTP_APP_PASSWORD", "")
    if not senha:
        raise CredenciaisAusentesError(
            "FOCUS_SMTP_APP_PASSWORD não definida. Gere uma senha de app em "
            "https://myaccount.google.com/apppasswords e cadastre-a como secret "
            "do repositório."
        )
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(destino.remetente, senha)
        smtp.send_message(mensagem, from_addr=destino.remetente, to_addrs=destino.envelope)
    log.info("E-mail enviado para %s", ", ".join(destino.envelope))
