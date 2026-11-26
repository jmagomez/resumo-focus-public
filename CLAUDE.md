# Boletim Focus — guia completo do projeto

Este arquivo é o ponto de entrada para qualquer IA ou humano que trabalhe neste
repositório. Leia-o antes de qualquer outra coisa. Ele é a fonte de verdade sobre
arquitetura, workflows, regras de negócio e histórico de decisões.

---

## Objetivo

Coletar semanalmente as expectativas da pesquisa Focus do Banco Central,
manter o histórico estruturado, publicar um dashboard estático e enviar um
resumo executivo por e-mail aos analistas de mercado.

---

## Cadeia de publicação — mapa dos workflows

Seis workflows existem no repositório. Quatro formam a cadeia principal; dois
são auxiliares.

```
                      (todo dia 12h BRT)
                      focus-vigia.yml  ──► e-mail de alerta se parado

(seg–qua 09h15 BRT)
focus-semanal.yml    baixa PDF, extrai .txt, sincroniza histórico, gera dashboard
        │
        ├── workflow_run: completed ──► pages.yml   build + deploy → GitHub Pages
        │
        └── workflow_run: completed
                │
        focus-resumo.yml    chama Claude Code /gerar-resumo → escreve .md
                │
                └── workflow_run: completed
                        │
                focus-enviar.yml    monta HTML, envia e-mail, commita HTML
```

**Trigger de cada workflow:**

| Workflow | Trigger principal | Agendamento |
|---|---|---|
| `focus-semanal.yml` | `schedule` | `15 12 * * 1-3` (seg–qua) |
| `focus-resumo.yml` | `workflow_run` de focus-semanal | — |
| `focus-enviar.yml` | `workflow_run` de focus-resumo | — |
| `pages.yml` | `workflow_run` de Coleta semanal + `push docs/**` | — |
| `focus-vigia.yml` | `schedule` | `0 15 * * *` (diário) |
| `ci.yml` | `push`/`pull_request` + `schedule` | `0 13 * * 1` (seg) |

**Por que `workflow_run` e não `push`:** a coleta commita com o
`GITHUB_TOKEN` padrão, e o GitHub não dispara outros workflows a partir de
eventos gerados por esse token (prevenção de recursão). `workflow_run` é
imune: dispara na conclusão do workflow, não no push.

**Checagem de feriado em cada elo:** `workflow_run` dispara inclusive quando
o workflow anterior pulou o próprio trabalho (feriado nacional). Por isso
`focus-resumo.yml` e `focus-enviar.yml` fazem a checagem `python -m focus
feriado` por conta própria, antes de qualquer passo de trabalho.

---

## Fontes de dados

**Primária — API de Expectativas de Mercado (Olinda/OData):**
`https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata`

Três endpoints utilizados:
- `ExpectativasMercadoAnuais` — projeções por ano-calendário
- `ExpectativaMercadoMensais` — projeções por mês de referência
- `ExpectativasMercadoInflacao12Meses` — inflação acumulada nos próximos 12
  meses. **Não traz `DataReferencia`**; distingue observações pela coluna
  `Suavizada` (`S`/`N`). O quadro do Focus publica a suavizada — é essa que o
  projeto grava sob a chave `mensal` / `infl12m`.

`baseCalculo`: `0` = últimos 30 dias, `1` = últimos 5 dias úteis.

**Reserva — PDF do Focus:**
`https://www.bcb.gov.br/content/focus/focus/R{AAAAMMDD}.pdf`
(ex.: `R20260911.pdf` = edição de 11/09/2026, divulgada 14/09)

O PDF não é mais commitado. Vira artifact do workflow com retenção de 90 dias.
O repositório versiona só o `.txt` extraído (~12 KB contra ~780 KB do PDF).

---

## Convenções de nomenclatura

- Nomes pela **sexta-feira de coleta**, nunca pela data de publicação:
  `focus_AAAA-MM-DD`. A edição `focus_2026-09-11` é a que o BCB divulgou na
  segunda-feira, 14/09.
- **Exceção: sexta que é feriado.** O BCB data a edição pelo último dia útil
  da semana. A semana de 20/11/2026 (Consciência Negra) gerou
  `focus_2026-11-19` — quinta. Nenhum código pode supor "edição = sexta":
  a unidade é a **semana** (seg–sex), e a edição é a última data dela.
- Referência anual: `"2026"`. Referência mensal: `"2026-09"` (a API devolve
  `"09/2026"` e o cliente normaliza). Inflação 12 meses: `"infl12m"`.
