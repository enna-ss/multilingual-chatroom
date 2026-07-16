"""
tcp_server.py
=====================================================================
SERVER TCP - Multilingual Chat Room
=====================================================================
Arsitektur : Client-Server, protokol TCP (connection-oriented, reliable)
Konkurensi : 1 thread per koneksi client (threading.Thread)
Framing    : length-prefixed JSON (lihat protocol.py)

Alur protokol (tipe pesan dari client -> server):
  register     {email, password}
  verify_otp   {email, otp}
  login        {email, password}
  set_language {language}
  chat         {text}
  media        {filename, mime, data_b64}
  logout       {}

Balasan server -> client:
  auth_result  {ok, stage, message}
  otp_sent     {message}
  system       {message}
  user_list    {users: [email, ...]}
  chat         {from, text, original_lang, timestamp}
  media        {from, filename, mime, timestamp, url_path}
  error        {message}
=====================================================================
"""
import os
import socket
import threading
import time
import base64
import traceback
import uuid

from protocol import send_msg, recv_msg, ConnectionClosed
from database import (
    init_db, user_exists, create_user, verify_password, is_verified,
    set_verified, generate_otp, check_otp, set_language, get_language,
)
from email_utils import send_otp_email, EmailConfigError
from translator import translate_text, SUPPORTED_LANGUAGES

HOST = os.getenv("CHAT_HOST", "0.0.0.0")
PORT = int(os.getenv("CHAT_PORT", "5050"))
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# clients: dict[socket] -> {"email": str, "language": str, "lock": threading.Lock}
clients_lock = threading.Lock()
clients = {}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def broadcast_system(message: str, exclude_sock=None):
    with clients_lock:
        targets = list(clients.items())
    for sock, info in targets:
        if sock is exclude_sock:
            continue
        try:
            send_msg(sock, {"type": "system", "message": message})
        except OSError:
            pass


def broadcast_user_list():
    with clients_lock:
        emails = [info["email"] for info in clients.values() if info.get("email")]
        targets = list(clients.items())
    for sock, _ in targets:
        try:
            send_msg(sock, {"type": "user_list", "users": emails})
        except OSError:
            pass


def broadcast_chat(sender_email: str, text: str, sender_lang: str):
    """Menerjemahkan pesan untuk SETIAP client sesuai bahasa pilihan mereka."""
    timestamp = time.time()
    with clients_lock:
        targets = list(clients.items())
    for sock, info in targets:
        target_lang = info.get("language", "id")
        try:
            translated = translate_text(text, target_lang)
            send_msg(sock, {
                "type": "chat",
                "from": sender_email,
                "text": translated,
                "original_lang": sender_lang,
                "timestamp": timestamp,
            })
        except OSError:
            pass
        except Exception:
            traceback.print_exc()


def broadcast_media(sender_email: str, filename: str, mime: str):
    timestamp = time.time()
    with clients_lock:
        targets = list(clients.items())
    for sock, _info in targets:
        try:
            send_msg(sock, {
                "type": "media",
                "from": sender_email,
                "filename": filename,
                "mime": mime,
                "timestamp": timestamp,
                "url_path": os.path.join(UPLOAD_DIR, filename),
            })
        except OSError:
            pass


