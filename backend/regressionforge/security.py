from __future__ import annotations

import secrets


def valid_bearer_token(authorization: str, expected: str) -> bool:
    if not expected:
        return False
    scheme, separator, token = authorization.partition(" ")
    return (
        bool(separator)
        and scheme.lower() == "bearer"
        and bool(token)
        and secrets.compare_digest(token, expected)
    )
