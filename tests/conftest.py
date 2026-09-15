import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# O pacote vive em src/ — layout src evita que o diretório do repositório
# entre no sys.path e mascare erros de empacotamento.
sys.path.insert(0, str(RAIZ / "src"))


def fixture(nome: str) -> Path:
    return FIXTURES / nome
