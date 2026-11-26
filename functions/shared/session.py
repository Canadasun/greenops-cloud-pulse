"""Short-lived session tokens (F12, Role 5 – Idowu Ayeni).

The dashboard site signs people in with Microsoft (Static Web Apps authentication). Its /api/token function (swa-api/) then
issues a token that says only who the person is; the Fleet API checks it here. Format: JWT with HMAC-SHA256 (RFC 7519). Only this
one algorithm is accepted, so a token that names another one, or none, fails.
"""
import base64
import hashlib
import hmac
import json
from datetime import timedelta

from .models import utcnow

ISSUER, AUDIENCE = "greenops-dashboard", "greenops-fleet-api"
DEFAULT_LIFE_S = 15 * 60
MAX_LIFE_S = 60 * 60
CLOCK_SKEW_S = 60
MIN_KEY = 32


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(message: str, key: str) -> str:
    return _b64(hmac.new(key.encode(), message.encode(), hashlib.sha256).digest())


def issue(email, key, now=None, ttl_s=DEFAULT_LIFE_S, audience=AUDIENCE):
    """Used by the tests and the live checks; in production swa-api issues the same token."""
    now = now or utcnow()
    claims = {"iss": ISSUER, "aud": audience, "email": email, "iat": int(now.timestamp()), "exp": int((now + timedelta(seconds=ttl_s)).timestamp())}
    message = _b64(b'{"alg":"HS256","typ":"JWT"}') + "." + _b64(json.dumps(claims).encode())
    return f"{message}.{_sign(message, key)}"


def verify(token, key, now=None):
    """Return the claims of a valid token, otherwise None. Never raises on bad input."""
    if not key or len(key) < MIN_KEY or not isinstance(token, str):
        return None
    try:
        head, body, signature = token.split(".")
        if not hmac.compare_digest(_sign(f"{head}.{body}", key).encode(), signature.encode()):
            return None
        if json.loads(_unb64(head)).get("alg") != "HS256":
            return None
        claims = json.loads(_unb64(body))
        t = (now or utcnow()).timestamp()
        valid = (claims["iss"] == ISSUER and claims["aud"] == AUDIENCE and claims["iat"] <= t + CLOCK_SKEW_S
                 and t < claims["exp"] <= claims["iat"] + MAX_LIFE_S and isinstance(claims["email"], str) and claims["email"])
        return claims if valid else None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
