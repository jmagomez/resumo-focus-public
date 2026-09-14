"""Pipeline do Boletim Focus (BCB) — coleta, parsing, histórico e publicação.

Camadas:

``focus.pdf``        download do PDF no site do BCB e extração de texto
``focus.parser``     leitura do PDF em estrutura tipada, dirigida pelo cabeçalho
``focus.api``        cliente da API Olinda de Expectativas de Mercado (fonte primária)
``focus.store``      histórico longitudinal em CSV (formato longo, idempotente)
``focus.analytics``  métricas analíticas (revisões, dispersão, gap 5d/30d, ancoragem)
``focus.report``     HTML do e-mail semanal
``focus.dashboard``  dashboard estático autocontido (GitHub Pages)
``focus.cli``        interface de linha de comando que amarra tudo

Regra de ouro do projeto: nenhum número é inventado ou inferido. Toda camada
falha alto (exceção) em vez de devolver valor plausível porém errado.
"""

__all__ = [
    "analytics",
    "api",
    "cli",
    "dashboard",
    "parser",
    "pdf",
    "report",
    "store",
]

__version__ = "2.0.0"
