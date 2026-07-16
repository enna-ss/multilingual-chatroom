"""
socket_client.py
Wrapper TCP client yang dipakai oleh streamlit_app.py maupun test_client.py.
Menjalankan thread terpisah untuk menerima pesan (receiver thread) sehingga
UI tidak blocking, dan menaruh setiap pesan masuk ke dalam queue.Queue
yang aman untuk diakses lintas-thread.
"""
import base64
import os
import queue
import socket
import sys
import threading

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "server"))
from protocol import send_msg, recv_msg, ConnectionClosed  # noqa: E402


class ChatClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 5050):
        self.host = host
        self.port = port
        self.sock = None
        self.incoming = queue.Queue()
        self._recv_thread = None
        self._running = False

    def connect(self, timeout: float = 5.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(None)
        self._running = True
        self._recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._recv_thread.start()

    def _receive_loop(self):
        while self._running:
            try:
                msg = recv_msg(self.sock)
                self.incoming.put(msg)
            except ConnectionClosed:
                self.incoming.put({"type": "system", "message": "Koneksi ke server terputus."})
                break
            except OSError:
                break

    def _send(self, obj: dict):
        send_msg(self.sock, obj)

    def register(self, email: str, password: str):
        self._send({"type": "register", "email": email, "password": password})

    def verify_otp(self, email: str, otp: str):
        self._send({"type": "verify_otp", "email": email, "otp": otp})

    def login(self, email: str, password: str):
        self._send({"type": "login", "email": email, "password": password})

    def set_language(self, language: str):
        self._send({"type": "set_language", "language": language})

    def send_chat(self, text: str):
        self._send({"type": "chat", "text": text})

    def send_media(self, filename: str, mime: str, data: bytes):
        self._send({
            "type": "media",
            "filename": filename,
            "mime": mime,
            "data_b64": base64.b64encode(data).decode("ascii"),
        })

    def logout(self):
        try:
            self._send({"type": "logout"})
        except OSError:
            pass

    def close(self):
        self._running = False
        try:
            self.sock.close()
        except OSError:
            pass
