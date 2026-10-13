import hashlib
import secrets

from pwdlib import PasswordHash

PASSWORD_HASH = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return PASSWORD_HASH.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_HASH.verify(password, password_hash)
    except Exception:
        return False


def create_secret() -> str:
    return secrets.token_urlsafe(48)


def secret_digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()
