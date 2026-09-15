"""Raízes e resolução de fixtures dos testes.

As fixtures **não são cópias**: são os boletins reais já versionados em
``data/``. Duplicá-los em ``tests/fixtures/`` custaria 46 KB e criaria o risco
silencioso de a cópia divergir do arquivo que o pipeline realmente lê — que é
exatamente a classe de defeito que esta reestruturação existe para eliminar.

Cada apelido abaixo nomeia o *caso de layout* que aquela edição exercita. Os
quatro foram escolhidos porque quebravam o parser anterior.
"""

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "data"

# O pacote vive em src/ — layout src evita que o diretório do repositório
# entre no sys.path e mascare erros de empacotamento.
sys.path.insert(0, str(RAIZ / "src"))

#: apelido do caso  ->  edição real do Focus que o exercita
EDICOES = {
    # Quadro anual e mensal completos, com as colunas de 5 dias úteis.
    "focus_completo.txt": "focus_2026-07-17.txt",
    # Câmbio mensal traz "5,13 5,12 -": bloco sem a mediana de hoje e sem
    # cauda. O parser anterior consumia a coluna de 5 dias do bloco seguinte.
    "focus_sem_hoje.txt": "focus_2026-07-31.txt",
    # Edição anterior à de referência, usada para calcular revisão semanal.
    "focus_anterior.txt": "focus_2026-08-28.txt",
    # Selic mensal traz "- - -" para outubro: bloco inteiramente vazio, que
    # deslocava todas as colunas seguintes na extração posicional.
    "focus_bloco_vazio.txt": "focus_2026-09-11.txt",
}


def fixture(nome: str) -> Path:
    """Caminho do boletim real correspondente ao caso ``nome``."""
    arquivo = EDICOES.get(nome, nome)
    caminho = DADOS / arquivo
    if not caminho.exists():
        pytest.fail(
            f"O caso '{nome}' depende de {caminho.relative_to(RAIZ)}, que não está "
            "no repositório. Os .txt de data/ são versionados de propósito: o "
            "conjunto de testes os usa como fixtures. Não os remova."
        )
    return caminho
