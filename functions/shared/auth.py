"""Fail-closed bearer credentials, mapped to server-owned operator identities.

Keys are provisioned out of band and never compiled into the dashboard bundle.
Local ingestion and workflow callbacks use separate service credentials.
"""
import hmac
import json
import os


def bearer(req):
    value = req.headers.get("Authorization", "")
    return value[7:] if value.startswith("Bearer ") else ""


def service_authorized(req, setting):
    expected, supplied = os.getenv(setting, ""), bearer(req)
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def operator(req):
    supplied = bearer(req)
    if not supplied:
        return None
    tokens = json.loads(os.getenv("OPERATOR_TOKENS", "{}"))
    for token, name in tokens.items():
        if isinstance(name, str) and name.strip() and hmac.compare_digest(token, supplied):
            return name.strip()[:120]
    return None
