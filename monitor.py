"""
Radar de IA/Tech - monitor de fontes por grupo
------------------------------------------------
Mesmo motor do radar de futebol (radar-remo), adaptado para noticias de
Inteligencia Artificial, big tech e negocios.

Le config.json (fontes agrupadas por tema), verifica o que ha de novo desde a
ultima execucao (guardado em state/state.json) e dispara uma notificacao no
Telegram para cada item novo.

Uso local:
    export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
    export TELEGRAM_CHAT_ID="123456789"
    python monitor.py

Para ver o que cada fonte esta devolvendo AGORA, sem notificar e sem gravar
estado (util pra ajustar filtros):
    python monitor.py --preview

Em producao isso roda via GitHub Actions (ver .github/workflows/monitor.yml).
"""

import html
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import feedparser
import requests

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state" / "state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

MAX_ITEMS_PER_SOURCE = 10
MAX_IDS_KEPT_PER_SOURCE = 300

# janela de HTML apos o link, onde procuramos o titulo da noticia (h1-h6).
TITLE_SEARCH_WINDOW = 700
TITLE_TAG_PREFERRED_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.DOTALL)
TITLE_TAG_ANY_RE = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")

# --- deduplicacao entre fontes -------------------------------------------
# Um lancamento da OpenAI sai no blog deles, no TechCrunch, no Verge e no
# Olhar Digital. Sem isso, a mesma noticia chegaria 4x no Telegram.
DEDUP_SIMILARITY = 0.6      # fracao de palavras em comum pra considerar igual
DEDUP_MIN_PALAVRAS = 5      # abaixo disso o titulo e curto demais pra comparar
DEDUP_HISTORY_SIZE = 200    # quantos titulos recentes ficam na comparacao
DEDUP_STATE_KEY = "_titulos_recentes"
PALAVRAS_IGNORADAS = {
    "para", "com", "que", "dos", "das", "uma", "por", "mais", "the", "and",
    "for", "with", "from", "its", "new", "novo", "nova", "sobre", "como",
    "após", "apos", "apos", "seu", "sua", "the", "this", "that", "says",
    "diz", "vai", "ser", "sao", "são",
}


