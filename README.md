# Boletim Focus — pipeline de expectativas de mercado

Coleta semanal das expectativas da pesquisa **Focus** do Banco Central do
Brasil, com histórico longitudinal, dashboard público e resumo executivo por
e-mail.

📊 **Dashboard:** https://jmagomez.github.io/resumo-focus-public/

---

## Como funciona

```
segunda-feira, 09h15 BRT
          │
          ├─► API de Expectativas (Olinda)  ──┐   fonte primária:
          │   mediana · média · desvio-padrão │   estruturada, com dispersão
          │   mín/máx · respondentes          │   e histórico completo
          │   bases de 30 dias e 5 dias úteis │
          │                                   ├─► data/history/expectativas.csv
          └─► PDF do Focus  ──────────────────┘   (formato longo, idempotente)
              baixado e arquivado como               │
              prova documental; parser é reserva     │
                                                     ├─► docs/index.html
                                                     │   dashboard estático
                                                     │
          agente de IA lê o histórico  ──────────────┤
          e escreve a prosa da semana                │
          output/focus/focus_AAAA-MM-DD.md           │
                                                     ▼
                              código monta o HTML e envia o e-mail
```

**O agente escreve texto; o código escreve os números.** Toda tabela, todo
percentual e toda seta do e-mail saem do histórico já validado. O agente
contribui com interpretação — resumo executivo e hipóteses para as revisões.

---

## Fontes

