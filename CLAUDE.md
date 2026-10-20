# Boletim Focus — briefing do projeto

## Objetivo
Coletar semanalmente as expectativas da pesquisa Focus do Banco Central,
manter o histórico estruturado, publicar um dashboard e enviar um resumo
executivo por e-mail.

## Fontes
- **Primária** — API de Expectativas de Mercado (Olinda/OData):
  `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata`
  Três endpoints:
  - `ExpectativasMercadoAnuais` — projeções por ano-calendário;
  - `ExpectativaMercadoMensais` — projeções por mês de referência;
  - `ExpectativasMercadoInflacao12Meses` — inflação acumulada nos próximos
    12 meses. **Não traz `DataReferencia`**; distingue as observações por uma
    coluna `Suavizada` (`S`/`N`). O quadro do Focus publica a **suavizada**, e
    é essa que o projeto grava, sob a chave `mensal` / `infl12m` — a mesma que
    o parser do PDF produz, para que a linha da API substitua a do PDF em vez
    de duplicar o indicador.

  `baseCalculo`: `0` = últimos 30 dias, `1` = últimos 5 dias úteis.
- **Arquivo e reserva** — PDF do Focus:
  `https://www.bcb.gov.br/content/focus/focus/R{AAAAMMDD}.pdf`
  (ex.: `R20260911.pdf` para a edição de 11/09/2026).

## Convenções
- Nomes pela **sexta-feira de coleta**, não pela data de publicação:
  `focus_AAAA-MM-DD`. A edição `focus_2026-09-11` é a que o BCB divulgou na
  segunda, 14/09.
- Referência anual: `"2026"`. Referência mensal: `"2026-09"` — a API devolve
  `"09/2026"` e o cliente normaliza. Inflação em 12 meses: `"infl12m"`.
- Histórico em formato **longo**, chave única
  `(data, indicador, horizonte, referencia, base_calculo)`.

## Estrutura
```
src/focus/     pacote (pdf, parser, api, store, analytics, charts,
               dashboard, report, mail, cli, calendario, feriados)
tests/         pytest; os casos apontam para os boletins reais de data/
data/          .txt versionado (serve de fixture); PDFs ignorados;
               history/ com o CSV longo
docs/          dashboard estático publicado no GitHub Pages
output/focus/  .md escrito pelo agente e .html efetivamente enviado
```

## Regras de negócio

### Download
- O Focus é **semanal**: coleta até a sexta, publicação na segunda seguinte —
  em feriado nacional, escorrega para terça ou adiante. O artefato leva o nome
  da **sexta de coleta** (`R20260911.pdf` saiu na segunda, 14/09). O downloader
  recua dia a dia (até 8 dias) em vez de modelar o calendário de feriados.
- Disso decorre que a edição corrente **envelhece a semana inteira**: tem 3
  dias na segunda em que sai e chega a 10 na manhã da segunda seguinte, antes
  da próxima. Nenhum limiar fixo de "dias desde a coleta" funciona — abaixo de
  10 dispara sozinho, acima de 12 demora duas semanas para notar coleta
  travada. Quem responde "o dado está atrasado?" é `focus.calendario`, e ele
  pergunta outra coisa: *é a edição mais recente que já deveria existir?*
- Só aceita resposta que comece com `%PDF` **e** tenha ao menos 50 KB — o
  portal do BCB às vezes devolve página de erro com HTTP 200.

### Feriados nacionais — quando a rotina nem começa
- `focus.feriados` modela o calendário de feriados nacionais do Brasil
  (fixos pela Lei nº 10.607/2002 + Sexta-feira da Paixão, móvel, + Dia
  Nacional de Zumbi e da Consciência Negra desde 2024, Lei nº 14.759/2023).
  Carnaval e Corpus Christi ficam de fora de propósito: são pontos
  facultativos por decreto, não feriados nacionais por lei.
- `python -m focus feriado` devolve código de saída 1 (e nomeia o feriado)
  quando "hoje" é feriado nacional. Os três workflows da cadeia semanal —
  `focus-semanal`, `focus-resumo` e `focus-enviar` — chamam esse comando como
  primeiro passo de trabalho e pulam o resto do job quando ele reprova. Cada
  um checa por conta própria, porque cada um é disparado por `workflow_run`
  do anterior **completar**, não de ele ter feito algo: sem a checagem
  própria, uma segunda de feriado em que a coleta não encontra nada novo
  ainda dispararia o resumo e o envio, que acabariam reprocessando — e
  reenviando — a edição da semana passada.
