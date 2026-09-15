# Boletim Focus — briefing do projeto

## Objetivo
Coletar semanalmente as expectativas da pesquisa Focus do Banco Central,
manter o histórico estruturado, publicar um dashboard e enviar um resumo
executivo por e-mail.

## Fontes
- **Primária** — API de Expectativas de Mercado (Olinda/OData):
  `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata`
  Endpoints usados: `ExpectativasMercadoAnuais`, `ExpectativaMercadoMensais`.
  `baseCalculo`: `0` = últimos 30 dias, `1` = últimos 5 dias úteis.
- **Arquivo e reserva** — PDF do Focus:
  `https://www.bcb.gov.br/content/focus/focus/R{AAAAMMDD}.pdf`
  (ex.: `R20260911.pdf` para a edição de 11/09/2026).

## Convenções
- Nomes por data de publicação: `focus_AAAA-MM-DD`.
- Referência anual: `"2026"`. Referência mensal: `"2026-09"` — a API devolve
  `"09/2026"` e o cliente normaliza.
- Histórico em formato **longo**, chave única
  `(data, indicador, horizonte, referencia, base_calculo)`.

## Estrutura
```
src/focus/     pacote (pdf, parser, api, store, analytics, charts,
               dashboard, report, mail, cli)
tests/         pytest; os casos apontam para os boletins reais de data/
data/          .txt versionado (serve de fixture); PDFs ignorados;
               history/ com o CSV longo
docs/          dashboard estático publicado no GitHub Pages
output/focus/  .md escrito pelo agente e .html efetivamente enviado
```

## Regras de negócio

### Download
- Publicação na segunda-feira; em feriado nacional, escorrega para terça ou
  adiante. O downloader recua dia a dia (até 8 dias) em vez de modelar o
  calendário de feriados.
- Só aceita resposta que comece com `%PDF` **e** tenha ao menos 50 KB — o
  portal do BCB às vezes devolve página de erro com HTTP 200.

### Parsing
- Os períodos de referência e o formato das colunas são lidos do **cabeçalho do
  próprio PDF**. Nunca codifique ano ou mês no fonte: foi assim que os rótulos
  mensais ficaram três meses defasados sem que nada falhasse.
- Ao encontrar layout que não fecha com a gramática esperada, levante
  `LayoutDesconhecidoError`. Interromper o pipeline é preferível a publicar
  número plausível e errado.
- Guarde o valor **literal** (`"5,02"`) ao lado do numérico. É o literal que vai
  para o texto.

### Análise e apresentação
- **Nunca misture unidades num mesmo eixo ou ranking.** +1,67 US$ bi e +0,10
  p.p. não são comparáveis; `analytics.FAMILIA_UNIDADE` agrupa.
- Quando a edição da semana anterior não existir no histórico, use a mais
  próxima **e registre qual foi** (`Revisao.data_1_semana`,
  `Revisao.comparacao_exata`).
- Cor no e-mail segue o **sentido econômico**, não a direção: queda do IPCA é
  verde; queda do PIB é vermelha. Ver `analytics.ALTA_E_DESFAVORAVEL`.
- A seta acompanha a mediana de hoje, nunca a coluna da semana anterior.

### Divisão de trabalho com o agente
- **O agente escreve prosa; o código escreve números.** O agente entrega
  `output/focus/focus_AAAA-MM-DD.md` com resumo e bullets de revisão. Todo o
  HTML, o quadro-resumo, as setas e as cores são gerados por `focus.report`.
- **Nunca invente número**: todo valor citado deve estar literalmente na saída
  de `python -m focus email --dry-run` ou no `.txt` do boletim.

### Meta de inflação
Desde janeiro de 2025 vale a **meta contínua**: centro de 3,00% com banda de
±1,5 p.p., avaliada mês a mês sobre o IPCA acumulado em 12 meses. Não descreva
a meta como calendário anual.

## Ao mexer no código
- `ruff check .` e `ruff format --check .` são bloqueantes no CI.
- Todo defeito corrigido ganha um teste que nomeia o defeito. Os casos de
  layout não têm cópia própria: `tests/conftest.py` mapeia cada apelido
  (`focus_bloco_vazio.txt`) para a edição real em `data/` que o exercita
  (`focus_2026-09-11.txt`). Por isso os `.txt` de `data/` são versionados e
  **não podem ser removidos** — são as fixtures.
- Não reintroduza dependência de runtime além de `requests` e `pdfplumber`; o
  dashboard precisa continuar sendo um HTML autocontido, sem CDN.
