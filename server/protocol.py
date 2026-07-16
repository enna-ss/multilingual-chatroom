"""
protocol.py
Framing pesan untuk komunikasi TCP: setiap pesan diawali 4 byte panjang
(big-endian) lalu payload JSON UTF-8. Ini mencegah masalah TCP yang
menggabungkan/memotong pesan (message framing problem).
"""
import json
import socket
import struct

HEADER_SIZE = 4  # 4 byte = unsigned int, cukup untuk pesan hingga ~4GB


class ConnectionClosed(Exception):
    """Dilempar saat socket peer menutup koneksi."""
    pass


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Menerima persis n byte dari socket, atau melempar ConnectionClosed."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionClosed("Koneksi ditutup oleh peer")
        buf += chunk
    return buf


def send_msg(sock: socket.socket, obj: dict) -> None:
    """Mengirim satu pesan (dict) sebagai JSON dengan length-prefix."""
    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    header = struct.pack("!I", len(payload))
    sock.sendall(header + payload)


def recv_msg(sock: socket.socket) -> dict:
    """Menerima satu pesan (dict) yang dikirim dengan send_msg."""
    header = recv_exact(sock, HEADER_SIZE)
    (length,) = struct.unpack("!I", header)
    payload = recv_exact(sock, length)
    return json.loads(payload.decode("utf-8"))