- Isso não troca a folga de `focus.calendario` (que continua sem modelar
  feriados de propósito, para o diagnóstico de atraso) — resolve um problema
  diferente: não *processar* numa segunda que é feriado, e não só tolerar o
  atraso que isso causa.

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
  p.p. não são comparáveis; `analytics.FAMILIA_UNIDADE` agrupa. A única exceção
  legítima é uma medida **adimensional** — o CV ordena indicadores de escalas
  diferentes porque já não tem unidade.
- **A API entrega dado DIÁRIO, o boletim é semanal.** São ~505 datas em dois
  anos, das quais só ~101 são sextas. Nunca recorte janela por contagem de
  datas disponíveis (`datas[-52:]`): use `analytics.desde_semanas`, que corta
  no calendário, e `analytics.amostrar_semanal` para a cadência do gráfico.
- **CV só onde o CV existe.** `σ/μ` exige escala de razão com média
  estritamente positiva. Em variável que cruza o zero — resultado primário e
  nominal, conta corrente — o denominador tende a zero e a razão explode sem
  que a discordância tenha mudado. `analytics.RAZAO_MINIMA_PARA_CV` guarda
  isso; linhas sem CV publicável mostram o desvio-padrão na unidade original.
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
- **A prosa tem de ser a desta edição, não a mais recente que existir.**
  `cmd_email` resolvia o caminho default com
  `sorted(glob("focus_*.md"), reverse=True)[0]` — "o .md mais recente que
  houver", não "o .md desta data". Quando o agente não escrevia a prosa da
  semana (run #10 de `focus-resumo`, 19/10/2026: a coleta trouxe
  `focus_2026-10-16.txt` e não havia `focus_2026-10-16.md`), o comando caía
  silenciosamente para a prosa da edição anterior e a publicava junto do
  quadro-resumo novo — nenhum número inventado, mas uma narrativa velha
  descrevendo dados novos, o mesmo tipo de falha silenciosa que
  `focus.calendario` e o vigia existem para pegar em download e em entrega.
  Corrigido: o caminho default é exatamente `focus_{data}.md`; sem ele, o
  comportamento é o mesmo de "nenhuma prosa" (`cli.py`, `cmd_email`).
- **Não há rotina externa agendada para este passo.** Até 16/09/2026 (#18)
  não existia `focus-resumo.yml`, e uma rotina do Claude Code fora do
  repositório (agendada às segundas) tentava preencher o vão escrevendo HTML
  à mão e fazendo `git push` direto — os dois hábitos que este arquivo já
  rejeita (ver "Divisão de trabalho" acima e `focus-enviar.yml`, que não
  dispara por push). Essa rotina foi desativada em 20/10/2026: o passo já
  roda dentro do próprio CI (`focus-resumo.yml` chama `claude -p
  "/gerar-resumo"`, contrato em `.claude/commands/gerar-resumo.md`), e manter
  as duas ativas arriscava duplicar o e-mail ou reintroduzir exatamente os
  defeitos que a v2 deste pipeline corrigiu (seta na coluna errada, cor
  invertida — ver histórico de commits de `focus.report`).

### Meta de inflação
Desde janeiro de 2025 vale a **meta contínua**: centro de 3,00% com banda de
±1,5 p.p., avaliada mês a mês sobre o IPCA acumulado em 12 meses. Não descreva
a meta como calendário anual.

O número que a meta avalia é a série `infl12m` — por isso ela vem da API, com
dispersão e histórico, e não mais só do recorte semanal do PDF. É também a
primeira seção do painel: as seções por ano-calendário são úteis, mas nenhuma
delas é o horizonte que o CMN afere.

## Ao mexer no código
- `ruff check .` e `ruff format --check .` são bloqueantes no CI.
- Todo defeito corrigido ganha um teste que nomeia o defeito. Os casos de
  layout não têm cópia própria: `tests/conftest.py` mapeia cada apelido
  (`focus_bloco_vazio.txt`) para a edição real em `data/` que o exercita
  (`focus_2026-09-11.txt`). Por isso os `.txt` de `data/` são versionados e
  **não podem ser removidos** — são as fixtures.
- Não reintroduza dependência de runtime além de `requests` e `pdfplumber`; o
  dashboard precisa continuar sendo um HTML autocontido, sem CDN.
- Constante de módulo usada como valor padrão de argumento fica **amarrada na
  importação**: `def f(p: Path = PASTA_DADOS)` ignora qualquer troca posterior
  de `PASTA_DADOS`, e o teste que pensa estar isolado lê a pasta real. Use
  `p: Path | None = None` e resolva dentro da função.