def normalizar_palavras(titulo: str) -> set:
    """Reduz o titulo a um conjunto de palavras significativas, sem acento."""
    texto = unicodedata.normalize("NFKD", titulo.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    palavras = re.findall(r"[a-z0-9]+", texto)
    return {p for p in palavras if len(p) > 3 and p not in PALAVRAS_IGNORADAS}


def eh_repetida(titulo: str, historico: list[list[str]]) -> bool:
    """A mesma noticia ja chegou por outra fonte?

    Na duvida, responde False: deixar passar uma repetida custa uma mensagem a
    mais, engolir uma noticia nova custa a pauta. Por isso titulos curtos nunca
    sao deduplicados -- "Introducing Claude Opus 5" e "Introducing Claude
    Sonnet 5" dividem 2 de 3 palavras e sao dois lancamentos diferentes.
    """
    atual = normalizar_palavras(titulo)
    if len(atual) < DEDUP_MIN_PALAVRAS:
        return False
    for anterior in historico:
        anterior = set(anterior)
        if len(anterior) < DEDUP_MIN_PALAVRAS:
            continue
        comum = len(atual & anterior)
        if comum / min(len(atual), len(anterior)) >= DEDUP_SIMILARITY:
            return True
    return False


def extract_nearby_title(html_text: str, end_pos: int, fallback: str,
                         window_size: int = TITLE_SEARCH_WINDOW) -> str:
    window = html_text[end_pos: end_pos + window_size]
    for pattern in (TITLE_TAG_PREFERRED_RE, TITLE_TAG_ANY_RE):
        m = pattern.search(window)
        if m:
            cleaned = html.unescape(HTML_TAG_RE.sub("", m.group(1)))
            cleaned = " ".join(cleaned.split())
            if cleaned:
                return cleaned
    return fallback


def item_cap(source: dict) -> int:
    """Quantos itens varrer na origem.

    Com filtro por palavra-chave vale varrer bem mais antes de peneirar: um
    portal generalista publica dezenas de materias de celular/games entre uma
    noticia de IA e outra.
    """
    if source.get("filter_keywords") or source.get("exclude_keywords"):
        return MAX_ITEMS_PER_SOURCE * 5
    return MAX_ITEMS_PER_SOURCE


def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_rss(source: dict) -> list[dict]:
    # baixamos com requests (User-Agent de navegador) porque alguns feeds
    # recusam o cliente padrao do feedparser
    resp = requests.get(source["url"], headers=HEADERS, timeout=25)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries[:item_cap(source)]:
        link = entry.get("link")
        if not link:
            continue
        items.append(
            {
                "id": entry.get("id") or link,
                "title": (entry.get("title") or "").strip(),
                "link": link,
            }
        )
    return items


def fetch_scrape_list(source: dict) -> list[dict]:
    resp = requests.get(source["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    # o Content-Type de alguns sites nao declara charset, e requests cai pra
    # ISO-8859-1 por padrao mesmo quando o conteudo real e UTF-8 (mojibake)
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    page_html = resp.text

    pattern = source["url_pattern"]

    items = []
    seen_links = set()
    for m in re.finditer(pattern, page_html):
        raw = m.group(0)
        link = raw if raw.startswith("http") else source.get("base_url", "").rstrip("/") + "/" + raw.lstrip("/")
        if link in seen_links:
            continue
        seen_links.add(link)
        title = extract_nearby_title(
            page_html, m.end(), source["name"],
            source.get("title_window", TITLE_SEARCH_WINDOW),
        )
        items.append({"id": link, "title": title, "link": link})
        if len(items) >= item_cap(source):
            break
    return items


def fetch_json_list(source: dict) -> list[dict]:
    """Le uma API que devolve JSON (mais estavel que raspar HTML).

    Campos esperados na config da fonte:
      items_path    - caminho ate a lista, separado por ponto (ex: "data.posts")
      id_field      - campo usado como identificador unico
      title_field   - campo com o titulo
      link_template - molde do link, com {campo} preenchido pelo item
    """
    resp = requests.get(source["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    for key in source.get("items_path", "").split("."):
        if key:
            data = data[key]

    items = []
    for entry in data[:item_cap(source)]:
        items.append(
            {
                "id": str(entry[source.get("id_field", "id")]),
                "title": str(entry[source.get("title_field", "title")]).strip(),
                "link": source["link_template"].format(**entry),
            }
        )
    return items


def normalizar_texto(texto: str) -> str:
    """minusculas, sem acento, pontuacao virando espaco, com espaco nas bordas.

    O espaco nas bordas e o que permite casar palavra inteira: procurar " ia "
    encontra "IA generativa" e "o que e IA?", mas nao "familia" nem "noticia".
    """
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " " + " ".join(re.findall(r"[a-z0-9]+", texto)) + " "


def matches_keywords(item: dict, keywords: list[str], onde: str = "titulo_e_link") -> bool:
    """Procura as palavras no titulo (e no link, se onde == "titulo_e_link").

    Olhar o link ajuda quando o site organiza por categoria
    (canaltech.com.br/inteligencia-artificial/...), mas atrapalha no blog da
    propria empresa: em blogs.nvidia.com todo link casaria com "nvidia". Por
    isso essas fontes usam "match_in": "titulo".
    """
    alvo = item.get("title", "")
    if onde != "titulo":
        alvo += " " + item.get("link", "")
    alvo = normalizar_texto(alvo)
    return any(normalizar_texto(k) in alvo for k in keywords)


def get_items(source: dict) -> list[dict]:
    source_type = source["type"]
    if source_type in ("rss", "youtube_rss"):
        items = fetch_rss(source)
    elif source_type == "scrape_list":
        items = fetch_scrape_list(source)
    elif source_type == "json_list":
        items = fetch_json_list(source)
    else:
        raise ValueError(f"Tipo de fonte desconhecido: {source_type}")

    # portais generalistas (Canaltech, InfoMoney, CNBC) publicam de tudo;
    # so passa o que tem palavra de IA/tech no titulo ou no link
    onde = source.get("match_in", "titulo_e_link")
    keywords = source.get("filter_keywords")
    if keywords:
        items = [it for it in items if matches_keywords(it, keywords, onde)]

    # assuntos que nunca viram pauta do canal (cupom, review de celular...).
    # A excecao resgata o item que, apesar de casar com a exclusao, fala do
    # que interessa: "review do celular com o novo chip de IA" continua vindo.
    excluir = source.get("exclude_keywords")
    if excluir:
        resgate = source.get("exclude_except", [])
        items = [
            it for it in items
            if not matches_keywords(it, excluir)
            or (resgate and matches_keywords(it, resgate))
        ]

    return items[:MAX_ITEMS_PER_SOURCE]


# o Telegram corta mensagem acima de 4096 caracteres
TELEGRAM_MAX_CHARS = 3800


def enviar_digest(blocos: list[str]):
    """Manda tudo o que apareceu na execucao numa mensagem so.

    Com o radar rodando a cada 30 minutos, receber 6 mensagens seguidas e
    pior do que receber uma com 6 links. Quebra em varias so se estourar o
    limite do Telegram.
    """
    if not blocos:
        return

    cabecalho = f"\U0001F4E1 Radar de IA - {len(blocos)} novidade(s)\n\n"
    atual = cabecalho
    for bloco in blocos:
        if len(atual) + len(bloco) + 2 > TELEGRAM_MAX_CHARS:
            notify_telegram(atual.rstrip())
            atual = ""
        atual += bloco + "\n\n"
    if atual.strip():
        notify_telegram(atual.rstrip())


def notify_telegram(message: str):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("[AVISO] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID nao configurados. "
              "Mensagem que seria enviada:")
        print(message)
        print("-" * 40)
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        r = requests.post(url, data=payload, timeout=20)
        r.raise_for_status()
        print(f"[OK] Notificacao enviada: {message.splitlines()[0]}")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar Telegram: {e}")


def preparar_fonte(source: dict, config: dict) -> dict:
    """Resolve listas de palavras reutilizaveis e junta os filtros globais.

    "filter_keywords_ref": "ia" pega a lista chamada "ia" em "listas_de_palavras"
    la no topo da config, em vez de repetir 40 palavras em cada fonte.
    """
    pronta = dict(source)

    ref = pronta.pop("filter_keywords_ref", None)
    if ref:
        listas = config.get("listas_de_palavras", {})
        if ref not in listas:
            raise KeyError(f"lista de palavras '{ref}' nao existe na config")
        pronta["filter_keywords"] = list(pronta.get("filter_keywords", [])) + listas[ref]

    excluir_global = config.get("exclude_keywords_global", [])
    if excluir_global:
        pronta["exclude_keywords"] = (
            list(pronta.get("exclude_keywords", [])) + excluir_global
        )
        pronta["exclude_except"] = (
            list(pronta.get("exclude_except", []))
            + config.get("exclude_except_global", [])
        )

    return pronta


def fontes_ativas(grupo: dict) -> list[dict]:
    """Fontes do grupo, pulando as marcadas com "enabled": false."""
    return [s for s in grupo.get("sources", []) if s.get("enabled", True)]


def preview():
    """Mostra o que cada fonte devolve agora, sem notificar e sem gravar."""
    config = load_json(CONFIG_PATH, {"grupos": {}})
    for grupo_key, grupo in config["grupos"].items():
        for source in fontes_ativas(grupo):
            print("=" * 72)
            print(f"{grupo['name']} / {source['name']}")
            try:
                items = get_items(preparar_fonte(source, config))
            except Exception as e:
                print(f"  [ERRO] {type(e).__name__}: {str(e)[:140]}")
                continue
            if not items:
                print("  (nenhum item passou pelos filtros agora)")
            for it in items[:5]:
                print(f"  - {it['title'][:80]}")
                print(f"    {it['link']}")


def run():
    config = load_json(CONFIG_PATH, {"grupos": {}})
    state = load_json(STATE_PATH, {})

    # titulos ja notificados recentemente, pra nao mandar a mesma noticia
    # vinda de 4 sites diferentes
    historico_titulos = state.get(DEDUP_STATE_KEY, [])

    # "digest" junta tudo numa mensagem por execucao; "individual" manda uma
    # mensagem por noticia (como no radar de futebol)
    modo = config.get("modo_notificacao", "digest")
    digest: list[str] = []

    total_new = 0
    total_repetidas = 0

    for grupo_key, grupo in config["grupos"].items():
        sources = fontes_ativas(grupo)
        if not sources:
            continue

        emoji = grupo.get("emoji", "\U0001F916")
        grupo_state = state.setdefault(grupo_key, {})

        for source in sources:
            source_key = source["id"]
            # seen_ids guarda a ordem de chegada (mais antigo -> mais novo), pra
            # o corte no fim descartar de fato os mais antigos. O set e so pra
            # consulta rapida.
            seen_ids = list(grupo_state.get(source_key, []))
            already_seen = set(seen_ids)
            is_first_run = source_key not in grupo_state

            try:
                items = get_items(preparar_fonte(source, config))
            except Exception as e:
                print(f"[ERRO] {grupo['name']} / {source['name']}: {e}")
                continue

            new_items = [it for it in items if it["id"] not in already_seen]

            # do mais antigo para o mais novo, pra notificar na ordem certa
            for it in reversed(new_items):
                if not is_first_run:
                    if eh_repetida(it["title"], historico_titulos):
                        total_repetidas += 1
                        print(f"[DUP] Ja noticiado por outra fonte: {it['title'][:60]}")
                    else:
                        msg = (
                            f"{emoji} {source['name']}\n"
                            f"{it['title']}\n"
                            f"{it['link']}"
                        )
                        if modo == "digest":
                            digest.append(msg)
                        else:
                            notify_telegram(msg)
                        historico_titulos.append(sorted(normalizar_palavras(it["title"])))
                        total_new += 1
                if it["id"] not in already_seen:
                    already_seen.add(it["id"])
                    seen_ids.append(it["id"])

            if is_first_run and new_items:
                print(f"[INFO] Primeira execucao de '{source['name']}' "
                      f"({grupo['name']}): {len(new_items)} itens registrados, "
                      f"sem notificar.")

            # nao deixa a lista crescer pra sempre; como seen_ids esta em ordem
            # de chegada, o corte descarta os mais antigos e mantem os recentes
            grupo_state[source_key] = seen_ids[-MAX_IDS_KEPT_PER_SOURCE:]

    if modo == "digest":
        enviar_digest(digest)

    state[DEDUP_STATE_KEY] = historico_titulos[-DEDUP_HISTORY_SIZE:]
    save_json(STATE_PATH, state)
    print(f"[FIM] {total_new} novidade(s) notificada(s); "
          f"{total_repetidas} repetida(s) de outra fonte foram silenciadas.")


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview()
    else:
        run()
