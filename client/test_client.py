"""
test_client.py
Client baris-perintah (CLI) MURNI socket, tanpa Streamlit. Dipakai untuk:
  1. Menguji server TCP secara independen (pembuktian arsitektur client-server).
  2. Mengambil screenshot komunikasi client-server mentah untuk laporan.

Cara pakai:
    python client/test_client.py
lalu ikuti prompt (register/login/otp), lalu ketik pesan chat.
Ketik /lang <kode>  untuk ganti bahasa (contoh: /lang en)
Ketik /quit         untuk keluar
"""
import os
import sys
import threading
import time

sys.path.append(os.path.dirname(__file__))
from socket_client import ChatClient


def print_incoming(client: ChatClient):
    while True:
        msg = client.incoming.get()
        mtype = msg.get("type")
        if mtype == "chat":
            print(f"\n[{msg['from']} ({msg['original_lang']})] {msg['text']}")
        elif mtype == "media":
            print(f"\n[MEDIA] {msg['from']} mengirim file: {msg['filename']} ({msg['mime']})")
        elif mtype == "system":
            print(f"\n*** {msg['message']} ***")
        elif mtype == "user_list":
            print(f"\n(Online: {', '.join(msg['users'])})")
        elif mtype == "error":
            print(f"\n[ERROR] {msg['message']}")
        elif mtype == "auth_result":
            print(f"\n[AUTH] {msg['message']}")
        elif mtype == "otp_sent":
            print(f"\n[INFO] {msg['message']}")
        print("> ", end="", flush=True)


def main():
    host = input("Host server [127.0.0.1]: ") or "127.0.0.1"
    port = int(input("Port server [5050]: ") or "5050")

    client = ChatClient(host, port)
    client.connect()
    threading.Thread(target=print_incoming, args=(client,), daemon=True).start()

    action = input("register/login? [login]: ") or "login"
    email = input("Email: ")
    password = input("Password: ")

    if action == "register":
        client.register(email, password)
        time.sleep(1)
        otp = input("Masukkan kode OTP dari email: ")
        client.verify_otp(email, otp)
        time.sleep(1)

    client.login(email, password)
    time.sleep(1)

    print("Ketik pesan (atau /lang <kode>, /quit):")
    while True:
        text = input("> ")
        if text == "/quit":
            client.logout()
            client.close()
            break
        elif text.startswith("/lang "):
            client.set_language(text.split(" ", 1)[1].strip())
        elif text.strip():
            client.send_chat(text)


if __name__ == "__main__":
    main()
