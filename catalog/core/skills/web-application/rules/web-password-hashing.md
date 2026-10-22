---
id: web-password-hashing
name: Hash passwords with Argon2
description: "Store passwords only as Argon2id hashes, verify and rehash through the library off the event loop, and answer unknown emails in the same time and with the same error."
version: 1
scope: scoped
globs:
  - "**/auth.py"
  - "**/auth/**/*.py"
  - "**/security.py"
  - "**/security/**/*.py"
  - "**/services/**/*.py"
applies_if:
  any_framework: ["fastapi", "flask", "django", "starlette"]
section: security
priority: 22
tags: [python, web, security, passwords]
---

# Hash passwords with Argon2

## Description

Store passwords only as hashes from a slow, salted, memory-hard algorithm. `hashlib.sha256` and `md5` are built to be fast, so a leaked table is brute-forced at billions of guesses per second, and unsalted digests repeat for equal passwords. Use Argon2id through `pwdlib`, verify with the library instead of `==`, rehash when parameters change, and run the CPU-heavy work in a thread from `async def` code.

## Bad Example

```python
import hashlib


async def register(session: AsyncSession, email: str, password: str) -> User:
    digest = hashlib.sha256(password.encode()).hexdigest()  # fast and unsalted
    user = User(email=email, password_hash=digest)
    session.add(user)
    await session.commit()
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        return None  # returns instantly: response time reveals which emails exist
    if user.password_hash != hashlib.sha256(password.encode()).hexdigest():
        return None
    return user
```

## Good Example

```python
import asyncio

from pwdlib import PasswordHash
from pydantic import SecretStr


class PasswordHasher:
    """Built once by create_app (or the lifespan) and passed to the auth code."""

    def __init__(self) -> None:
        self._hash = PasswordHash.recommended()  # Argon2id with current parameters
        self._dummy = self._hash.hash("dummy-password-for-timing")  # at startup, not import

    async def hash(self, password: SecretStr) -> str:
        # Argon2 takes tens of milliseconds of CPU; keep it off the event loop
        return await asyncio.to_thread(self._hash.hash, password.get_secret_value())

    async def verify(self, password: SecretStr, stored: str | None) -> tuple[bool, str | None]:
        secret = password.get_secret_value()
        if stored is None:
            # Spend the same time as a real check so timing does not reveal valid emails
            await asyncio.to_thread(self._hash.verify, secret, self._dummy)
            return False, None
        return await asyncio.to_thread(self._hash.verify_and_update, secret, stored)


async def authenticate(
    session: AsyncSession, hasher: PasswordHasher, email: str, password: SecretStr
) -> User | None:
    user = await session.scalar(select(User).where(User.email == email))
    valid, updated_hash = await hasher.verify(password, user.password_hash if user else None)
    if user is None or not valid:
        return None
    if updated_hash is not None:  # stored hash used outdated parameters
        user.password_hash = updated_hash
        await session.commit()
    return user
```

## Notes

- When the project has no password hasher yet, propose adding `pwdlib` with its `argon2` extra through the project's package manager, never unasked; do not introduce `passlib` in new code. bcrypt is acceptable for existing hashes, but it only reads the first 72 bytes of input.
- Return the same error for "unknown email" and "wrong password" (`401 Incorrect email or password`) so responses do not reveal which accounts exist. A 409 on sign-up reveals the same thing; where account existence must stay private, answer new and existing emails alike and notify the owner by email instead.
- Throttle login and password-reset endpoints, at the reverse proxy or with the rate limiter the project already has; propose adding a limiter dependency only with the user's agreement. Read limits from settings, and keep their counters in a shared store when the app runs on several instances.
- Cap password length in the request model (`Field(max_length=128)`) so oversized input cannot be used to burn hashing CPU.
- Accept passwords as `SecretStr` so they stay out of `repr`, logs, and tracebacks; call `get_secret_value()` only where you hash or verify.
- Never log passwords or hashes, and never include `password_hash` in a response model (`web-api-schemas`).
- In a plain `def` endpoint FastAPI already runs the function in a thread pool, so a sync hasher can be called directly there (`fastapi-no-blocking-calls`).
- A framework with built-in auth (Django) keeps its own hasher setting, with the Argon2 hasher listed first in `PASSWORD_HASHERS`.
