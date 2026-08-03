from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 240_000


@dataclass(frozen=True)
class PasswordCheck:
    valid: bool
    needs_rehash: bool = False


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Create a salted PBKDF2-SHA256 password hash.

    Stored format:
        pbkdf2_sha256$iterations$salt_hex$digest_hex
    """
    if not isinstance(password, str) or not password:
        raise ValueError("La contraseña no puede estar vacía.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, int(iterations)
    )
    return f"{ALGORITHM}${int(iterations)}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> PasswordCheck:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != ALGORITHM:
            return PasswordCheck(False)
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return PasswordCheck(False)

    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    valid = hmac.compare_digest(actual, expected)
    return PasswordCheck(valid, valid and iterations < DEFAULT_ITERATIONS)


def normalize_username(username: str) -> str:
    return "".join(str(username).strip().lower().split())


def validate_password_strength(password: str, username: str = "") -> list[str]:
    """Return human-readable problems. Demo credentials may bypass this in seeding."""
    problems: list[str] = []
    if len(password) < 8:
        problems.append("Debe tener al menos 8 caracteres.")
    if not any(ch.isalpha() for ch in password):
        problems.append("Debe incluir una letra.")
    if not any(ch.isdigit() for ch in password):
        problems.append("Debe incluir un número.")
    if username and password.lower() == username.lower():
        problems.append("No debe ser igual al usuario en una implementación real.")
    return problems
