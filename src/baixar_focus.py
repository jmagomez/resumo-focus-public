import sys
from datetime import date, timedelta
from pathlib import Path

import requests

_BCB_URL = "https://www.bcb.gov.br/content/focus/focus/R{}.pdf"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}
_MAX_LOOKBACK = 7


def última_segunda(hoje: date) -> date:
    """Retorna a segunda-feira mais recente estritamente anterior a `hoje`.

    Se `hoje` já é segunda-feira, retrocede para a segunda da semana passada.
    """
    # weekday(): Monday=0 … Sunday=6
    dias_desde_segunda = hoje.weekday()  # 0 se hoje é segunda
    if dias_desde_segunda == 0:
        dias_desde_segunda = 7  # força recuo para a semana anterior
    return hoje - timedelta(days=dias_desde_segunda)


def baixar(dest: Path | str) -> tuple[date, Path]:
    """Baixa o PDF mais recente do Boletim Focus na pasta `dest`.

    Parte da última segunda-feira em relação a hoje e recua dia a dia até
    encontrar o PDF (máximo _MAX_LOOKBACK tentativas, cobrindo feriados).
    Valida que o conteúdo começa com bytes ``%PDF`` antes de aceitar.

    Retorna ``(data_da_publicacao, caminho_do_arquivo)``.
    Levanta ``RuntimeError`` se nenhuma tentativa for bem-sucedida.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    inicio = última_segunda(date.today())

    for delta in range(_MAX_LOOKBACK):
        candidata = inicio - timedelta(days=delta)
        url = _BCB_URL.format(candidata.strftime("%Y%m%d"))

        try:
            r = requests.get(url, headers=_HEADERS, timeout=30)
        except requests.RequestException:
            continue

        if r.status_code != 200:
            continue

        if not r.content.startswith(b"%PDF"):
            continue

        nome = f"focus_{candidata.isoformat()}.pdf"
        caminho = dest / nome
        caminho.write_bytes(r.content)
        return candidata, caminho

    raise RuntimeError(
        f"PDF do Focus não encontrado nos últimos {_MAX_LOOKBACK} dias a partir de {inicio}"
    )


def main() -> None:
    pasta = Path(__file__).parent.parent / "data"
    data_pub, caminho = baixar(pasta)
    tamanho_kb = caminho.stat().st_size / 1024
    print(f"{caminho}  ({tamanho_kb:.1f} KB)")


if __name__ == "__main__":
    main()
