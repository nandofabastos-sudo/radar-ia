"""
Ativa e testa o bot do Telegram do radar de IA.
------------------------------------------------
Confere se o token funciona, descobre o seu chat_id sozinho e manda uma
mensagem de teste. Rode isso ANTES de subir pro GitHub -- se chegar mensagem
no seu Telegram, esta tudo certo.

Como usar (PowerShell):
    $env:TELEGRAM_BOT_TOKEN = "cole-aqui-o-token-do-BotFather"
    python ativar_bot.py

O token nao e gravado em disco em nenhum momento: ele vive so na variavel de
ambiente desta janela do terminal, e some quando voce fecha.
"""

import os
import sys

import requests

API = "https://api.telegram.org/bot{token}/{metodo}"


def chamar(token: str, metodo: str, **params):
    r = requests.get(API.format(token=token, metodo=metodo), params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("Nao encontrei o token na variavel TELEGRAM_BOT_TOKEN.\n")
        print("No PowerShell, rode assim (trocando pelo token do BotFather):")
        print('    $env:TELEGRAM_BOT_TOKEN = "123456789:ABCdef..."')
        print("    python ativar_bot.py")
        return 1

    # 1. o token e valido?
    try:
        eu = chamar(token, "getMe")
    except Exception as e:
        print(f"[ERRO] O token nao foi aceito pelo Telegram: {e}")
        print("Confira se copiou o token inteiro, sem espaco sobrando.")
        return 1

    bot = eu["result"]
    print(f"[OK] Token valido. Bot: {bot.get('first_name')} (@{bot.get('username')})")

    # 2. descobrir o chat_id nas mensagens que voce mandou pra ele
    updates = chamar(token, "getUpdates")["result"]
    chats = {}
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or {}
        chat = msg.get("chat")
        if chat:
            nome = chat.get("first_name") or chat.get("title") or "?"
            chats[chat["id"]] = nome

    if not chats:
        print("\n[ATENCAO] O bot ainda nao recebeu nenhuma mensagem sua.")
        print(f"Abra o Telegram, procure por @{bot.get('username')}, e mande")
        print("qualquer coisa pra ele (um 'oi' basta). Depois rode este script")
        print("de novo. Sem isso o Telegram nao deixa o bot te escrever.")
        return 1

    if len(chats) > 1:
        print("\n[ATENCAO] Encontrei mais de uma conversa:")
        for cid, nome in chats.items():
            print(f"    chat_id {cid}  ->  {nome}")
        print("Usando a primeira da lista para o teste.")

    chat_id, nome = next(iter(chats.items()))
    print(f"\n[OK] Seu chat_id e: {chat_id}   (conversa: {nome})")

    # 3. mensagem de teste
    texto = (
        "\U0001F4E1 Radar de IA conectado!\n\n"
        "Se voce esta lendo isso, o bot esta funcionando. "
        "As novidades de IA e tecnologia vao chegar por aqui."
    )
    envio = requests.post(
        API.format(token=token, metodo="sendMessage"),
        data={"chat_id": chat_id, "text": texto},
        timeout=20,
    )
    if envio.ok:
        print("[OK] Mensagem de teste enviada. Confere o seu Telegram.")
    else:
        print(f"[ERRO] Nao consegui enviar: {envio.text}")
        return 1

    print("\n--- Guarde estes dois valores para os Secrets do GitHub ---")
    print("TELEGRAM_BOT_TOKEN = o token que voce colou aqui")
    print(f"TELEGRAM_CHAT_ID   = {chat_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
