# Radar de IA e Tecnologia

Mesmo motor do radar de futebol (`radar-remo`), com outra lista de fontes:
monitora anúncios dos laboratórios de IA, imprensa internacional, mercado e
veículos brasileiros, e te avisa no Telegram quando sai coisa nova.

Foco editorial escolhido: **IA aplicada a negócios** + **Big Tech e mercado**,
com fontes internacionais (onde a notícia sai primeiro) e brasileiras.

## O que está pronto

- `config.json` — 30 fontes ativas em 4 grupos, mais 6 desligadas que você pode
  ligar quando quiser.
- `monitor.py` — checa cada fonte, compara com o que já foi visto
  (`state/state.json`) e manda no Telegram só o que é novo.
- `.github/workflows/monitor.yml` — roda sozinho a cada 30 minutos, de graça,
  via GitHub Actions.

Todas as fontes foram testadas em 04/08/2026: cada feed desta config respondeu
e entregou item recente na hora do teste.

## Os 4 grupos

| Grupo | Emoji | O que chega |
|---|---|---|
| Laboratórios e Big Tech | 🧪 | Anúncio oficial, direto da fonte: OpenAI, Anthropic, Google DeepMind, Microsoft, Meta, Nvidia, xAI, Mistral |
| Imprensa de IA | 📰 | TechCrunch AI, The Verge AI, The Decoder, Ars Technica, VentureBeat, MIT Tech Review, Wired, Platformer, Hacker News |
| Mercado e negócios | 💰 | CNBC Tech, TechCrunch Startups, Crunchbase News — rodadas, aquisições, resultados |
| Brasil | 🇧🇷 | MIT Tech Review Brasil, Olhar Digital, Tecnoblog, Canaltech, Tilt/UOL, NeoFeed, Brazil Journal, Startups.com.br, Mobile Time |

## Passo a passo para colocar no ar

### 1. Criar o bot do Telegram (separado do radar de futebol)

1. No Telegram, procure **@BotFather** e envie `/newbot`.
2. Escolha um nome e um username (precisa terminar em `bot`) — algo como
   `radar_ia_bot`, pra não confundir com o do futebol.
3. O BotFather responde na hora com o **token**.
4. Abra conversa com o bot novo e mande qualquer mensagem ("oi") — sem isso ele
   não consegue te responder depois.
5. Descubra o `chat_id` e teste tudo de uma vez, no PowerShell dentro desta
   pasta:

   ```powershell
   $env:TELEGRAM_BOT_TOKEN = "cole-aqui-o-token-do-BotFather"
   python ativar_bot.py
   ```

   O script confere o token, acha seu `chat_id` sozinho e manda uma mensagem de
   teste. Se ela chegar no seu Telegram, está tudo certo. (O token fica só na
   variável de ambiente daquela janela do terminal — não é gravado em disco.)

   Se preferir na mão: `https://api.telegram.org/bot<TOKEN>/getUpdates` no
   navegador e procure `"chat":{"id":123456789,...}`.

O `chat_id` provavelmente vai ser o **mesmo** do radar de futebol (é o seu
usuário). O que separa as conversas é o bot: cada bot tem sua própria janela de
conversa no Telegram.

### 2. Criar o repositório no GitHub

1. Repositório novo (pode ser privado), separado do radar de futebol, com estes
   arquivos.
2. Em **Settings → Secrets and variables → Actions**, crie:
   - `TELEGRAM_BOT_TOKEN` → o token do bot novo
   - `TELEGRAM_CHAT_ID` → o chat_id

### 3. Deixar rodando

O workflow roda sozinho a cada 30 minutos. Dá pra disparar na mão em
**Actions → Radar de IA → Run workflow** pra testar.

O `state/state.json` já vem preenchido com o que estava no ar em 11/08/2026, ou
seja: ao subir, ele não te manda uma enxurrada de notícia velha — só o que sair
daí em diante. (Fonte que ainda não tem estado registrado também não notifica na
primeira execução; só grava o que existe.)

## Como isso difere do radar de futebol

Três coisas que o radar de futebol não tem:

**1. Digest.** Uma mensagem por execução com tudo que apareceu, em vez de uma
mensagem por notícia. Com 30 fontes, mensagem avulsa viraria spam. Para voltar
ao comportamento do radar de futebol, troque em `config.json`:
`"modo_notificacao": "individual"`.

