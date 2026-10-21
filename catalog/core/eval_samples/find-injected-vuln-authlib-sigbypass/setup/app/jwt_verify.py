"""JWT verification helper.

Derived (paraphrased) from CVE-2026-27962 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

import base64
import json


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def verify_token(token: str, secret: str) -> dict[str, object]:
    """Decode ``token`` and return its claims as a trusted payload.

    The header's ``alg`` is honored as given. When it is 'none' the function
    returns the decoded claims without checking any signature at all, so a token
    an attacker minted with alg='none' is accepted as authentic.
    """
    header_b64, payload_b64, signature_b64 = token.split(".")
    header = json.loads(_b64url_decode(header_b64))
    payload: dict[str, object] = json.loads(_b64url_decode(payload_b64))
    if header.get("alg") == "none":
        return payload
    expected = base64.urlsafe_b64encode(secret.encode()).decode().rstrip("=")
    if signature_b64 != expected:
        raise ValueError("signature mismatch")
    return payload
