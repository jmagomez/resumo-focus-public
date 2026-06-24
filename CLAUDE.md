# Boletim Focus — Briefing do Projeto

## Objetivo
Baixar o Boletim Focus do Banco Central do Brasil toda segunda-feira, extrair o texto do PDF e gerar um resumo executivo em Markdown.

## Fonte
- Página oficial: https://www.bcb.gov.br/publicacoes/focus
- Padrão de URL do PDF: `https://www.bcb.gov.br/content/focus/focus/R{AAAAMMDD}.pdf`
  - Exemplo: `R20260622.pdf` para a edição de 22 de junho de 2026.

## Convenções de nomenclatura
- Arquivos nomeados com a data de publicação: `focus_AAAA-MM-DD`
  - PDF baixado: `data/focus_AAAA-MM-DD.pdf`
  - Texto extraído: `data/focus_AAAA-MM-DD.txt`
  - Resumo gerado: `output/focus/focus_AAAA-MM-DD.md`

## Estrutura de pastas
```
Projeto_BoletimFocus/
├── src/                  # código-fonte
├── tests/                # testes automatizados
├── data/                 # PDFs e textos extraídos
├── output/
│   └── focus/            # resumos em Markdown
└── .github/
    └── workflows/        # pipelines de CI/CD e agendamento
```

## Regras de negócio

### Download
- A publicação ocorre toda **segunda-feira**.
- Se a segunda-feira for feriado nacional, o BCB publica na **terça-feira**.
- Estratégia de busca: tentar a data-alvo e, em caso de 404, **retroceder dia a dia** até encontrar o PDF (máximo de 7 dias para trás).

### Extração e resumo
- **Nunca inventar números**: toda mediana ou estatística citada no resumo deve estar literalmente presente no texto extraído do PDF.
- O resumo deve ser fiel ao conteúdo do boletim, sem inferências ou projeções adicionais.
