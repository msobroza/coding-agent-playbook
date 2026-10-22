"""Pins of core skill ``web-application`` (prU D4, L0-15, C-web-application-01..04).

The two FastAPI rules re-homed by L0-15, plus the security rules vendored by
C-web-application-01 and the database and async I/O rules vendored by
C-web-application-02 (mapping-web-application.md order).
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

#: D23, D46(3): DB rules gate on any web framework plus SQLAlchemy or Alembic.
_WEB_DB_GATE: Final = {
    "any_framework": ["fastapi", "flask", "django", "starlette"],
    "any_dependency": ["sqlalchemy", "alembic"],
}
#: The app-entry and provider-module globs the mapping repeats.
_APP_GLOBS: Final = (
    "**/main.py",
    "**/app.py",
    "**/asgi.py",
    "**/deps.py",
    "**/dependencies.py",
)
#: The model and data-access globs the mapping repeats.
_DB_GLOBS: Final = (
    "**/models.py",
    "**/models/**/*.py",
    "**/db/**/*.py",
    "**/database.py",
    "**/repositories/**/*.py",
)
#: The service-layer glob the mapping repeats.
_SERVICE_GLOBS: Final = ("**/services/**/*.py",)
#: The route-module globs the mapping repeats across web-application rules.
_ROUTE_GLOBS: Final = (
    "**/routers/**/*.py",
    "**/routes/**/*.py",
    "**/api/**/*.py",
    "**/endpoints/**/*.py",
    "**/views.py",
    "**/views/**/*.py",
)

_RULES: Final = {
    "sqlalchemy-bound-parameters": RulePin(
        applies_if=_WEB_DB_GATE,
        globs=(*_DB_GLOBS, *_ROUTE_GLOBS, *_SERVICE_GLOBS),
        priority=25,
        name="Bound SQL parameters",
        tags=("python", "sqlalchemy", "database", "security"),
        section="database",
    ),
    "sqlalchemy-session-per-request": RulePin(
        applies_if={"has_framework": ["fastapi"], "any_dependency": ["sqlalchemy", "alembic"]},
        globs=(*_APP_GLOBS, *_DB_GLOBS),
        priority=26,
        name="Session per request",
        tags=("python", "fastapi", "sqlalchemy", "database"),
        section="database",
    ),
    "sqlalchemy-transaction-boundary": RulePin(
        applies_if=_WEB_DB_GATE,
        globs=(*_SERVICE_GLOBS, *_DB_GLOBS, *_APP_GLOBS),
        priority=27,
        name="Transaction boundary",
        tags=("python", "sqlalchemy", "database"),
        section="database",
    ),
    "sqlalchemy-eager-loading": RulePin(
        applies_if=_WEB_DB_GATE,
        globs=(*_DB_GLOBS, *_SERVICE_GLOBS, *_ROUTE_GLOBS),
        priority=28,
        name="Eager loading",
        tags=("python", "sqlalchemy", "database", "performance"),
        section="database",
    ),
    "alembic-migrations": RulePin(
        applies_if=_WEB_DB_GATE,
        globs=(
            "alembic.ini",
            "**/alembic/**/*.py",
            "**/migrations/**/*.py",
            *_DB_GLOBS,
            *_APP_GLOBS,
        ),
        priority=29,
        name="Alembic migrations",
        tags=("python", "alembic", "sqlalchemy", "database"),
        section="database",
    ),
    "sqlalchemy-2-style": RulePin(
        applies_if=_WEB_DB_GATE,
        globs=(*_DB_GLOBS, *_SERVICE_GLOBS),
        priority=30,
        name="SQLAlchemy 2.0 style",
        tags=("python", "sqlalchemy", "database", "typing"),
        section="database",
    ),
    "fastapi-no-blocking-calls": RulePin(
        applies_if={"has_framework": ["fastapi"]},
        globs=(*_ROUTE_GLOBS, *_APP_GLOBS, *_SERVICE_GLOBS),
        priority=31,
        name="No blocking calls in async routes",
        tags=("python", "fastapi", "async"),
        section="async-io",
    ),
    "httpx-shared-client": RulePin(
        applies_if={"has_framework": ["fastapi", "httpx"]},
        globs=(*_APP_GLOBS, *_SERVICE_GLOBS, "**/clients/**/*.py", "**/adapters/**/*.py"),
        priority=32,
        name="Shared httpx client",
        tags=("python", "fastapi", "httpx", "async"),
        section="async-io",
    ),
    "fastapi-error-boundaries": RulePin(
        applies_if={"has_framework": ["fastapi"]},
        globs=("**/*.py",),
        priority=41,
        name="FastAPI error boundaries",
        tags=("python", "fastapi", "errors"),
        section="api-design",
    ),
    "fastapi-app-wiring": RulePin(
        applies_if={"has_framework": ["fastapi"]},
        globs=(
            "**/routers/**/*.py",
            "**/routes/**/*.py",
            "**/api/**/*.py",
            "**/main.py",
            "**/app.py",
            "**/dependencies.py",
            "**/deps.py",
            "tests/**/*.py",
        ),
        priority=44,
        name="FastAPI app wiring",
        tags=("python", "fastapi"),
        section="app-structure",
    ),
}

PINS: Final = CoreSkillPins(
    skill_id="web-application",
    where="Web endpoints, database access and migrations",
    members=(
        "web-object-authorization",
        "web-jwt-validation",
        "web-password-hashing",
        "web-secure-tokens",
        "web-cors-origins",
        "sqlalchemy-bound-parameters",
        "sqlalchemy-session-per-request",
        "sqlalchemy-transaction-boundary",
        "sqlalchemy-eager-loading",
        "alembic-migrations",
        "sqlalchemy-2-style",
        "fastapi-no-blocking-calls",
        "httpx-shared-client",
        "fastapi-error-boundaries",
        "fastapi-app-wiring",
    ),
    # The reference probe has FastAPI and httpx but no SQLAlchemy or Alembic (D23).
    probe_inactive=frozenset(
        rule_id for rule_id, pin in _RULES.items() if "any_dependency" in pin.applies_if
    ),
    section_ids=(
        "security",
        "database",
        "async-io",
        "api-design",
        "app-structure",
        "observability",
        "testing",
        "api-conventions",
    ),
    rules=_RULES,
)
