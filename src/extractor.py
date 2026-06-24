import logging
import sys
import pdfplumber
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


def extract_text(pdf_path: Path) -> Path:
    """
    Extrai o texto de um PDF do Focus e salva em .txt com o mesmo stem.
    Páginas vazias ou sem texto são ignoradas.
    Retorna o caminho do arquivo .txt gerado.
    """
    pdf_path = Path(pdf_path)
    dest = pdf_path.with_suffix(".txt")

    if dest.exists():
        log.info("Texto já extraído: %s", dest.name)
        return dest

    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text(layout=True)
            if text and text.strip():
                pages.append(text.strip())
            log.debug("Página %d — %d chars", i, len(text) if text else 0)

    if not pages:
        raise ValueError(f"Nenhum texto extraído de {pdf_path.name}")

    full_text = "\n\n".join(pages)
    dest.write_text(full_text, encoding="utf-8")
    log.info("Texto salvo: %s (%d chars, %d páginas)", dest.name, len(full_text), len(pages))
    return dest


def _most_recent_pdf() -> Path:
    pdfs = sorted(DATA_DIR.glob("focus_*.pdf"), reverse=True)
    if not pdfs:
        raise FileNotFoundError("Nenhum PDF encontrado em data/. Execute o downloader primeiro.")
    return pdfs[0]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _most_recent_pdf()
    print(extract_text(pdf_path))
