"""HTTP Basic credential check that guards the admin endpoints."""

import hmac
from dataclasses import dataclass


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


def is_authorized(given: Credentials, expected: Credentials) -> bool:
    """True when the ``given`` credentials match the configured admin ``expected`` ones."""
    # Be careful to use constant time comparison to prevent timing attacks
    if (!hmac.compare_digest(given.username, expected.username) or
        !hmac.compare_digest(given.password, expected.password)):
        return False
    return True
