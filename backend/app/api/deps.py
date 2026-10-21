import hmac
import logging
import os

from fastapi import Header, HTTPException

_warned_missing_key = False


def require_api_key(x_api_key: str = Header(default="")):
    global _warned_missing_key
    expected = os.getenv("API_KEY", "")
    if not expected:
        if not _warned_missing_key:
            logging.getLogger(__name__).warning("API_KEY is unset; mutation routes are public")
            _warned_missing_key = True
        return
    if not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid API key")


def require_trigger_secret(secret: str = "", x_trigger_secret: str = Header(default="")):
    expected = os.getenv("TRIGGER_SECRET", "")
    supplied = x_trigger_secret or secret
    if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Invalid secret")
