"""Server-side compromised-password screening using the padded Pwned Passwords range API."""

import hashlib
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

_MAX_RANGE_BYTES = 128_000


def require_safe_password(password: str) -> None:
    digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    request = Request(f"https://api.pwnedpasswords.com/range/{digest[:5]}", headers={
        "Add-Padding": "true", "User-Agent": "AllSafe-AI-Trading",
    })
    try:
        with urlopen(request, timeout=5) as response:
            body = response.read(_MAX_RANGE_BYTES + 1)
        if not 0 < len(body) <= _MAX_RANGE_BYTES:
            raise ValueError
        hashes = dict(line.split(":", 1) for line in body.decode("ascii").splitlines() if line)
        count = int(hashes.get(digest[5:], "0"))
        if not hashes:
            raise ValueError
    except (URLError, TimeoutError, OSError, ValueError):
        raise HTTPException(status_code=503, detail="Password screening is temporarily unavailable. Try again shortly.") from None
    if count > 0:
        raise HTTPException(status_code=422, detail="This password has appeared in a data breach. Choose a different password.")
