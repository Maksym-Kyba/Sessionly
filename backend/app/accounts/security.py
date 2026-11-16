"""Cryptographic primitives for psychologist OAuth sessions."""

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken


def random_token(num_bytes: int = 32) -> str:
    return secrets.token_urlsafe(num_bytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_pkce_pair() -> tuple[str, str]:
    verifier = random_token(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge.rstrip(b"=").decode("ascii")


def encrypt_secret(key: str, value: str) -> str:
    return Fernet(key.encode("ascii")).encrypt(value.encode()).decode("ascii")


def decrypt_secret(key: str, value: str) -> str:
    try:
        return Fernet(key.encode("ascii")).decrypt(value.encode("ascii")).decode()
    except (InvalidToken, ValueError) as exc:
        raise ValueError("OAuth transaction secret is invalid") from exc


def csrf_token(session_token: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), session_token.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def csrf_token_matches(session_token: str, secret: str, candidate: str | None) -> bool:
    return bool(candidate) and hmac.compare_digest(csrf_token(session_token, secret), candidate)
