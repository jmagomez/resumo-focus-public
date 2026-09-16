"""Testes do envio — foco no diagnóstico, não no transporte.

O Gmail responde `535 ... BadCredentials` de forma idêntica para usuário
errado, senha revogada, 2FA desligada e senha de app de outra conta. Sem
mensagem própria, o log do Actions mostra só um traceback de `smtplib`, e a
única reação possível vira "gerar outra senha" — que não resolve nada quando
a causa é o usuário. Foi o que aconteceu em 16/09/2026: duas execuções
seguidas com o mesmo 535 e nenhuma pista de qual conta havia sido tentada.
"""

import smtplib
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from focus import mail


def _destino():
    return mail.Destino(remetente="jose@exemplo.com", para=["dest@exemplo.com"], bcc=[])


# ── Normalização da senha de app ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "bruto",
    [
        "abcdefghijklmnop",
        "abcd efgh ijkl mnop",
        "abcd efgh ijkl mnop\n",
        "  abcd efgh ijkl mnop  ",
        "abcd\tefgh ijkl\nmnop",
    ],
)
def test_senha_de_app_normaliza_como_o_google_exibe(bruto, monkeypatch):
    """O Google mostra a senha em quatro grupos; copiar traz espaço e newline."""
    monkeypatch.setenv("FOCUS_SMTP_APP_PASSWORD", bruto)
    assert mail._senha_de_app() == "abcdefghijklmnop"


def test_senha_ausente_continua_sendo_erro(monkeypatch):
    monkeypatch.setenv("FOCUS_SMTP_APP_PASSWORD", "   \n ")
    with pytest.raises(mail.CredenciaisAusentesError, match="FOCUS_SMTP_APP_PASSWORD"):
        mail.enviar(EmailMessage(), _destino())


# ── Máscara: o log deste repositório é público ────────────────────────────────


@pytest.mark.parametrize(
    "endereco, esperado",
    [
        ("jose@exemplo.com", "jo**@exemplo.com"),
        ("ab@exemplo.com", "a*@exemplo.com"),
        ("a@exemplo.com", "a*@exemplo.com"),
        ("semarroba", "(endereço sem @)"),
    ],
)
def test_mascarar(endereco, esperado):
    assert mail._mascarar(endereco) == esperado


# ── O 535 vira mensagem acionável ─────────────────────────────────────────────


def _smtp_que_recusa_login():
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.login.side_effect = smtplib.SMTPAuthenticationError(
        535, b"5.7.8 Username and Password not accepted."
    )
    return smtp


def test_535_explica_as_tres_causas_possiveis(monkeypatch):
    monkeypatch.setenv("FOCUS_SMTP_APP_PASSWORD", "abcd efgh ijkl mnop")
    with patch("focus.mail.smtplib.SMTP_SSL", return_value=_smtp_que_recusa_login()):
        with pytest.raises(mail.CredenciaisAusentesError) as erro:
            mail.enviar(EmailMessage(), _destino())

    texto = str(erro.value)
    assert "535" in texto
    assert "FOCUS_SMTP_USER" in texto
    assert "duas etapas" in texto
    assert "revogada" in texto


def test_mensagem_de_erro_nao_vaza_senha_nem_endereco_inteiro(monkeypatch):
    """O log do Actions é público: nem a senha nem o endereço completo entram."""
    monkeypatch.setenv("FOCUS_SMTP_APP_PASSWORD", "abcd efgh ijkl mnop")
    with patch("focus.mail.smtplib.SMTP_SSL", return_value=_smtp_que_recusa_login()):
        with pytest.raises(mail.CredenciaisAusentesError) as erro:
            mail.enviar(EmailMessage(), _destino())

    texto = str(erro.value)
    assert "abcdefghijklmnop" not in texto
    assert "abcd efgh" not in texto
    assert "jose@exemplo.com" not in texto
    assert "jo**@exemplo.com" in texto


def test_o_tamanho_da_senha_aparece_porque_denuncia_o_caso_bobo(monkeypatch):
    """16 é o esperado; qualquer outro número aponta a causa sem expor o valor."""
    monkeypatch.setenv("FOCUS_SMTP_APP_PASSWORD", "curta")
    with patch("focus.mail.smtplib.SMTP_SSL", return_value=_smtp_que_recusa_login()):
        with pytest.raises(mail.CredenciaisAusentesError) as erro:
            mail.enviar(EmailMessage(), _destino())
    assert "5 caractere(s)" in str(erro.value)


def test_envio_bem_sucedido_usa_a_senha_normalizada(monkeypatch):
    monkeypatch.setenv("FOCUS_SMTP_APP_PASSWORD", "abcd efgh ijkl mnop\n")
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    with patch("focus.mail.smtplib.SMTP_SSL", return_value=smtp):
        mail.enviar(EmailMessage(), _destino())

    smtp.login.assert_called_once_with("jose@exemplo.com", "abcdefghijklmnop")
    smtp.send_message.assert_called_once()
