"""Extrai medianas estruturadas do arquivo .txt do Boletim Focus."""

import re
from pathlib import Path

_NUM   = re.compile(r'-?\d+,\d+')
_DATE  = re.compile(r'(\d{1,2}) de (\w+) de (\d{4})', re.IGNORECASE)
_PAGE  = re.compile(r'Pág\.\s+\d+/\d+')

_MONTHS_PT = {
    "janeiro": "01", "fevereiro": "02", "março": "03", "abril": "04",
    "maio": "05", "junho": "06", "julho": "07", "agosto": "08",
    "setembro": "09", "outubro": "10", "novembro": "11", "dezembro": "12",
}

# --- Indicadores e padrões de busca ---

_ANN_PATTERNS: dict[str, re.Pattern] = {
    "IPCA":             re.compile(r'IPCA \(varia'),
    "PIB":              re.compile(r'PIB Total'),
    "Câmbio":           re.compile(r'Câmbio \(R'),
    "Selic":            re.compile(r'Selic \(% a'),
    "IGP-M":            re.compile(r'IGP-M'),
    "IPCA Admin.":      re.compile(r'IPCA Adminis'),
    "Conta corrente":   re.compile(r'Conta corrente'),
    "Bal. comercial":   re.compile(r'Balan'),
    "IDP":              re.compile(r'Investimento direto'),
    "DLSP":             re.compile(r'vida l'),
    "Result. primário": re.compile(r'Resultado prim'),
    "Result. nominal":  re.compile(r'Resultado nom'),
}

_MON_PATTERNS: dict[str, re.Pattern] = {
    "IPCA":  re.compile(r'IPCA \(varia'),
    "IGP-M": re.compile(r'IGP-M'),
}

YEARS  = ["2026", "2027", "2028", "2029"]
MONTHS = ["jun/2026", "jul/2026", "ago/2026", "infl12m"]

# Índices de "hoje" e "há 1 sem" dentro da lista de decimais extraídos por linha.
#
# Anual: blocos de (4, 4, 3, 3) decimais por ano → hoje em [2, 6, 10, 13]
# Mensal: blocos de (4, 4, 4, 4) decimais por mês → hoje em [2, 6, 10, 14]
_ANN_HOJ = [2, 6, 10, 13]
_ANN_SEM = [1, 5, 9,  12]

_MON_HOJ = [2, 6, 10, 14]
_MON_SEM = [1, 5, 9,  13]


def _cell(nums: list[str], idx: int) -> str:
    return nums[idx] if idx < len(nums) else "-"


def _trend(hoje: str, ha1sem: str) -> str:
    try:
        h = float(hoje.replace(",", "."))
        s = float(ha1sem.replace(",", "."))
        return "▲" if h > s else ("▼" if h < s else "→")
    except ValueError:
        return "→"


def _parse_indicators(
    lines: list[str],
    patterns: dict[str, re.Pattern],
    hoj: list[int],
    sem: list[int],
    periods: list[str],
) -> dict:
    result: dict = {}
    for name, pat in patterns.items():
        for line in lines:
            if pat.search(line):
                nums = _NUM.findall(line)
                entry: dict = {}
                for i, period in enumerate(periods):
                    h = _cell(nums, hoj[i])
                    s = _cell(nums, sem[i])
                    if h != "-":
                        entry[period] = {"hoje": h, "ha1sem": s, "trend": _trend(h, s)}
                result[name] = entry
                break
    return result


def _extract_date(text: str) -> str:
    m = _DATE.search(text)
    if not m:
        return ""
    day, month_pt, year = m.groups()
    month = _MONTHS_PT.get(month_pt.lower(), "00")
    return f"{year}-{month}-{int(day):02d}"


def parse_focus(txt_path: Path) -> dict:
    """
    Lê um .txt do Focus e retorna um dict estruturado:

        {
            "date": "2026-06-19",
            "annual":  {indicador: {ano:  {"hoje": str, "ha1sem": str, "trend": str}}},
            "monthly": {indicador: {mês:  {"hoje": str, "ha1sem": str, "trend": str}}},
        }

    Os valores são strings exatamente como aparecem no relatório ("5,33", "-59,60").
    Nenhum número é inventado ou arredondado.
    """
    text = txt_path.read_text(encoding="utf-8")

    # Separa páginas pelo marcador "Pág. X/X"
    parts = _PAGE.split(text)
    page1_lines = parts[0].splitlines() if len(parts) > 0 else []
    page2_lines = parts[1].splitlines() if len(parts) > 1 else []

    return {
        "date":    _extract_date(text),
        "annual":  _parse_indicators(page1_lines, _ANN_PATTERNS, _ANN_HOJ, _ANN_SEM, YEARS),
        "monthly": _parse_indicators(page2_lines, _MON_PATTERNS, _MON_HOJ, _MON_SEM, MONTHS),
    }
