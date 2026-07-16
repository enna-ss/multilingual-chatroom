"""
translator.py
Menerjemahkan pesan chat di SISI SERVER menggunakan deep-translator
(free, tanpa API key, memakai backend Google Translate).
Setiap client bisa punya bahasa pilihan berbeda -> server menerjemahkan
pesan yang sama berkali-kali, sekali per bahasa tujuan yang unik.
"""
from functools import lru_cache
from deep_translator import GoogleTranslator

SUPPORTED_LANGUAGES = {
    "id": "Indonesian",
    "en": "English",
    "zh-CN": "Chinese (Simplified)",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "th": "Thai",
    "vi": "Vietnamese",
    "ms": "Malay",
    "hi": "Hindi",
    "ru": "Russian",
    "pt": "Portuguese",
}


@lru_cache(maxsize=2048)
def _cached_translate(text: str, target_lang: str) -> str:
    return GoogleTranslator(source="auto", target=target_lang).translate(text)


def translate_text(text: str, target_lang: str) -> str:
    """Menerjemahkan `text` ke `target_lang`. Jika gagal (mis. tidak ada
    internet), kembalikan teks asli + penanda supaya UI tidak rusak."""
    if not text.strip():
        return text
    try:
        return _cached_translate(text, target_lang)
    except Exception:
        return f"{text} [terjemahan gagal]"
