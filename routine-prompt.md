# Prompt da rotina — resumo do Boletim Focus

Rotina agendada no Claude Code (`trig_01HqCWbbJRqAGiogmVjWF6iv`), segunda-feira
às 12h00 BRT.

## O que mudou na v2

A rotina **não escreve mais HTML nem tabela**. Escrever a tabela à mão foi a
origem de dois defeitos publicados por e-mail: a seta ▲/▼ na coluna errada e a
cor invertida em relação ao sentido econômico do indicador.

Agora a divisão é:

| Quem | O quê |
|---|---|
| **código** (`python -m focus email`) | todos os números, o quadro-resumo, as setas, as cores, o HTML e o envio |
| **você, agente** | a prosa: resumo executivo e hipóteses para as revisões |

Você entrega **um arquivo Markdown**: `output/focus/focus_AAAA-MM-DD.md`.
O push desse arquivo dispara o workflow `focus-enviar`, que monta e envia.

---

## Regra absoluta

Nunca invente número. Todo valor citado deve estar literalmente presente na
saída de `python -m focus verificar` ou no `.txt` do boletim. Em qualquer falha
dos passos 1 a 3, **pare sem commitar** — assim nenhum e-mail é enviado. O
motivo fica registrado no transcript da rotina.

---

## Passo 1 — Diagnóstico

```bash
python -m focus verificar
```

Se o comando sair com código diferente de zero, **pare sem commitar**. A saída
já diz o motivo (download parado, histórico desatualizado, parser falhando,
resumo em atraso). Não tente contornar.

## Passo 2 — Ler os números

```bash
python -m focus email --dry-run
```

O comando imprime o e-mail montado a partir do histórico, com o quadro-resumo
já preenchido. **Esses são os números da semana.** Use-os; não recalcule nada e
não leia o PDF para conferir aritmética — o quadro vem de dados validados.

Para as maiores revisões da semana, em pontos percentuais:

```bash
python - <<'PY'
from focus import analytics as an, store
obs = store.carregar("data/history/expectativas.csv")
data = an.ultima_data(obs)
for r in an.destaques(an.revisoes(obs, data=data), quantidade=5):
    print(f"{r.indicador} ({r.referencia}): {r.ha_1_semana} -> {r.atual} "
          f"[{r.delta_1s:+.2f} {r.unidade}] gap5d={r.gap_5d} "
          f"comparacao_exata={r.comparacao_exata}")
PY
```

Se `comparacao_exata` for `False`, a edição comparada não é a da semana
anterior. Diga isso no texto em vez de escrever "na semana passada".

## Passo 3 — Verificação de sanidade

Confirme, a partir da saída do passo 2:

1. A data do boletim é a esperada para esta segunda-feira.
2. IPCA, Selic e PIB aparecem com valores.
3. Nenhum valor citado por você é diferente do que o comando imprimiu.

Se qualquer verificação falhar, **pare sem commitar**.

## Passo 4 — Escrever a prosa

Grave em `output/focus/focus_AAAA-MM-DD.md` (data real do boletim), neste
formato:

```markdown
Parágrafo único de até 200 palavras, em prosa corrida. Comece pelas medianas
do ano corrente para IPCA, Selic, PIB e câmbio, citando os valores entre aspas
exatamente como aparecem ("4,90", "13,75"). Em seguida, o que mudou na semana
e o que isso sugere sobre o cenário. Tom descritivo; nada de previsão própria.

- Selic (2026): 14,00 → 13,75. Hipótese: possível antecipação de corte pelo Copom.
- IPCA (2026): 5,00 → 4,90. Hipótese: leitura corrente de inflação mais benigna.
- IGP-M (2026): 4,38 → 4,54. Hipótese: sem hipótese clara — pode ser ruído amostral.
```

Regras do texto:

* Primeiro parágrafo (ou parágrafos) = resumo. Bullets = as três principais
  revisões, no formato `Variável (ano): anterior → atual. Hipótese: motivo.`
* Sem hipótese sólida, escreva: "sem hipótese clara — pode ser ruído amostral".
* Use apenas revisões da mesma família de unidade (p.p.) no ranking — o
  comando do passo 2 já filtra.
* Não escreva HTML. Não escreva tabela. Não escreva a seta ▲/▼.

Quando o gap de 5 dias úteis for relevante (mesmo sinal por várias semanas, ou
magnitude acima de 0,05 p.p.), vale uma frase: a base curta antecede a mediana
cheia, e é leitura que o público deste boletim aproveita.

## Passo 5 — Publicar

```bash
git config user.email "bot@boletimfocus"
git config user.name  "BoletimFocus Bot"
git add output/focus/focus_AAAA-MM-DD.md
git commit -m "feat: resumo focus AAAA-MM-DD"
git push origin main
```

O workflow `focus-enviar` monta o HTML e envia. Remetente, senha de app e
destinatários vêm dos **Secrets do repositório** — nunca do código, nunca deste
arquivo.

---

## Cenários de parada (sem commitar)

| Situação | Motivo registrado |
|---|---|
| `focus verificar` sai com código ≠ 0 | a própria saída do comando |
| `focus email --dry-run` falha | histórico ausente ou corrompido |
| Um número que você escreveria não está na saída do passo 2 | risco de valor inventado |
