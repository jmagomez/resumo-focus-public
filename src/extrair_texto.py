"""Extrai o texto de um PDF do Boletim Focus e salva como arquivo .txt."""

import argparse
import sys
from pathlib import Path

import pdfplumber

# Pasta padrão onde os PDFs ficam armazenados
_PASTA_DADOS = Path(__file__).parent.parent / "data"


def extrair(pdf_path: Path | str) -> Path:
    """Abre o PDF com pdfplumber, une o texto de todas as páginas e salva em .txt.

    O arquivo de saída fica na mesma pasta do PDF, com o mesmo nome e extensão .txt.
    Retorna o caminho do .txt gerado.
    """
    pdf_path = Path(pdf_path)

    # Coleta o texto de cada página que tenha conteúdo
    paginas: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text(layout=True)
            if texto and texto.strip():
                paginas.append(texto.strip())

    # Une as páginas com linha em branco entre elas
    texto_completo = "\n\n".join(paginas)

    # Salva com o mesmo stem do PDF, só trocando a extensão
    caminho_txt = pdf_path.with_suffix(".txt")
    caminho_txt.write_text(texto_completo, encoding="utf-8")

    return caminho_txt


def _pdf_mais_recente() -> Path | None:
    """Retorna o PDF mais recente em _PASTA_DADOS, ou None se não houver nenhum."""
    pdfs = sorted(_PASTA_DADOS.glob("focus_*.pdf"), reverse=True)
    return pdfs[0] if pdfs else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai o texto de um PDF do Boletim Focus e salva como .txt."
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=None,
        help="Caminho do PDF a extrair (padrão: mais recente em data/).",
    )
    args = parser.parse_args()

    # Decide qual PDF usar
    if args.pdf:
        pdf_path = args.pdf
        if not pdf_path.exists():
            print(f"Erro: arquivo não encontrado: {pdf_path}", file=sys.stderr)
            sys.exit(1)
    else:
        pdf_path = _pdf_mais_recente()
        if pdf_path is None:
            # Nenhum PDF disponível: orienta o usuário a baixar primeiro
            print(
                "Nenhum PDF encontrado em data/. "
                "Execute primeiro: python src/baixar_focus.py",
                file=sys.stderr,
            )
            sys.exit(1)

    caminho_txt = extrair(pdf_path)
    print(caminho_txt)


if __name__ == "__main__":
    main()