- Histórico em formato **longo**, chave única
  `(data, indicador, horizonte, referencia, base_calculo)`.

---

## Estrutura de diretórios

```
src/focus/        pacote principal
  __init__.py     versão e re-exportações públicas
  cli.py          entry-point: python -m focus <subcomando>
  api.py          cliente da API Olinda/OData
  pdf.py          download e validação do PDF
  parser.py       extração do texto do PDF
  store.py        leitura/escrita do CSV histórico longo
  analytics.py    cálculos: revisão, dispersão, ranking, CV
  charts.py       gráficos SVG inline para o dashboard
  dashboard.py    geração do docs/index.html
  report.py       montagem do HTML do e-mail
  mail.py         envio via SMTP (Gmail)
  calendario.py   diagnóstico de atraso (sem modelar feriados)
  feriados.py     feriados nacionais brasileiros

tests/            pytest; aponta para boletins reais em data/
data/             .txt versionado (fixtures); PDFs ignorados pelo .gitignore
                  history/ com o CSV longo do histórico
docs/             dashboard estático publicado no GitHub Pages
output/focus/     .md escrito pelo agente; .html efetivamente enviado
.claude/commands/ comandos slash para o Claude Code
  gerar-resumo.md contrato do agente (/gerar-resumo)
```

---

## Comandos de desenvolvimento

```bash
# Instalar em modo editável (uma vez)
pip install -e .
pip install -r requirements-dev.txt

# Lint — bloqueante no CI
ruff check .
ruff format --check .

# Corrigir automaticamente (nunca no CI, apenas local)
ruff check --fix .
ruff format .

# Testes offline (sem bater na API do BCB)
pytest -q

# Testes de contrato com a API (requer internet)
pytest -m network -q
```

Python mínimo: **3.11** (CI roda 3.11 e 3.12). O target-version do ruff é
`py311` pelo mesmo motivo.

---

## Comandos CLI do projeto

Todos via `python -m focus <subcomando>`:

| Subcomando | O que faz | Código de saída |
|---|---|---|
| `baixar` | Baixa o PDF mais recente, extrai o `.txt` | 0 se ok, 1 se falha |
| `sincronizar` | Merge API + PDF no histórico longo (`data/history/`) | — |
| `dashboard` | Gera `docs/index.html` a partir do histórico | — |
| `email [--dry-run]` | Monta e envia o HTML do e-mail | — |
| `email --dry-run` | **Exibe os números sem gravar nenhum arquivo nem enviar** | — |
| `verificar` | Coleta e histórico na semana esperada (`focus.calendario`) e `data_html ≥ data_coletada` | 0 ok / 1 parado |
| `feriado` | Hoje é feriado nacional? Imprime o nome e retorna 1 se sim | 0 não-feriado / 1 feriado |

**Detalhe crítico sobre `--dry-run`:** antes de outubro de 2026, o dry-run
escrevia o arquivo HTML como efeito colateral, imprimindo "HTML gravado:".
Isso confundia o agente, que interpretava a mensagem como prova de tarefa
concluída e não escrevia o `.md`. **Corrigido em `cli.py`:** o dry-run agora
retorna antes do `write_text` — só exibe os números. O HTML de envio é
gerado exclusivamente pelo `focus-enviar.yml`, nunca pelo dry-run.

---

## Regras de negócio

### Feriados nacionais — quando a rotina nem começa

`focus.feriados` modela os feriados nacionais do Brasil (fixos pela Lei
nº 10.607/2002 + Sexta-feira da Paixão, móvel + Dia de Zumbi desde 2024,
Lei nº 14.759/2023). Carnaval e Corpus Christi ficam fora: são pontos
facultativos, não feriados por lei.

`python -m focus feriado` retorna código 1 (e nomeia o feriado) quando hoje é
feriado nacional. Os três workflows da cadeia chamam esse comando como primeiro
passo e pulam o restante do job quando ele reprova.

Cada workflow checa individualmente porque `workflow_run` dispara inclusive
quando o antecessor pulou o próprio trabalho — sem a checagem própria, o
seguinte reprocessaria e reenviaria a edição da semana passada.

Isso é diferente de `focus.calendario`, que diagnostica atraso sem modelar
feriados: os dois módulos resolvem problemas distintos.

### Download

- O Focus é **semanal**: coleta na sexta, publicação na segunda (ou terça, em
  feriado). O artefato leva o nome da sexta de coleta.
