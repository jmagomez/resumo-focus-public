import logging
import requests
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

BCB_URL = "https://www.bcb.gov.br/content/focus/focus/R{}.pdf"
DATA_DIR = Path(__file__).parent.parent / "data"
MAX_LOOKBACK = 7

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BoletimFocus-Bot/1.0)"}


def fetch_focus(start: date = None, max_lookback: int = MAX_LOOKBACK) -> Path:
    """
    Baixa o PDF mais recente do Boletim Focus, partindo de `start` e
    recuando dia a dia até encontrá-lo (máximo `max_lookback` tentativas).

    Regra BCB: publicação toda segunda-feira; quando é feriado, publica na terça.
    O retrocesso garante que ambos os casos sejam cobertos sem lógica especial
    de calendário.

    Retorna o caminho do arquivo salvo em data/.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    start = start or date.today()

    for delta in range(max_lookback):
        candidate = start - timedelta(days=delta)
        dest = DATA_DIR / f"focus_{candidate.isoformat()}.pdf"

        if dest.exists():
            log.info("Arquivo já existe localmente: %s", dest.name)
            return dest

        url = BCB_URL.format(candidate.strftime("%Y%m%d"))
        log.debug("Tentando: %s", url)

        try:
            r = requests.get(url, headers=_HEADERS, timeout=30)
        except requests.RequestException as exc:
            log.warning("Erro de rede em %s: %s", url, exc)
            continue

        if r.status_code == 200:
            dest.write_bytes(r.content)
            log.info("Baixado: %s (%.1f KB)", dest.name, len(r.content) / 1024)
            return dest

        log.debug("HTTP %s — %s", r.status_code, url)

    raise FileNotFoundError(
        f"PDF do Focus não encontrado nos últimos {max_lookback} dias a partir de {start}"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    saved = fetch_focus()
    print(saved)
