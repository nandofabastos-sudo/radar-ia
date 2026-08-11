"""
Ativa o bot do Telegram do radar de IA -- do zero ao GitHub, num comando so.
---------------------------------------------------------------------------
Rode:
    python ativar_bot.py

Ele vai:
  1. pedir o token do BotFather (o que voce digita nao aparece na tela)
  2. conferir se o token e valido
  3. descobrir o seu chat_id sozinho
  4. mandar uma mensagem de teste no seu Telegram
  5. cadastrar TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID nos Secrets do GitHub

O token nunca e gravado em disco nem aparece na tela: vai da sua colagem
direto pro Telegram e pro GitHub.
"""

import getpass
import os
import subprocess
import sys

import requests

API = "https://api.telegram.org/bot{token}/{metodo}"
REPO_PADRAO = "nandofabastos-sudo/radar-ia"


def chamar(token: str, metodo: str, **params):
    r = requests.get(API.format(token=token, metodo=metodo), params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def pedir_token() -> str:
    """Pega o token da variavel de ambiente ou pergunta na hora."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        print("[OK] Usando o token da variavel TELEGRAM_BOT_TOKEN.")
        return token

    print("Cole abaixo o token que o BotFather te mandou e tecle Enter.")
    print("(parece com 8123456789:AAH... -- a tela NAO vai mostrar o que voce")
    print(" colar, isso e proposital, e assim que se digita senha no terminal)\n")
    try:
        return getpass.getpass("Token: ").strip()
    except Exception:
        print("\n[ERRO] Nao consegui ler o token deste terminal.")
        print("Rode assim, colando o token entre as aspas:")
        print('    $env:TELEGRAM_BOT_TOKEN = "cole-o-token-aqui"')
        print("    python ativar_bot.py")
        sys.exit(1)


def cadastrar_secret(nome: str, valor: str, repo: str) -> bool:
    """Manda o valor pro GitHub pelo stdin do gh, sem passar por arquivo."""
    try:
        r = subprocess.run(
            ["gh", "secret", "set", nome, "--repo", repo],
            input=valor.encode("utf-8"),
            capture_output=True,
        )
    except FileNotFoundError:
        print("[ERRO] Nao encontrei o comando 'gh' (GitHub CLI) nesta maquina.")
        return False
    if r.returncode != 0:
        print(f"[ERRO] Falha ao cadastrar {nome}: {r.stderr.decode(errors='replace').strip()}")
        return False
    print(f"[OK] Secret {nome} cadastrado em {repo}.")
    return True


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else REPO_PADRAO

    token = pedir_token()
    if not token:
        print("[ERRO] Token vazio.")
        return 1

    # 1. o token e valido?
    try:
        bot = chamar(token, "getMe")["result"]
    except Exception as e:
        print(f"\n[ERRO] O Telegram nao aceitou esse token: {e}")
        print("Confira se copiou o token inteiro (ele tem dois pedacos,")
        print("separados por dois-pontos) e sem espaco sobrando nas pontas.")
        return 1

    print(f"\n[OK] Token valido. Bot: {bot.get('first_name')} (@{bot.get('username')})")

    # 2. descobrir o chat_id nas mensagens que voce mandou pra ele
    updates = chamar(token, "getUpdates")["result"]
    chats = {}
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or {}
        chat = msg.get("chat")
        if chat:
            chats[chat["id"]] = chat.get("first_name") or chat.get("title") or "?"

    if not chats:
        print("\n[FALTA UM PASSO] O bot ainda nao recebeu nenhuma mensagem sua.")
        print(f"Abra o Telegram, procure por @{bot.get('username')}, toque em")
        print("INICIAR e mande um 'oi' pra ele. Depois rode este script de novo.")
        print("Sem isso o Telegram proibe o bot de te escrever.")
        return 1

    if len(chats) > 1:
        print("\n[ATENCAO] Encontrei mais de uma conversa; usando a primeira:")
        for cid, nome in chats.items():
            print(f"    chat_id {cid}  ->  {nome}")

    chat_id, nome = next(iter(chats.items()))
    print(f"[OK] Seu chat_id: {chat_id}   (conversa: {nome})")

    # 3. mensagem de teste
    envio = requests.post(
        API.format(token=token, metodo="sendMessage"),
        data={
            "chat_id": chat_id,
            "text": (
                "\U0001F4E1 Radar de IA conectado!\n\n"
                "Se voce esta lendo isso, o bot funciona. As novidades de IA "
                "e tecnologia vao chegar por aqui."
            ),
        },
        timeout=20,
    )
    if not envio.ok:
        print(f"[ERRO] Nao consegui enviar a mensagem de teste: {envio.text}")
        return 1
    print("[OK] Mensagem de teste enviada -- confere o seu Telegram agora.")

    # 4. cadastrar no GitHub
    print(f"\nAgora posso cadastrar os dois valores nos Secrets de {repo},")
    print("que e o que faz o radar rodar sozinho no GitHub.")
    resposta = input("Cadastrar agora? [S/n] ").strip().lower()
    if resposta and not resposta.startswith("s"):
        print("\nOk, deixei pra depois. Quando quiser, rode de novo ou cadastre")
        print(f"na mao em: https://github.com/{repo}/settings/secrets/actions")
        return 0

    ok1 = cadastrar_secret("TELEGRAM_BOT_TOKEN", token, repo)
    ok2 = cadastrar_secret("TELEGRAM_CHAT_ID", str(chat_id), repo)

    if ok1 and ok2:
        print("\n=== TUDO PRONTO ===")
        print("O radar ja pode rodar sozinho no GitHub Actions.")
        print(f"Para disparar um teste agora: https://github.com/{repo}/actions")
        return 0

    print("\nAlgo falhou no cadastro. Da pra fazer na mao em:")
    print(f"https://github.com/{repo}/settings/secrets/actions")
    return 1


if __name__ == "__main__":
    sys.exit(main())
