"""Request authentication built on the JWT verifier.

Derived (paraphrased) from CVE-2026-27962 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

from app.jwt_verify import verify_token

_SECRET = "server-signing-secret"


def authenticate(request: dict[str, str]) -> dict[str, object]:
    """Authenticate a request from its bearer token and return the claims.

    ``request['authorization']`` is fully attacker-controlled — it is the raw
    token presented by the client — and is passed straight to the verifier whose
    result is then treated as the authenticated identity.
    """
    token = request["authorization"].removeprefix("Bearer ").strip()
    return verify_token(token, _SECRET)
