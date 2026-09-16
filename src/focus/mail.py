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


def _senha_de_app() -> str:
    """Lê a senha de app já normalizada.

    O Google exibe a senha de app em quatro grupos de quatro letras
    (``abcd efgh ijkl mnop``). Copiar da tela traz os espaços, e colar num
    campo de secret às vezes traz também uma quebra de linha no fim. O
    servidor do Gmail tolera os espaços internos, mas qualquer coisa em volta
    vira ``535 BadCredentials`` — um erro que não diz o que está errado e é
    indistinguível de senha revogada.

    Uma senha de app é sempre 16 letras minúsculas, então remover todo espaço
    em branco não pode descartar informação legítima.
    """
    return "".join(os.environ.get("FOCUS_SMTP_APP_PASSWORD", "").split())


def _mascarar(endereco: str) -> str:
    """``jose@gmail.com`` → ``jo**@gmail.com``.

    O log do Actions deste repositório é **público**. Precisamos de
    identificação suficiente para notar que a conta tentada não é a esperada,
    sem publicar o endereço inteiro.
    """
    usuario, arroba, dominio = endereco.partition("@")
    if not arroba:
        return "(endereço sem @)"
    visivel = usuario[:2] if len(usuario) > 3 else usuario[:1]
    return f"{visivel}{'*' * max(len(usuario) - len(visivel), 1)}@{dominio}"


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
    senha = _senha_de_app()
    if not senha:
        raise CredenciaisAusentesError(
            "FOCUS_SMTP_APP_PASSWORD não definida. Gere uma senha de app em "
            "https://myaccount.google.com/apppasswords e cadastre-a como secret "
            "do repositório."
        )
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        try:
            smtp.login(destino.remetente, senha)
        except smtplib.SMTPAuthenticationError as exc:
            # O 535 do Gmail é sempre a mesma frase, qualquer que seja a causa:
            # usuário errado, senha revogada, 2FA desligada ou senha de app de
            # outra conta. Sem esta mensagem, o log mostra só um traceback de
            # smtplib e a única reação possível é gerar outra senha — que não
            # resolve nada quando o problema é o usuário.
            raise CredenciaisAusentesError(
                f"O Gmail recusou as credenciais ({exc.smtp_code}) para a conta "
                f"{_mascarar(destino.remetente)}, com {len(senha)} caractere(s) de "
                "senha de app (o esperado são 16). Confira, nesta ordem: "
                "(1) FOCUS_SMTP_USER é o endereço completo da conta DONA da senha "
                "de app; (2) a verificação em duas etapas está ativa nessa conta; "
                "(3) a senha de app foi gerada para essa mesma conta e não foi "
                "revogada — trocar a senha da conta revoga todas."
            ) from exc
        smtp.send_message(mensagem, from_addr=destino.remetente, to_addrs=destino.envelope)
    log.info("E-mail enviado para %d destinatário(s)", len(destino.envelope))
