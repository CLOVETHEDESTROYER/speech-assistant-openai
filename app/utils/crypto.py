import os
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Optional[Fernet]:
    key = os.getenv("DATA_ENCRYPTION_KEY")
    if not key:
        return None
    return Fernet(key.encode("utf-8"))


def encrypt_string(plaintext: str) -> str:
    f = _get_fernet()
    if not f:
        raise ValueError(
            "DATA_ENCRYPTION_KEY environment variable must be set for encryption")
    token = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_string(ciphertext: str) -> str:
    f = _get_fernet()
    if not f:
        raise ValueError(
            "DATA_ENCRYPTION_KEY environment variable must be set for decryption")
    try:
        data = f.decrypt(ciphertext.encode("utf-8"))
        return data.decode("utf-8")
    except InvalidToken:
        raise ValueError("Invalid or corrupted encrypted data")
