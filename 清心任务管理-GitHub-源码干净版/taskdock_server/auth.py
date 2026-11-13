# -*- coding: utf-8 -*-
"""Password hashing and opaque session tokens (stdlib only)."""

import hashlib
import hmac
import secrets

ITERATIONS = 180000


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", (password or "").encode("utf-8"), salt.encode("ascii"), ITERATIONS
    )
    return "pbkdf2_sha256$%d$%s$%s" % (ITERATIONS, salt, digest.hex())


def verify_password(password, encoded):
    try:
        scheme, iterations, salt, digest = (encoded or "").split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode("utf-8"), salt.encode("ascii"),
            int(iterations),
        )
        return hmac.compare_digest(candidate.hex(), digest)
    except Exception:
        return False


def new_token():
    return secrets.token_urlsafe(32)
