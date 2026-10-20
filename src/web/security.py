"""Password hashing and session-token helpers.

Stdlib only: hashlib.scrypt for passwords, secrets for tokens, hashlib.sha256
for token-at-rest. No plaintext credential is ever stored or logged.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# scrypt parameters. n=2**14, r=8, p=1 is the widely used interactive setting;
# it costs ~16 MB and ~50-100 ms per hash, which is fine for login frequency.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32
_PREFIX = "scrypt"


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def hash_password(password: str) -> str:
    """Return `scrypt$n$r$p$salt_b64$hash_b64`.

    Raises ValueError on empty passwords so a caller cannot accidentally
    persist a blank credential.
    """
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_KEY_BYTES,
    )
    return f"{_PREFIX}${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64e(salt)}${_b64e(derived)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification. Returns False for malformed hashes."""
    try:
        prefix, n_s, r_s, p_s, salt_b64, hash_b64 = stored.split("$")
        if prefix != _PREFIX:
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = _b64d(salt_b64)
        expected = _b64d(hash_b64)
        derived = hashlib.scrypt(
            password.encode("utf-8"), salt=salt,
            n=n, r=r, p=p, dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, expected)


def new_session_token() -> str:
    """Opaque cookie value. Only its hash is persisted."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_matches(submitted: str | None, expected: str | None) -> bool:
    if not submitted or not expected:
        return False
    return hmac.compare_digest(submitted, expected)
