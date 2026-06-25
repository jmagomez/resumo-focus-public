"""Pipeline local: baixa o Boletim Focus e extrai o texto em sequência."""

import argparse
import sys
import webbrowser
from pathlib import Path

# Garante que caracteres acentuados apareçam corretamente no terminal Windows
sys.stdout.reconfigure(encoding="utf-8")

# Adiciona src/ ao path para que as importações abaixo funcionem
sys.path.insert(0, str(Path(__file__).parent / "src"))

from baixar_focus import baixar
from extrair_texto import extrair


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Baixa o Boletim Focus e extrai o texto do PDF."
    )
    parser.add_argument(
        "--abrir",
        action="store_true",
        help="Abre o arquivo .txt gerado no navegador padrão ao final.",
    )
    args = parser.parse_args()

    pasta_dados = Path(__file__).parent / "data"

    # --- Etapa 1: download do PDF ---
    data_pub, caminho_pdf = baixar(pasta_dados)
    tamanho_kb = caminho_pdf.stat().st_size / 1024
    print(f"[1/2] PDF baixado: {caminho_pdf.name} ({tamanho_kb:.1f} KB)")

    # --- Etapa 2: extração do texto ---
    caminho_txt = extrair(caminho_pdf)
    print(f"[2/2] Texto extraído: {caminho_txt}")

    # Abre o .txt no navegador se a flag --abrir foi passada
    if args.abrir:
        webbrowser.open(caminho_txt.as_uri())


if __name__ == "__main__":
    main()
