"""Testes para src/baixar_focus.py."""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

# Insere src/ no path, igual ao demo.py
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from baixar_focus import baixar, última_segunda

# ---------------------------------------------------------------------------
# Testes offline para última_segunda
# ---------------------------------------------------------------------------

def test_última_segunda_quinta():
    """Quinta-feira deve retornar a segunda da mesma semana."""
    quinta = date(2026, 6, 18)          # quinta-feira
    assert última_segunda(quinta) == date(2026, 6, 15)


def test_última_segunda_terça():
    """Terça-feira deve retornar a segunda imediatamente anterior."""
    terça = date(2026, 6, 16)           # terça-feira
    assert última_segunda(terça) == date(2026, 6, 15)


def test_última_segunda_quando_hoje_é_segunda():
    """Se hoje for segunda, a própria segunda é retornada (inclui hoje)."""
    segunda = date(2026, 6, 15)         # segunda-feira
    assert última_segunda(segunda) == date(2026, 6, 15)


def test_última_segunda_domingo():
    """Domingo deve retornar a segunda de seis dias atrás."""
    domingo = date(2026, 6, 14)         # domingo
    assert última_segunda(domingo) == date(2026, 6, 8)


def test_última_segunda_varredura_60_dias():
    """Para qualquer dia numa janela de 60 dias, o retorno deve ser:
    - uma segunda-feira (weekday == 0), e
    - anterior ou igual à data fornecida (inclui hoje se for segunda).
    """
    inicio = date(2026, 4, 1)
    for delta in range(60):
        hoje = inicio + timedelta(days=delta)
        resultado = última_segunda(hoje)
        assert resultado.weekday() == 0, (
            f"{hoje} deveria retornar uma segunda, mas retornou {resultado} "
            f"({resultado.strftime('%A')})"
        )
        assert resultado <= hoje, (
            f"Para {hoje}, o retorno {resultado} não pode ser posterior."
        )


# ---------------------------------------------------------------------------
# Teste de rede — baixa o PDF real do BCB
# ---------------------------------------------------------------------------

@pytest.mark.network
def test_baixar_pdf_real(tmp_path):
    """Faz o download real do Boletim Focus e valida o arquivo recebido."""
    data_pub, caminho = baixar(tmp_path)

    # O arquivo deve existir em disco
    assert caminho.exists(), "O arquivo PDF não foi criado."

    # Deve ter mais de 50 KB (boletins reais têm centenas de KB)
    tamanho_kb = caminho.stat().st_size / 1024
    assert tamanho_kb > 50, f"Arquivo suspeito: apenas {tamanho_kb:.1f} KB."

    # O conteúdo deve começar com a assinatura de PDF
    with caminho.open("rb") as f:
        cabecalho = f.read(4)
    assert cabecalho == b"%PDF", f"Arquivo não é um PDF válido (cabeçalho: {cabecalho!r})."

    # O nome do arquivo deve bater com a data de publicação retornada
    nome_esperado = f"focus_{data_pub.isoformat()}.pdf"
    assert caminho.name == nome_esperado, (
        f"Nome do arquivo ({caminho.name}) não corresponde à data ({data_pub})."
    )

    # A data de publicação não pode ser futura nem mais antiga que 14 dias
    hoje = date.today()
    assert data_pub <= hoje, f"Data de publicação {data_pub} está no futuro."
    assert (hoje - data_pub).days <= 14, (
        f"Data de publicação {data_pub} está a mais de 14 dias no passado."
    )
