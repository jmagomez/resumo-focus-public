# Prompt da Rotina — Resumo Boletim Focus

Prompt usado pela rotina agendada no Claude Code
(`trig_01HqCWbbJRqAGiogmVjWF6iv`), que roda toda segunda-feira às 12h00 BRT.

O agente lê o `.txt` gerado pelo GitHub Action `focus-download.yml`,
escreve o resumo, salva o HTML e faz **push para o repositório**.
É esse push que dispara o Action `focus-enviar.yml`, que lê os Secrets
do repositório (`FOCUS_SMTP_USER`, `FOCUS_SMTP_APP_PASSWORD`,
`FOCUS_EMAIL_DEST`, `FOCUS_EMAIL_BCC`) e envia o e-mail.
**O destinatário, o remetente e a senha nunca aparecem neste arquivo.**

---

## Regra absoluta

Nunca invente número. Todo valor citado deve estar literalmente
presente no arquivo `.txt`. Em qualquer falha dos passos 1, 2 ou 3,
**pare sem commitar o HTML** — assim nenhum e-mail é enviado.
O motivo fica registrado no transcript da rotina.

---

## Passo 1 — Localizar o .txt mais recente

Liste os arquivos `data/focus_*.txt` e identifique o de data mais alta
(pelo nome do arquivo).
Se não houver nenhum `.txt` em `data/`, **pare sem commitar o HTML**.
Motivo de parada: "Nenhum .txt em data/ — o GitHub Action não rodou."

## Passo 2 — Verificar frescor

Extraia a data do nome do arquivo (formato `focus_AAAA-MM-DD.txt`)
e compare com a data de hoje:

- **0 a 3 dias:** fresco, siga normalmente.
- **4 a 7 dias:** siga, mas adicione `[REVISAR]` no início do assunto.
- **Mais de 7 dias:** **pare sem commitar o HTML**.
  Motivo de parada: ".txt com mais de 7 dias — o Action pode estar com problema."

## Passo 3 — Sanity check do texto

Leia o arquivo `.txt` inteiro. Verifique:

1. O texto tem pelo menos 2.080 caracteres.
2. Contém as palavras `IPCA`, `Selic` e `PIB`.

Se qualquer verificação falhar, **pare sem commitar o HTML**.
Motivo de parada: "Sanity check falhou — layout do PDF pode ter mudado."

## Passo 4 — Escrever o resumo

### 4a. Resumo executivo (até 200 palavras, prosa corrida)

- Comece pelas medianas das principais variáveis do ano corrente:
  IPCA, Selic fim de ano, PIB e câmbio.
- Cite literalmente entre aspas os valores numéricos-chave
  exatamente como aparecem no `.txt`.
- Nunca invente número: use apenas o que está literalmente no texto.

### 4b. Três principais revisões da semana (bullets)

Formato: `Variável (ano): anterior → atual. Hipótese: motivo.`

- Se não houver hipótese sólida, escreva:
  "sem hipótese clara — pode ser ruído amostral."
- Use apenas números presentes no arquivo `.txt`.

## Passo 5 — Montar e salvar o HTML

Salve em `output/focus/focus_AAAA-MM-DD.html`
(use a data real extraída do nome do `.txt`).

Estrutura obrigatória:

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>Focus AAAA-MM-DD</title></head>
<body style="font-family: Arial, sans-serif; max-width: 680px; margin: auto; padding: 24px;">
  <img src="https://analisemacro.com.br/wp-content/uploads/dlm_uploads/2021/10/logo_an.png"
       alt="Análise Macro" style="height: 48px; margin-bottom: 16px;">
  <h1 style="color: #282f6b;">Focus AAAA-MM-DD</h1>
  <p><!-- resumo executivo em prosa --></p>
  <h2 style="color: #282f6b;">Principais revisões da semana</h2>
  <ul>
    <li><!-- revisão 1 --></li>
    <li><!-- revisão 2 --></li>
    <li><!-- revisão 3 --></li>
  </ul>
</body>
</html>
```

## Passo 6 — Inspecionar o HTML gerado

Releia o arquivo HTML salvo e confirme:

1. A tag `<img>` com a URL da logo está presente.
2. Os valores numéricos citados no HTML batem com o que está no `.txt`.
3. Há ao menos uma citação literal entre aspas.

Se alguma verificação falhar, corrija o HTML antes de continuar.

## Passo 7 — Publicar o HTML (git push → dispara o envio de e-mail)

Faça commit do HTML gerado e push para `main`:

```bash
git config user.email "bot@boletimfocus"
git config user.name "BoletimFocus Bot"
git add output/focus/focus_AAAA-MM-DD.html
git commit -m "feat: resumo focus AAAA-MM-DD"
git push origin main
```

O push detectado pelo GitHub Action `focus-enviar.yml` dispara
automaticamente o envio do e-mail. O remetente, a senha de app e os
destinatários são lidos dos **Secrets do repositório** configurados
em `Settings → Secrets and variables → Actions` — nunca do código
ou deste arquivo.

---

## Cenários de parada (sem commitar o HTML)

| Situação | Motivo registrado |
|---|---|
| Nenhum `.txt` em `data/` | Action `focus-download.yml` não rodou |
| `.txt` com mais de 7 dias | Action pode estar quebrado |
| Sanity check falhou | Layout do PDF pode ter mudado |
