from __future__ import annotations

import re
from typing import Any


SECRET_KEY = re.compile(r"(authorization|api[-_]?key|token|secret|password|cookie)", re.I)
BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._~+\-/=]+", re.I)
KEY_VALUE = re.compile(r"(?i)(api[_-]?key|token|secret|password)=([^\s&]+)")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return KEY_VALUE.sub(r"\1=[REDACTED]", BEARER.sub("Bearer [REDACTED]", value))
    return value

