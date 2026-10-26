---
id: domino-app-verify-viewer-jwt
name: Verify the viewer token
description: "Verify the Authorization bearer token against the identity provider's cached key set (RS256, audience apps) before trusting any claim."
scope: scoped
globs:
  - "**/app.py"
  - "**/views.py"
  - "**/callbacks.py"
  - "**/auth.py"
  - "**/identity.py"
applies_if:
  domino_project: true
section: access
priority: 26
tags: [python, domino, apps, security]
---

# Verify the viewer token

## Description

With the secure identity flag, on by default in Domino 6.2, the proxy adds an `Authorization: Bearer <token>` header to every request. The token is signed by the platform's identity provider with RS256 for the audience `apps`, and only a verified token proves who the viewer is. Decoding it without checking the signature, or trusting a claim from a header anyone can set, lets a caller claim any identity.

Build the key-set client once, with caching and a timeout, and verify each token against it before reading the viewer's name, email or id.

## Bad Example

```python
import jwt


def viewer_email(token: str) -> str:
    claims = jwt.decode(token, options={"verify_signature": False})
    return claims["email"]
```

## Good Example

```python
from dataclasses import dataclass

import jwt

#: Check the claim names on a decoded token of your deployment.
USERNAME_CLAIM = "preferred_username"


class UnverifiedViewerError(Exception):
    """The request carries no token, or one that fails verification."""


@dataclass(frozen=True)
class Viewer:
    username: str


class ViewerVerifier:
    def __init__(self, jwks_url: str, *, timeout_s: float = 5.0) -> None:
        # Built once in the composition root; caches keys and refreshes on an unknown key id.
        self._keys = jwt.PyJWKClient(jwks_url, cache_keys=True, timeout=timeout_s)

    def verify(self, authorization: str | None) -> Viewer:
        if not authorization or not authorization.startswith("Bearer "):
            raise UnverifiedViewerError(
                "no viewer token: expected an 'Authorization: Bearer <token>' header"
            )
        token = authorization.removeprefix("Bearer ")
        try:
            key = self._keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience="apps",
                options={"require": ["exp", "aud", USERNAME_CLAIM]},
            )
        except jwt.PyJWTError as exc:
            raise UnverifiedViewerError(str(exc)) from exc
        return Viewer(username=str(claims[USERNAME_CLAIM]))
```

The key-set URL comes from a prefixed project variable, for example `MYAPP_JWKS_URL` (`domino-env-var-names`, domino-jobs skill); the boundary turns `UnverifiedViewerError` into a 401.

## Notes

- `web-jwt-validation` (web-application skill, where a web framework is declared) holds the general rule on pinned algorithms.
- The timeout follows `python-retries-and-timeouts` (python-coding skill, where the repo declares an HTTP client).
- PyJWT with its crypto extra must be in the environment; propose adding it through the repo's package manager, never unasked.
- Never hard-code the identity provider's address; it differs per deployment.
- Before 6.1.1 the flag was off by default and no token arrived; a missing header always means "not verified", never "trusted".