- O downloader recua dia a dia (até 8 dias) em vez de modelar o calendário.
- Só aceita resposta que comece com `%PDF` **e** tenha ao menos 50 KB — o
  portal do BCB às vezes devolve página de erro com HTTP 200.
- A edição corrente "envelhece" a semana inteira: `focus.calendario` pergunta
  "é a edição mais recente que já deveria existir?", não "há quantos dias foi
  coletada?".

### Parsing

- Os períodos de referência e o formato das colunas são lidos do **cabeçalho do
  próprio PDF**. Nunca codifique ano ou mês no fonte.
- Ao encontrar layout fora da gramática esperada, levante
  `LayoutDesconhecidoError`. Interromper o pipeline é preferível a publicar
  número plausível e errado.
- Guarde o valor **literal** (`"5,02"`) ao lado do numérico. É o literal que
  vai para o texto.

### Análise e apresentação

- **Nunca misture unidades num mesmo eixo ou ranking.** `+1,67 US$ bi` e
  `+0,10 p.p.` não são comparáveis; `analytics.FAMILIA_UNIDADE` agrupa.
- **A API entrega dado DIÁRIO, o boletim é semanal.** Nunca recorte janela por
  contagem de datas (`datas[-52:]`): use `analytics.desde_semanas` e
  `analytics.amostrar_semanal`.
- **CV só onde o CV existe.** `σ/μ` exige escala de razão com média
  estritamente positiva. Em variável que cruza o zero (resultado primário,
  conta corrente), o denominador tende a zero e a razão explode.
  `analytics.RAZAO_MINIMA_PARA_CV` guarda isso.
- **Comparação entre edições casa pela semana, nunca por "data − 7 dias".**
  O histórico é diário; "há 1/4/13 semanas" é a última data da semana-alvo
  (`analytics._edicao_da_semana`, mesmo critério de `amostrar_semanal`).
  Mirar a data exata acertava só por coincidência quando a edição era sexta;
  com a edição de quinta (19/11/2026) a revisão saiu contra o dia 12/11 em vez
  da edição de 13/11 — 88 de 144 séries anuais erradas, 19 com sinal trocado.
- Quando a edição da semana anterior não existir no histórico, use a mais
  próxima **e registre qual foi** (`Revisao.data_1_semana`,
  `Revisao.comparacao_exata`, que mede distância em semanas, não em dias).
- Cor no e-mail segue o **sentido econômico**, não a direção: queda do IPCA é
  verde; queda do PIB é vermelha. Ver `analytics.ALTA_E_DESFAVORAVEL`.
- A seta acompanha a mediana de hoje, nunca a coluna da semana anterior.

### Meta de inflação

Desde janeiro de 2025 vale a **meta contínua**: centro de 3,00% com banda de
±1,5 p.p., avaliada mês a mês sobre o IPCA acumulado em 12 meses. Não descreva
a meta como calendário anual. O número que a meta avalia é a série `infl12m` —
por isso ela vem da API, com dispersão e histórico, e não mais só do recorte
semanal do PDF.

### Divisão de trabalho com o agente

- **O agente escreve prosa; o código escreve números.** O agente entrega
  `output/focus/focus_AAAA-MM-DD.md`. Todo o HTML, o quadro-resumo, as setas e
  as cores são gerados por `focus.report`.
- **Nunca invente número.** Todo valor citado deve estar literalmente na saída
  de `python -m focus email --dry-run` ou no `.txt` do boletim.
- **A prosa tem de ser a desta edição.** `cmd_email` resolve o caminho default
  como `focus_{data}.md` exato — sem ele, o comportamento é "nenhuma prosa",
  não "pegar a mais recente" (bug histórico corrigido em outubro de 2026).
- **Não há rotina externa agendada.** A rotina de Claude Code que existia fora
  do repositório (agendada às segundas) foi desativada em 20/10/2026. O passo
  roda dentro do CI (`focus-resumo.yml` chama `claude -p "/gerar-resumo"`).

---

## Secrets necessários (GitHub Actions)

| Secret | Usado em | Para quê |
|---|---|---|
| `ANTHROPIC_API_KEY` | `focus-resumo.yml` | Autenticar o Claude Code |
| `FOCUS_SMTP_USER` | `focus-enviar.yml`, `focus-semanal.yml`, `focus-vigia.yml` | Usuário Gmail SMTP |
| `FOCUS_SMTP_APP_PASSWORD` | idem | Senha de app Gmail |
| `FOCUS_EMAIL_DEST` | idem | Destinatário do e-mail |
| `FOCUS_EMAIL_BCC` | `focus-enviar.yml` | BCC opcional |

