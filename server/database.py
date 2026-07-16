"""
database.py
Penyimpanan user (autentikasi) dan kode OTP menggunakan SQLite.
Password TIDAK pernah disimpan plaintext -> di-hash dengan PBKDF2-HMAC-SHA256
+ salt acak per user (modul bawaan hashlib, tanpa dependency tambahan).
"""
import hashlib
import os
import sqlite3
import time
import random
import threading

DB_PATH = os.path.join(os.path.dirname(__file__), "chatroom.db")
_lock = threading.Lock()
PBKDF2_ITERATIONS = 200_000


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    with _lock, _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0,
                language TEXT NOT NULL DEFAULT 'id',
                created_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                email TEXT PRIMARY KEY,
                code TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
        """)
        conn.commit()


def _hash_password(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return dk.hex()


def user_exists(email: str) -> bool:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
        return row is not None


def create_user(email: str, password: str) -> None:
    salt = os.urandom(16)
    pw_hash = _hash_password(password, salt)
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO users (email, salt, password_hash, verified, language, created_at) "
            "VALUES (?, ?, ?, 0, 'id', ?)",
            (email, salt.hex(), pw_hash, time.time()),
        )
        conn.commit()


def verify_password(email: str, password: str) -> bool:
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT salt, password_hash FROM users WHERE email=?", (email,)
        ).fetchone()
    if not row:
        return False
    salt_hex, stored_hash = row
    candidate = _hash_password(password, bytes.fromhex(salt_hex))
    return candidate == stored_hash


def is_verified(email: str) -> bool:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT verified FROM users WHERE email=?", (email,)).fetchone()
        return bool(row and row[0] == 1)


def set_verified(email: str) -> None:
    with _lock, _connect() as conn:
        conn.execute("UPDATE users SET verified=1 WHERE email=?", (email,))
        conn.commit()


def set_language(email: str, lang: str) -> None:
    with _lock, _connect() as conn:
        conn.execute("UPDATE users SET language=? WHERE email=?", (lang, email))
        conn.commit()


def get_language(email: str) -> str:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT language FROM users WHERE email=?", (email,)).fetchone()
        return row[0] if row else "id"


def generate_otp(email: str, ttl_seconds: int = 600) -> str:
    code = f"{random.randint(0, 999999):06d}"
    expires_at = time.time() + ttl_seconds
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO otp_codes (email, code, expires_at) VALUES (?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET code=excluded.code, expires_at=excluded.expires_at",
            (email, code, expires_at),
        )
        conn.commit()
    return code


def check_otp(email: str, code: str) -> bool:
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT code, expires_at FROM otp_codes WHERE email=?", (email,)
        ).fetchone()
        if not row:
            return False
        stored_code, expires_at = row
        if time.time() > expires_at:
            return False
        ok = stored_code == code
        if ok:
            conn.execute("DELETE FROM otp_codes WHERE email=?", (email,))
            conn.commit()
        return ok
