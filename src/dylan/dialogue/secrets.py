"""Drop candidates that contain the live key or an sk- token. No general classifier."""

from __future__ import annotations

import re

from dylan.memory.constants import SECRET_PATTERN

_TOKEN = re.compile(SECRET_PATTERN)


def has_secret(text: str, api_key: str) -> bool:
    if api_key and api_key in text:
        return True
    return _TOKEN.search(text) is not None
