"""
streamlit_app.py
=====================================================================
Multilingual Chat Room - Web Client (Streamlit)
=====================================================================
Aplikasi ini adalah GUI client yang terhubung ke server TCP
(server/tcp_server.py) melalui raw socket (bukan HTTP), sesuai
requirement mata kuliah Pemrograman Jaringan.

Server TCP dijalankan otomatis di dalam proses Streamlit yang sama
(sekali per proses, lihat ensure_server_running()) sehingga hanya
port Streamlit (8501) yang perlu di-expose ke Cloudflare Tunnel.
Setiap browser/tab yang membuka aplikasi ini menjadi SATU koneksi
socket TCP terpisah ke server -> arsitektur client-server tetap nyata,
bukan simulasi.
=====================================================================
"""
import os
import queue
import sys
import time
import mimetypes

import streamlit as st
from streamlit_autorefresh import st_autorefresh
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.join(os.path.dirname(__file__), "server"))
sys.path.append(os.path.join(os.path.dirname(__file__), "client"))

from socket_client import ChatClient  # noqa: E402
from translator import SUPPORTED_LANGUAGES  # noqa: E402

CHAT_HOST = os.getenv("CHAT_HOST_INTERNAL", "127.0.0.1")
CHAT_PORT = int(os.getenv("CHAT_PORT", "5050"))

st.set_page_config(page_title="Multilingual Chat Room", page_icon="💬", layout="wide")


@st.cache_resource(show_spinner=False)
def ensure_server_running(host: str, port: int):
    """Memastikan server TCP hidup di proses ini. Dijalankan hanya SEKALI
    per proses Streamlit berkat st.cache_resource (dibagi lintas-session)."""
    import socket as _socket
    import threading

    def is_up():
        try:
            s = _socket.create_connection((host, port), timeout=1)
            s.close()
            return True
        except OSError:
            return False

    if not is_up():
        from tcp_server import start_server
        t = threading.Thread(target=start_server, kwargs={"host": "0.0.0.0", "port": port}, daemon=True)
        t.start()
        for _ in range(20):
            if is_up():
                break
            time.sleep(0.25)
    return True


ensure_server_running(CHAT_HOST, CHAT_PORT)