**2. Deduplicação.** Um lançamento da OpenAI sai no blog deles, no TechCrunch e
no Tecnoblog. O radar compara o título com os 200 mais recentes já enviados e
silencia o repetido. É deliberadamente conservador — na dúvida, ele manda:
deixar passar uma repetida custa uma linha a mais, engolir notícia nova custa a
pauta. Por isso títulos com menos de 5 palavras significativas nunca são
deduplicados ("Introducing Claude Opus 5" e "Introducing Claude Sonnet 5"
dividem 2 de 3 palavras e são dois lançamentos diferentes). Notícia em inglês e
a versão dela em português chegam as duas — proposital, você pode querer a
manchete já em português.

**3. Filtro por palavra inteira.** No radar de futebol o filtro é por trecho de
texto. Aqui, procurar "ia" desse jeito casaria com "famí**lia**" e
"not**ícia**". O radar normaliza (tira acento, pontuação vira espaço) e exige
palavra inteira: "ia" pega "IA generativa" e "o que é IA?", mas não "família".

## Mexendo na configuração

**Ligar/desligar uma fonte:** `"enabled": false` desliga sem apagar. Vêm
desligadas: The Register, SiliconANGLE, Tecmundo, IT Forum, InfoMoney e Exame —
todas por volume alto ou muito ruído fora do tema no teste. Para ligar, troque
para `true` (ou apague a linha).

**Lista de palavras de IA:** fica em `listas_de_palavras.ia`, no topo do
arquivo, e as fontes usam com `"filter_keywords_ref": "ia"` em vez de repetir a
lista 20 vezes.

**`match_in`:** por padrão o filtro olha título e link. O link ajuda quando o
site organiza por categoria (`canaltech.com.br/inteligencia-artificial/...`) e
atrapalha no blog da própria empresa — em `blogs.nvidia.com` todo link casaria
com "nvidia" e passaria tudo, inclusive notícia de placa de vídeo pra jogar. Por
isso Nvidia, Microsoft, Meta e Google usam `"match_in": "titulo"`.

**Exclusões globais:** `exclude_keywords_global` corta cupom, oferta, guia de
compras, unboxing, gameplay etc. em todas as fontes. `exclude_except_global`
resgata o item que casou com uma exclusão mas fala de OpenAI/Anthropic/Nvidia.

**Ver o efeito de um filtro antes de subir:**

```bash
python monitor.py --preview
```

Mostra o que cada fonte devolve agora, já peneirado, sem notificar e sem gravar
estado. É o jeito rápido de testar mudança de palavra-chave.

## Tipos de fonte suportados

- `rss` — feeds RSS/Atom (mais estável; use sempre que existir).
- `scrape_list` — site sem RSS; acha os links pelo padrão de URL (regex) e
  procura a tag `<h1>`-`<h6>` mais próxima pra extrair o título. `title_window`
  controla quantos caracteres de HTML depois do link ele varre (padrão 700).
- `json_list` — site que serve notícia por API JSON. Precisa de `items_path`,
  `id_field`, `title_field` e `link_template`.

## Fontes que ficaram de fora (e por quê)

Estão registradas em `sources_nao_automatizadas` dentro do `config.json`:

- **Reuters Technology** e **Bloomberg / The Information** — bloqueiam acesso
  automatizado (401) ou são pagas.
- **Meta AI (blog técnico)** — servidor devolve 400 pra leitura automatizada. O
  newsroom da Meta, que está no radar, cobre os anúncios principais.

Duas fontes entram com limitação conhecida:

- **Mistral AI** — a página não expõe o título no HTML, então chega só o link
  (o endereço já diz o assunto: `/news/mistral-small-4`).
- **xAI** e **Anthropic** — de vez em quando um item vem com o nome da fonte no
  lugar do título, quando o HTML não tem cabeçalho perto do link.

## Limitações

- Site sem RSS pode mudar de estrutura e quebrar o scraping. Se uma fonte parar
  de notificar, rode `--preview` pra ver se ela ainda devolve item.
- O radar avisa que saiu — ele não apura, não confere data nem resume. A
  checagem continua sendo sua.
- GitHub Actions em repositório privado tem cota mensal de minutos. Com dois
  radares rodando (futebol a cada 10 min, IA a cada 30), vale olhar o consumo em
  **Settings → Billing** no primeiro mês.
