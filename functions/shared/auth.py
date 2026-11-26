"""Who may call the Fleet API (F12, Role 5 – Idowu Ayeni). Everything is refused unless a credential proves otherwise.

  viewer    – any person with a valid session token (shared/session.py): may read
  operator  – a viewer whose email is in OPERATOR_EMAILS ({"email": "display name"}): may also acknowledge and set demo faults
  services  – router, Logic App and trucks, each with its own credential that opens only its own endpoint
"""
import hmac
import json
import logging
import os
from functools import wraps

from . import session

log = logging.getLogger("auth")


def bearer(req):
    value = req.headers.get("Authorization", "")
    return value[7:] if value.startswith("Bearer ") else ""


def service_authorized(req, setting):
    expected, supplied = os.getenv(setting, ""), bearer(req)
    return bool(expected and supplied and hmac.compare_digest(expected.encode(), supplied.encode()))


def viewer(req):
    """The signed-in person's email, or None."""
    claims = session.verify(bearer(req), os.getenv("SESSION_SIGNING_KEY", ""))
    return claims["email"].strip().lower()[:254] if claims else None


def operator(req):
    """The display name of a signed-in operator, or None."""
    email = viewer(req)
    try:
        names = {k.strip().lower(): v for k, v in json.loads(os.getenv("OPERATOR_EMAILS", "{}")).items()}
    except (ValueError, AttributeError):
        log.error("OPERATOR_EMAILS is not a JSON object: nobody can operate")
        return None
    name = names.get(email) if email else None
    return name.strip()[:120] if isinstance(name, str) and name.strip() else None


def may_view(req, service=None):
    # AUTH_MODE=open exists for isolated automated tests only; it never opens the write endpoints.
    return bool(viewer(req) or (service and service_authorized(req, service)) or os.getenv("AUTH_MODE") == "open")


def guard(refuse, check):
    """Decorator for an HTTP function: run it only when check(req) is empty, otherwise refuse(error, status)."""
    def decorate(fn):
        @wraps(fn)
        def guarded(req):
            problem = check(req)
            return refuse(*problem) if problem else fn(req)
        return guarded
    return decorate


def needs_viewer(req, service=None):
    return None if may_view(req, service) else ({"error": "sign in to view the fleet"}, 401)


def needs_operator(req):
    if not viewer(req):
        return {"error": "sign in first"}, 401
    return None if operator(req) else ({"error": "your account can view only; operators can act"}, 403)