Configure em **Settings → Secrets and variables → Actions**.

---

## Recuperação manual (runbook)

### Pipeline parado (focus-vigia dispara alerta)

1. Cheque `python -m focus verificar` localmente para identificar onde parou.
2. Se faltou `.txt` (ou o dashboard precisa ser regerado): dispare
   `focus-semanal` com `ignorar_feriado: true`. Sem o input, fora do dia de
   execução o workflow pula todos os passos e não faz nada.
3. Se faltou `.md`: dispare `focus-resumo` com `ignorar_feriado: true`.
4. Se faltou o envio: dispare `focus-enviar` com `ignorar_feriado: true`.

**`ignorar_feriado: true`** está disponível como input `workflow_dispatch` nos
três elos: `focus-semanal.yml`, `focus-resumo.yml` e `focus-enviar.yml`. Use
para recuperações em dias não designados (fins de semana, quintas, sextas,
feriados).

**Cuidado com e-mail duplicado.** Disparar `focus-semanal` encadeia
`focus-resumo` e `focus-enviar` por `workflow_run`. Fora do dia de execução
eles pulam sozinhos (o input não se propaga) — é o que permite regerar só o
dashboard. Num dia de execução (segunda comum), os dois rodam e o e-mail sai
de novo.

### Sextas-feiras feriado à vista (vigiar o pipeline nessas semanas)

| Sexta | Feriado | Edição esperada |
|---|---|---|
| 25/12/2026 | Natal | provavelmente 23 ou 24/12 (24/12 é ponto facultativo) |
| 01/01/2027 | Confraternização | provavelmente 30 ou 31/12 (31/12 é ponto facultativo) |
| 26/03/2027 | Sexta-feira da Paixão | provavelmente 25/03 |

O vigia e as revisões já aceitam qualquer dia da semana; confira só se o
downloader encontrou o PDF (ele recua até 8 dias).

### Semana sem boletim — reprocessar edição específica

```bash
# 1. Garantir que o .txt existe
python -m focus baixar          # baixa a edição mais recente

# 2. Ver os números sem enviar
python -m focus email --dry-run

# 3. Escrever o .md manualmente (ou via /gerar-resumo no Claude Code)
# Arquivo: output/focus/focus_AAAA-MM-DD.md

# 4. Montar e enviar
python -m focus email --url-dashboard https://jmagomez.github.io/resumo-focus-public/
```

---

## Ao mexer no código

- `ruff check .` e `ruff format --check .` são **bloqueantes** no CI.
- Todo defeito corrigido ganha um teste que nomeia o defeito.
- Os `.txt` em `data/` são as fixtures dos testes — **não os remova**.
  `tests/conftest.py` mapeia apelidos (`focus_bloco_vazio.txt`) para edições
  reais (`focus_2026-09-11.txt`).
- Não reintroduza dependências de runtime além de `requests` e `pdfplumber`.
  O dashboard precisa continuar sendo um HTML autocontido, sem CDN.
- Constante de módulo como valor padrão de argumento fica amarrada na
  importação: use `p: Path | None = None` e resolva dentro da função.
- O dashboard não usa CDN; os gráficos são SVGs inline gerados por
  `focus.charts`. Isso não é uma limitação — é um requisito para que o HTML
  possa ser enviado por e-mail sem depender de servidor externo.

---

## Histórico de decisões arquiteturais (ADRs)

### ADR-01 — API como fonte primária, PDF como reserva (set/2026)

**Contexto:** o parser do PDF dependia de rótulos fixos no layout; qualquer
reformatação do BCB quebrava a coleta silenciosamente.

**Decisão:** a API Olinda/OData passa a ser a fonte primária. O parser do PDF
entra como reserva quando a API está fora do ar. `--exigir-api` está
disponível, mas desligado na coleta automática para tolerar instabilidade do
serviço.

**Consequência:** a série `infl12m` agora vem da API com histórico completo e
dispersão, em vez de só do recorte semanal do PDF.

### ADR-02 — PDF não versionado, apenas o .txt (set/2026)

**Contexto:** cada PDF pesava ~780 KB; o repositório acumulava centenas de
edições.

**Decisão:** o PDF vira artifact do workflow (retenção 90 dias). O repositório
versiona apenas o `.txt` extraído (~12 KB por edição).

### ADR-03 — focus-resumo.yml como elo explícito da cadeia (set/2026)

