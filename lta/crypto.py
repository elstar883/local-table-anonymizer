"""Криптографические примитивы LTA (только локальные вычисления, без сети).

  * пароль  --scrypt-->  мастер-ключ
  * мастер-ключ --HKDF(info)--> ключи: mapping / verifier / столбцы
  * шифрование словаря: AES-256-GCM (nonce уникален на запись)
  * псевдонимы: HMAC-SHA256 (детерминированные индексы)
"""
import hashlib
import hmac
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**16, 8, 1
_SCRYPT_MAXMEM = 256 * 1024 * 1024
NONCE_LEN = 12


def derive_master(password: str, salt: bytes) -> bytes:
    """Вывод мастер-ключа из пароля (scrypt, N=2^16)."""
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM,
        dklen=32,
    )


def hkdf(master: bytes, info: bytes, length: int = 32) -> bytes:
    """Вывод производного ключа (HKDF-SHA256)."""
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(master)


def encrypt(key: bytes, plaintext: bytes) -> bytes:
    """AES-256-GCM. Возвращает nonce || ciphertext+tag."""
    nonce = os.urandom(NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def decrypt(key: bytes, blob: bytes) -> bytes:
    """Расшифровка AES-256-GCM (nonce||ct)."""
    nonce, ct = blob[:NONCE_LEN], blob[NONCE_LEN:]
    return AESGCM(key).decrypt(nonce, ct, None)


def mac(key: bytes, message: str) -> str:
    """HMAC-SHA256 (hex)."""
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def index_hmac(key: bytes, canonical: str, counter: int = 0) -> str:
    """8-символьный индекс-псевдоним из HMAC (с учётом счётчика коллизий)."""
    return mac(key, f"{canonical}|{counter}")[:8].upper()


def verifier(master: bytes) -> str:
    """Проверочное значение ключа (позволяет проверить пароль, не раскрывая данные)."""
    return hashlib.sha256(hkdf(master, b"verify")).hexdigest()
