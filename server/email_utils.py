"""
email_utils.py
Mengirim kode OTP verifikasi ke email pengguna SUNGGUHAN via SMTP
(bukan simulasi/demo). Kredensial SMTP dibaca dari environment variable
(.env) supaya tidak di-hardcode di source code.

Cara pakai dengan Gmail:
1. Aktifkan 2-Step Verification di akun Google.
2. Buat "App Password" di https://myaccount.google.com/apppasswords
3. Isi SMTP_USER dan SMTP_PASSWORD (app password 16 karakter) di file .env
"""
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")


class EmailConfigError(Exception):
    pass


def send_otp_email(to_email: str, code: str) -> None:
    if not SMTP_USER or not SMTP_PASSWORD:
        raise EmailConfigError(
            "SMTP_USER / SMTP_PASSWORD belum diatur di file .env. "
            "Lihat .env.example untuk panduan."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Kode Verifikasi - Multilingual Chat Room"
    msg["From"] = SMTP_USER
    msg["To"] = to_email

    text = f"Kode verifikasi (OTP) Anda adalah: {code}\nBerlaku selama 10 menit."
    html = f"""
    <html><body>
      <p>Kode verifikasi (OTP) Anda adalah:</p>
      <h2 style="letter-spacing:4px">{code}</h2>
      <p>Kode berlaku selama 10 menit. Jangan bagikan kode ini ke siapa pun.</p>
    </body></html>
    """
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