# ---------------------------------------------------------------- state ----
defaults = {
    "client": None,
    "logged_in": False,
    "stage": "login",   # login | register | otp
    "email": "",
    "pending_email": "",
    "messages": [],
    "users_online": [],
    "language": "id",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def get_client() -> ChatClient:
    if st.session_state.client is None:
        c = ChatClient(CHAT_HOST, CHAT_PORT)
        c.connect()
        st.session_state.client = c
    return st.session_state.client


def wait_for(client: ChatClient, expected_types, timeout: float = 8.0):
    """Menunggu balasan server dengan tipe tertentu, sambil menampung
    pesan lain (mis. chat masuk) ke session_state.messages."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = max(0.1, deadline - time.time())
        try:
            msg = client.incoming.get(timeout=remaining)
        except queue.Empty:
            break
        if msg.get("type") in expected_types:
            return msg
        drain_one(msg)
    return None


def drain_one(msg: dict):
    mtype = msg.get("type")
    if mtype in ("chat", "media", "system"):
        st.session_state.messages.append(msg)
    elif mtype == "user_list":
        st.session_state.users_online = msg.get("users", [])


def drain_queue(client: ChatClient):
    while True:
        try:
            msg = client.incoming.get_nowait()
        except queue.Empty:
            break
        drain_one(msg)


# ------------------------------------------------------------- sidebar ----
with st.sidebar:
    st.header("💬 Multilingual Chat Room")
    st.caption("Client TCP socket ⇄ Server (127.0.0.1:%d)" % CHAT_PORT)
    if st.session_state.logged_in:
        st.success(f"Login sebagai: {st.session_state.email}")
        lang_codes = list(SUPPORTED_LANGUAGES.keys())
        lang_labels = [f"{c} - {SUPPORTED_LANGUAGES[c]}" for c in lang_codes]
        idx = lang_codes.index(st.session_state.language) if st.session_state.language in lang_codes else 0
        choice = st.selectbox("Bahasa terjemahan saya", lang_labels, index=idx)
        chosen_code = choice.split(" - ")[0]
        if chosen_code != st.session_state.language:
            st.session_state.language = chosen_code
            get_client().set_language(chosen_code)
            st.toast(f"Bahasa diatur ke {SUPPORTED_LANGUAGES[chosen_code]}")

        st.divider()
        st.write("**Online:**")
        for u in st.session_state.users_online:
            st.write(f"🟢 {u}")

        if st.button("Logout", use_container_width=True):
            get_client().logout()
            get_client().close()
            for k, v in defaults.items():
                st.session_state[k] = v
            st.rerun()
    else:
        st.info("Silakan login atau daftar akun untuk mulai chat.")

# --------------------------------------------------------- auth screens ----
if not st.session_state.logged_in:
    st.title("Selamat datang 👋")
    tab_login, tab_register = st.tabs(["Login", "Daftar (Register)"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pw")
            submitted = st.form_submit_button("Login")
        if submitted:
            client = get_client()
            client.login(email, password)
            resp = wait_for(client, {"auth_result"})
            if resp and resp.get("ok"):
                st.session_state.logged_in = True
                st.session_state.email = email.strip().lower()
                st.session_state.language = resp.get("language", "id")
                st.rerun()
            else:
                st.error(resp["message"] if resp else "Server tidak merespons.")

    with tab_register:
        st.caption("Kode OTP akan dikirim ke email Anda")
        if st.session_state.stage != "otp":
            with st.form("register_form"):
                remail = st.text_input("Email", key="reg_email")
                rpw = st.text_input("Password (min 6 karakter)", type="password", key="reg_pw")
                rsub = st.form_submit_button("Daftar & Kirim OTP")
            if rsub:
                client = get_client()
                client.register(remail, rpw)
                resp = wait_for(client, {"otp_sent", "auth_result", "error"})
                if resp and resp.get("type") == "otp_sent":
                    st.session_state.stage = "otp"
                    st.session_state.pending_email = remail.strip().lower()
                    st.success(resp["message"])
                    st.rerun()
                elif resp:
                    st.error(resp.get("message", "Registrasi gagal."))
                else:
                    st.error("Server tidak merespons.")
        else:
            st.write(f"Masukkan kode OTP yang dikirim ke **{st.session_state.pending_email}**")
            with st.form("otp_form"):
                otp = st.text_input("Kode OTP (6 digit)")
                osub = st.form_submit_button("Verifikasi")
            if osub:
                client = get_client()
                client.verify_otp(st.session_state.pending_email, otp)
                resp = wait_for(client, {"auth_result"})
                if resp and resp.get("ok"):
                    st.success(resp["message"])
                    st.session_state.stage = "login"
                else:
                    st.error(resp["message"] if resp else "Verifikasi gagal.")
            if st.button("Batal / kembali ke daftar"):
                st.session_state.stage = "login"
                st.rerun()

# --------------------------------------------------------------- chat ----
else:
    st_autorefresh(interval=2000, key="chat_autorefresh")
    drain_queue(get_client())

    st.title("💬 Multilingual Chat Room")
    chat_box = st.container(height=480, border=True)
    with chat_box:
        for msg in st.session_state.messages:
            mtype = msg.get("type")
            if mtype == "system":
                st.caption(f"— {msg['message']} —")
            elif mtype == "chat":
                is_me = msg["from"] == st.session_state.email
                who = "Saya" if is_me else msg["from"]
                st.markdown(f"**{who}** _(asli: {msg.get('original_lang','?')})_")
                st.write(msg["text"])
            elif mtype == "media":
                who = "Saya" if msg["from"] == st.session_state.email else msg["from"]
                st.markdown(f"**{who}** mengirim media:")
                path = msg.get("url_path")
                mime = msg.get("mime", "")
                if path and os.path.exists(path):
                    if mime.startswith("image/"):
                        st.image(path)
                    elif mime.startswith("video/"):
                        st.video(path)
                    elif mime.startswith("audio/"):
                        st.audio(path)
                    else:
                        st.write(f"📎 {msg['filename']}")

    st.divider()
    col1, col2 = st.columns([4, 1])
    with col1:
        with st.form("chat_form", clear_on_submit=True):
            text = st.text_input("Ketik pesan...", label_visibility="collapsed")
            send = st.form_submit_button("Kirim", use_container_width=True)
        if send and text.strip():
            get_client().send_chat(text.strip())

    with col2:
        with st.popover("📎 Upload media"):
            up = st.file_uploader("Foto / Video / Audio", type=None, key="uploader")
            if up is not None and st.button("Kirim media"):
                mime = up.type or mimetypes.guess_type(up.name)[0] or "application/octet-stream"
                get_client().send_media(up.name, mime, up.getvalue())
                st.success("Media dikirim!")
