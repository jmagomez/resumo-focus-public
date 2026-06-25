# Boletim Focus — Pipeline Automatizado

Pipeline que baixa semanalmente o **Boletim Focus** do Banco Central do Brasil, extrai o texto do PDF e, numa automação agendada na nuvem, gera um resumo executivo e o envia por e-mail.

## Como funciona

```
Segunda-feira
     │
     ▼
src/baixar_focus.py          ← baixa o PDF do BCB (faz fallback em feriados)
     │
     ▼
src/extrair_texto.py         ← extrai o texto bruto do PDF com pdfplumber
     │
     ▼
Agente Claude (nuvem)        ← lê o texto e escreve o resumo executivo
     │                          os números vêm literalmente do boletim,
     │                          sem inferências ou invenções
     ▼
output/focus/focus_AAAA-MM-DD.md   ← resumo em Markdown
     │
     ▼
jmagomez@gmail.com           ← rascunho de e-mail com o resumo
```

> **Importante:** os scripts Python apenas baixam e extraem dados.
> O resumo executivo é produzido por um agente de IA (Claude) que lê o
> texto extraído — nenhum número é inventado ou inferido.

## Estrutura de pastas

```
Projeto_BoletimFocus/
├── src/
│   ├── baixar_focus.py      # download do PDF do BCB com fallback de até 7 dias
│   ├── extrair_texto.py     # extração de texto do PDF via pdfplumber
│   ├── parser.py            # parser de medianas estruturadas do boletim
│   ├── dashboard.py         # dashboard Streamlit com expectativas de mercado
│   ├── downloader.py        # módulo interno de download (usado nos testes)
│   └── extractor.py         # módulo interno de extração (usado nos testes)
├── tests/
│   ├── test_baixar_focus.py # testes de última_segunda e download real
│   ├── test_downloader.py   # testes unitários do downloader
│   └── test_extractor.py    # testes unitários do extractor
├── data/                    # PDFs e TXTs baixados (gerados em runtime)
├── output/
│   └── focus/               # resumos em Markdown — versionados no repositório
├── .github/
│   └── workflows/
│       └── focus-download.yml  # GitHub Action: baixa e extrai toda segunda
├── demo.py                  # roda o pipeline completo localmente
└── requirements.txt
```

## Como rodar localmente

```bash
# 1. Instale as dependências
pip install -r requirements.txt

# 2. Rode o pipeline (baixa o PDF e extrai o texto)
python demo.py

# 3. Abre o .txt no navegador ao final
python demo.py --abrir

# 4. Sobe o dashboard interativo
streamlit run src/dashboard.py
```

## Como rodar os testes

```bash
# Testes offline (rápidos, sem rede)
pytest -m "not network" -v

# Teste de rede — faz o download real do BCB
pytest -m network -v

# Todos os testes
pytest -v
```