| Fonte | Papel | O que traz |
|---|---|---|
| [API de Expectativas de Mercado](https://dadosabertos.bcb.gov.br/dataset/expectativas-mercado) (Olinda/OData) | primária | mediana, média, desvio-padrão, mínimo, máximo, nº de respondentes, bases de 30 dias e de 5 dias úteis, série histórica completa |
| [Focus — Relatório de Mercado](https://www.bcb.gov.br/publicacoes/focus) (PDF) | arquivo e reserva | o quadro publicado; usado para auditoria e quando a API está fora do ar |

---

## Uso

```bash
pip install -r requirements.txt

python -m focus baixar        # PDF do BCB → data/, e extrai o .txt
python -m focus sincronizar   # API (+ PDF como reserva) → data/history/
python -m focus dashboard     # histórico → docs/index.html
python -m focus email --dry-run
python -m focus verificar     # diagnóstico: o pipeline está entregando?
```

Todo comando devolve código de saída diferente de zero quando o passo falha.

### Testes

```bash
pip install -r requirements-dev.txt

pytest                 # 90 testes offline, ~0,6 s
pytest -m network      # contrato contra a API real do BCB
ruff check . && ruff format --check .
```

Cada teste nomeia o defeito que cobre. Os casos de layout do parser **não têm
fixture própria**: `tests/conftest.py` mapeia cada apelido para a edição real
do Focus, em `data/`, que o exercita — `focus_bloco_vazio.txt` é o boletim de
11/09/2026, em que a Selic mensal traz `- - -` para outubro. Por isso os `.txt`
de `data/` são versionados e não devem ser removidos.

---

## Estrutura

```
src/focus/
  pdf.py         download do PDF e extração de texto
  parser.py      leitura do PDF dirigida pelo cabeçalho, com falha alta
  api.py         cliente da API Olinda de Expectativas
  store.py       histórico longitudinal em CSV longo, idempotente
  analytics.py   revisões, amplitude, gap 5d/30d, dispersão, ancoragem
  charts.py      gráficos SVG sem dependência de runtime
  dashboard.py   dashboard estático autocontido
  report.py      HTML do e-mail
  mail.py        envio via SMTP
  cli.py         `python -m focus ...`

data/
  focus_*.txt            texto extraído (versionado; 12 KB por edição).
                         Quatro deles são as fixtures do conjunto de testes.
  history/               histórico estruturado das expectativas
docs/index.html          dashboard publicado
output/focus/*.md        prosa escrita pelo agente
output/focus/*.html      e-mail efetivamente enviado
```

Os PDFs **não são versionados** desde a v2 (≈780 KB por edição, ≈40 MB por ano).
Cada execução guarda o PDF como *artifact* do workflow, com 90 dias de retenção.

---

## Leitura do dashboard

| Métrica | O que responde |
|---|---|
| **Revisão** (1, 4 e 13 semanas) | quanto a mediana se moveu. Uma semana costuma ser ruído; 13 semanas cobrem o intervalo entre reuniões do Copom |
| **Amplitude** | quantos horizontes foram revisados para cada lado. Revisão difusa e revisão concentrada têm leituras opostas |
| **Gap 5 dias × 30 dias** | a base curta incorpora informação nova antes da mediana cheia; gap persistente de mesmo sinal antecede a revisão |
| **Dispersão** (coef. de variação) | discordância entre analistas. Mediana parada com dispersão subindo indica distribuição se abrindo antes de a mediana se mover |
| **Ancoragem** | distância da expectativa de IPCA à meta por horizonte. Sob a **meta contínua** (desde jan/2025), o centro é 3,00% com banda de ±1,5 p.p. |

Gráficos nunca misturam unidades num mesmo eixo: uma revisão de +1,67 US$ bi na
balança comercial e uma de +0,10 p.p. no IPCA não são comparáveis, e ordená-las
juntas por magnitude colocaria o saldo comercial no topo de qualquer ranking.

---

## Segredos do repositório

`Settings → Secrets and variables → Actions`

| Segredo | Uso |
|---|---|
| `FOCUS_SMTP_USER` | endereço Gmail do remetente |
| `FOCUS_SMTP_APP_PASSWORD` | senha de app do Google (não a senha da conta) |
| `FOCUS_EMAIL_DEST` | destinatários, separados por vírgula |
| `FOCUS_EMAIL_BCC` | opcional, cópia oculta |

Nenhum endereço ou credencial aparece no código ou nos arquivos do repositório.

---

## Workflows

| Workflow | Quando | O que faz |
|---|---|---|
| `focus-semanal` | segunda, 09h15 BRT | baixa, extrai, sincroniza, gera o dashboard e commita |
| `focus-enviar` | push de `output/focus/*.md` | monta o HTML e envia o e-mail |
| `focus-vigia` | diariamente, 12h BRT | verifica se o pipeline está **entregando** e avisa quando para |
| `ci` | push, PR e semanalmente | ruff (bloqueante), pytest e contrato da API |
| `pages` | push em `docs/` | publica o dashboard |

O `focus-vigia` existe por um motivo específico: entre 31/07 e 11/09 de 2026 o
repositório continuou baixando PDFs toda semana e não publicou nenhum resumo.
Seis semanas sem entrega e nenhum alerta, porque o único alerta configurado
cobria a falha do download — e o download estava funcionando.

---

## Garantias de integridade

* Nenhum número é estimado, interpolado ou arredondado além das casas
  publicadas pelo BCB. O parser guarda o valor **literal** (`"5,02"`) junto com
  a forma numérica, e é o literal que deve ser citado em texto.
* O parser lê os períodos de referência **do cabeçalho do próprio PDF**. Antes
  eles eram constantes no código, e os rótulos mensais ficaram três meses
  defasados sem que nada falhasse.
* Quando o layout do boletim muda, o parser levanta `LayoutDesconhecidoError` e
  interrompe o pipeline, em vez de devolver número plausível e errado.
* Quando a edição da semana anterior falta no histórico, a comparação usa a
  edição mais próxima **e diz qual foi** — em vez de chamar de "1 semana" um
  intervalo de duas.
* No e-mail, a seta acompanha a mediana de hoje e a cor segue o sentido
  econômico do indicador: queda do IPCA é verde; queda do PIB é vermelha.

## Licença

MIT — ver [LICENSE](LICENSE).