def handle_client(conn: socket.socket, addr):
    log(f"Koneksi baru dari {addr}")
    session = {"email": None, "language": "id"}

    try:
        while True:
            try:
                msg = recv_msg(conn)
            except ConnectionClosed:
                break
            except (ConnectionResetError, TimeoutError, OSError) as e:
                log(f"Error socket dari {addr}: {e}")
                break

            mtype = msg.get("type")

            # ---------- REGISTER ----------
            if mtype == "register":
                email = (msg.get("email") or "").strip().lower()
                password = msg.get("password") or ""
                if not email or "@" not in email or len(password) < 6:
                    send_msg(conn, {"type": "auth_result", "ok": False, "stage": "register",
                                     "message": "Email tidak valid atau password < 6 karakter."})
                    continue
                if user_exists(email):
                    send_msg(conn, {"type": "auth_result", "ok": False, "stage": "register",
                                     "message": "Email sudah terdaftar. Silakan login."})
                    continue
                try:
                    create_user(email, password)
                    code = generate_otp(email)
                    send_otp_email(email, code)
                    send_msg(conn, {"type": "otp_sent",
                                     "message": f"Kode OTP telah dikirim ke {email}."})
                except EmailConfigError as e:
                    send_msg(conn, {"type": "error", "message": str(e)})
                except Exception as e:
                    log(f"Gagal kirim email: {e}")
                    send_msg(conn, {"type": "error",
                                     "message": f"Gagal mengirim email OTP: {e}"})

            # ---------- VERIFY OTP ----------
            elif mtype == "verify_otp":
                email = (msg.get("email") or "").strip().lower()
                otp = str(msg.get("otp") or "")
                if check_otp(email, otp):
                    set_verified(email)
                    send_msg(conn, {"type": "auth_result", "ok": True, "stage": "verify",
                                     "message": "Verifikasi berhasil! Silakan login."})
                else:
                    send_msg(conn, {"type": "auth_result", "ok": False, "stage": "verify",
                                     "message": "Kode OTP salah atau kedaluwarsa."})

            # ---------- LOGIN ----------
            elif mtype == "login":
                email = (msg.get("email") or "").strip().lower()
                password = msg.get("password") or ""
                if not user_exists(email) or not verify_password(email, password):
                    send_msg(conn, {"type": "auth_result", "ok": False, "stage": "login",
                                     "message": "Email atau password salah."})
                    continue
                if not is_verified(email):
                    send_msg(conn, {"type": "auth_result", "ok": False, "stage": "login",
                                     "message": "Email belum diverifikasi OTP."})
                    continue

                session["email"] = email
                session["language"] = get_language(email)
                with clients_lock:
                    clients[conn] = {"email": email, "language": session["language"]}

                send_msg(conn, {"type": "auth_result", "ok": True, "stage": "login",
                                 "message": "Login berhasil.",
                                 "language": session["language"]})
                broadcast_system(f"{email} bergabung ke chat room.", exclude_sock=conn)
                broadcast_user_list()

            # ---------- SET LANGUAGE ----------
            elif mtype == "set_language":
                lang = msg.get("language", "id")
                if lang not in SUPPORTED_LANGUAGES:
                    send_msg(conn, {"type": "error", "message": "Bahasa tidak didukung."})
                    continue
                session["language"] = lang
                if session["email"]:
                    set_language(session["email"], lang)
                    with clients_lock:
                        if conn in clients:
                            clients[conn]["language"] = lang
                send_msg(conn, {"type": "system", "message": f"Bahasa diatur ke {lang}."})

            # ---------- CHAT ----------
            elif mtype == "chat":
                if not session["email"]:
                    send_msg(conn, {"type": "error", "message": "Anda harus login dahulu."})
                    continue
                text = (msg.get("text") or "").strip()
                if text:
                    broadcast_chat(session["email"], text, session["language"])

            # ---------- MEDIA ----------
            elif mtype == "media":
                if not session["email"]:
                    send_msg(conn, {"type": "error", "message": "Anda harus login dahulu."})
                    continue
                try:
                    raw = base64.b64decode(msg["data_b64"])
                    ext = os.path.splitext(msg.get("filename", "file"))[1]
                    safe_name = f"{uuid.uuid4().hex}{ext}"
                    with open(os.path.join(UPLOAD_DIR, safe_name), "wb") as f:
                        f.write(raw)
                    broadcast_media(session["email"], safe_name, msg.get("mime", ""))
                except Exception as e:
                    log(f"Gagal simpan media: {e}")
                    send_msg(conn, {"type": "error", "message": f"Upload gagal: {e}"})

            # ---------- LOGOUT ----------
            elif mtype == "logout":
                break

            else:
                send_msg(conn, {"type": "error", "message": f"Tipe pesan tidak dikenal: {mtype}"})

    except Exception:
        traceback.print_exc()
    finally:
        with clients_lock:
            clients.pop(conn, None)
        try:
            conn.close()
        except OSError:
            pass
        if session["email"]:
            broadcast_system(f"{session['email']} keluar dari chat room.")
            broadcast_user_list()
        log(f"Koneksi {addr} ditutup.")


def start_server(host: str = HOST, port: int = PORT):
    init_db()
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((host, port))
    server_sock.listen(50)
    log(f"Server TCP mendengarkan di {host}:{port}")

    try:
        while True:
            conn, addr = server_sock.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        log("Server dihentikan (KeyboardInterrupt).")
    finally:
        server_sock.close()


if __name__ == "__main__":
    start_server()