**Contexto:** o `focus-enviar` esperava um `output/focus/focus_*.md` que
nenhum workflow escrevia. Os boletins eram montados à mão. Depois de
31/07/2026, silêncio — o pipeline seguiu coletando e parou de publicar por
seis semanas sem que nada reclamasse.

**Decisão:** criar o `focus-resumo.yml` como elo explícito, com o Claude Code
escrevendo o `.md` via `/gerar-resumo`, e adicionar verificação explícita de
que o arquivo foi criado antes de prosseguir.

### ADR-04 — focus-vigia.yml como watchdog diário (set/2026)

**Contexto:** o único alerta existente cobria falha de download. O pipeline
pode parar em qualquer elo posterior sem que o download falhe.

**Decisão:** watchdog diário às 12h BRT que roda `python -m focus verificar`.
Falha se `data_html < data_coletada` (pipeline travado em qualquer elo).

### ADR-05 — workflow_run em vez de push para a cadeia (set/2026)

**Contexto:** o GitHub não dispara workflows a partir de eventos gerados pelo
`GITHUB_TOKEN` padrão.

**Decisão:** toda a cadeia usa `workflow_run` ao invés de `push`. Efeito
colateral: cada elo dispara inclusive quando o antecessor pulou o trabalho
(feriado). Contramedida: cada elo faz a checagem `python -m focus feriado`
por conta própria.

### ADR-06 — ignorar_feriado como input de recuperação (out/2026)

**Contexto:** a cadeia completa rodou em um sábado de recuperação. O
`focus-resumo` aceitou `ignorar_feriado=true`, mas o `focus-enviar` disparado
automaticamente em seguida (via `workflow_run`) não tinha o input — e
bloqueou o envio.

**Decisão:** adicionar `ignorar_feriado` como `workflow_dispatch` input tanto
em `focus-resumo.yml` quanto em `focus-enviar.yml`. Para recuperações manuais
completas, disparar os dois com o input ativado.

### ADR-07 — dry-run não escreve HTML (out/2026)

**Contexto:** `python -m focus email --dry-run` escrevia o arquivo HTML como
efeito colateral, imprimindo "HTML gravado:". O agente interpretava essa
mensagem como conclusão da tarefa e não escrevia o `.md`.

**Decisão:** mover o early return do dry-run para **antes** do
`destino_html.write_text()` em `cli.py`. O dry-run agora exibe apenas os
números. O HTML de envio é responsabilidade exclusiva do `focus-enviar.yml`.

### ADR-08 — pages.yml com dois jobs separados (nov/2026)

**Contexto:** `upload-pages-artifact` e `deploy-pages` rodavam no mesmo job.
O upload completava com sucesso, mas `deploy-pages` consultava a API de
metadata imediatamente e recebia 0 artifacts (consistência eventual — o índice
ainda não havia propagado). Resultado: `Found 0 artifact(s)`, falha no deploy.

**Decisão:** separar em dois jobs (`build` + `deploy`) com `needs: build`. O
`needs` cria uma barreira de sincronização: quando `deploy` inicia, `build`
encerrou completamente e todos os artifacts estão totalmente indexados na API.
Esta é a arquitetura recomendada pela documentação oficial do GitHub para Pages.

### ADR-09 — A unidade é a semana, não a sexta (nov/2026)

**Contexto:** a sexta 20/11/2026 foi feriado e o BCB datou a edição de 19/11.
Dois pontos supunham "edição = sexta": (1) `calendario.esta_atrasado` cobrava
a edição de 2026-11-20, e o vigia alarmou de 25/11 em diante (run #71) com tudo
em dia; o selo do dashboard usa a mesma função e alarmaria se regerado nesses
dias; (2) `analytics.revisoes` buscava "data − 7 dias" no histórico diário e
comparou 19/11 com 12/11 em vez da edição de 13/11 — painel e e-mail de 23/11
publicaram revisões erradas em 88 de 144 séries anuais (19 com sinal trocado).

**Decisão:** sem modelar feriados (pontos facultativos como 24/12, 31/12 e
Carnaval não estão em lei), toda lógica de edição trabalha com a **semana**:
o vigia aceita qualquer edição datada na semana esperada; as comparações usam
a última data da semana-alvo. `focus-semanal.yml` ganhou `ignorar_feriado`
(o único elo que não tinha) para permitir regerar o dashboard fora do dia de
execução.

**Consequência:** detecção de coleta travada inalterada (o atraso real fica
numa semana anterior). O HTML do e-mail de 19/11 em `output/focus/` ficou com
os números antigos — é o registro do que foi enviado e não deve ser reescrito.
