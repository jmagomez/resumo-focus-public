# /gerar-resumo

Escreve a prosa do boletim Focus da semana em `output/focus/focus_AAAA-MM-DD.md`.

Este comando produz **texto**. Todo número publicado — quadro-resumo, setas,
cores, percentuais — é gerado por `focus.report` a partir do histórico já
validado. Você não monta tabela, não calcula variação e não formata valor.

## Passos

1. **Descubra a data da edição e leia os números.** Rode:

   ```bash
   python -m focus email --dry-run
   ```

   A primeira linha diz qual arquivo seria gravado (`focus_AAAA-MM-DD.html`) —
   é essa a data da edição. O resto da saída é o quadro-resumo com a mediana de
   hoje e a variação contra a edição anterior, indicador por indicador.

   Se o comando reclamar que não há prosa em `output/focus/*.md`, ignore: é
   exatamente o arquivo que você vai escrever. Use `--prosa /dev/null` para ver
   os números assim mesmo.

2. **Leia o boletim de origem.** O `.txt` mais recente em `data/` traz o texto
   do BCB para a mesma edição. Use-o para contexto, nunca como fonte de número
   que contradiga a saída do passo 1.

3. **Escreva `output/focus/focus_AAAA-MM-DD.md`** no formato abaixo. Não
   commite: o workflow faz isso.

## Formato do arquivo

Um parágrafo de resumo, linha em branco, e uma lista de revisões. Cabeçalhos
`#` são ignorados pelo parser; bullets começam com `- `.

```markdown
O Focus de 11 de setembro trouxe a quarta queda consecutiva da mediana do IPCA
para 2026, agora em 4,90%, com a Selic de fim de ano parada em 13,75% a.a. pela
sexta semana. O movimento se concentra nos horizontes curtos: 2027 subiu 0,01
p.p. e 2028 não se moveu.

- IPCA (2026): 5,00 → 4,90. A revisão veio junto com queda de 0,10 p.p. nos
  administrados, o que sugere repasse de tarifa e não alívio difuso de preços.
- PIB (2026): 1,93 → 1,89. Quarta revisão para baixo seguida, e o horizonte de
  2028 caiu 0,09 p.p. — a maior variação da semana em atividade.
- IGP-M (2026): 4,34 → 4,54. Única alta relevante do quadro.
```

## Regras inegociáveis

- **Nunca invente número.** Todo valor citado tem de aparecer literalmente na
  saída de `python -m focus email --dry-run` ou no `.txt` do boletim. Se você
  não encontrou o número, não escreva a frase.
- **Não misture unidades.** `+1,67 US$ bi` e `+0,10 p.p.` não são comparáveis e
  não entram na mesma comparação nem no mesmo ranking.
- **Sentido econômico, não direção.** Queda do IPCA é notícia favorável; queda
  do PIB é desfavorável. Escreva a interpretação, não só o sinal.
- **Meta contínua.** Desde janeiro de 2025 a meta é 3,00% com banda de ±1,5
  p.p., avaliada **mês a mês** sobre o IPCA acumulado em doze meses, e o
  descumprimento se caracteriza com seis meses consecutivos fora do intervalo.
  Não descreva a meta como de ano-calendário nem fale em "dois trimestres".
- **Hipótese é hipótese.** Quando sugerir o porquê de uma revisão, marque como
  leitura ("sugere", "é compatível com"), nunca como fato apurado.

## Extensão e tom

Resumo de três a cinco frases. De três a seis bullets, priorizando o que se
moveu mais e o que muda a leitura de política monetária — não a lista inteira
do quadro. O leitor é analista de mercado: não explique o que é o Focus, não
defina IPCA, não encha de adjetivo. Semana sem movimento relevante é uma
informação legítima; escreva isso em vez de inflar o texto.
