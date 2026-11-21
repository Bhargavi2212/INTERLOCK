"""Shared access code for /plants, /changes, /jobs. Never logged, never echoed."""

import hmac

from fastapi import Header, HTTPException

from app.config import get_access_code


def require_access(x_access_code: str | None = Header(default=None)) -> None:
    expected = get_access_code()
    if not expected:
        raise HTTPException(status_code=503, detail="access code not configured")
    given = (x_access_code or "").encode()
    if not given or not hmac.compare_digest(given, expected.encode()):
        raise HTTPException(status_code=401, detail="access code required")
