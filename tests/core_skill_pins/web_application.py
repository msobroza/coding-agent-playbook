"""Pins of core skill ``web-application`` (prU D4, L0-15, C-web-application-01..04).

The two FastAPI rules re-homed by L0-15, plus the security rules vendored by
C-web-application-01, the database and async I/O rules vendored by
C-web-application-02 and the API design, app structure, observability and testing
rules vendored by C-web-application-03 and the api-conventions rules vendored by
C-web-application-04 at the mapping's priorities 63-65 (mapping-web-application.md order).
"""

from __future__ import annotations

from typing import Final

from tests._catalog import TEST_FILE_GLOBS
from tests.core_skill_pins import CoreSkillPins, RulePin

#: D23: ``web-*`` rules gate on any web framework.
_ANY_WEB_FRAMEWORK: Final = {"any_framework": ["fastapi", "flask", "django", "starlette"]}
#: D46(3): ``fastapi-*`` rules gate on FastAPI only.
_FASTAPI: Final = {"has_framework": ["fastapi"]}
#: FastAPI endpoint tests also need pytest.
_FASTAPI_PYTEST: Final = {"has_framework": ["fastapi", "pytest"]}
#: D23, D46(3): DB rules gate on any web framework plus SQLAlchemy or Alembic.
_WEB_DB_GATE: Final = {**_ANY_WEB_FRAMEWORK, "any_dependency": ["sqlalchemy", "alembic"]}
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
#: The api-conventions rules list the provider and app-entry modules separately.
_PROVIDER_FILES: Final = ("**/deps.py", "**/dependencies.py")
_APP_FILES: Final = ("**/main.py", "**/app.py", "**/asgi.py")
#: The route-module globs the mapping repeats across web-application rules.
_ROUTE_GLOBS: Final = (
    "**/routers/**/*.py",
    "**/routes/**/*.py",
    "**/api/**/*.py",
    "**/endpoints/**/*.py",
    "**/views.py",
    "**/views/**/*.py",
)

_DATABASE_RULES: Final = {
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
}

_ASYNC_IO_RULES: Final = {
    "fastapi-no-blocking-calls": RulePin(
        applies_if=_FASTAPI,
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
}

_API_DESIGN_RULES: Final = {
    "web-api-schemas": RulePin(
        applies_if=_ANY_WEB_FRAMEWORK,
        globs=("**/schemas.py", "**/schemas/**/*.py", *_ROUTE_GLOBS),
        priority=40,
        name="Web API schemas",
        tags=("python", "web", "api", "pydantic"),
        section="api-design",
    ),
    "fastapi-error-boundaries": RulePin(
        applies_if=_FASTAPI,
        globs=("**/*.py",),
        priority=41,
        name="FastAPI error boundaries",
        tags=("python", "fastapi", "errors"),
        section="api-design",
    ),
    "web-api-pagination": RulePin(
        applies_if=_ANY_WEB_FRAMEWORK,
        globs=(*_ROUTE_GLOBS, *_SERVICE_GLOBS),
        priority=42,
        name="Web API pagination",
        tags=("python", "web", "api"),
        section="api-design",
    ),
    "web-http-methods": RulePin(
        applies_if=_ANY_WEB_FRAMEWORK,
        globs=_ROUTE_GLOBS,
        priority=43,
        name="HTTP methods and status codes",
        tags=("python", "web", "api"),
        section="api-design",
    ),
}

_APP_STRUCTURE_RULES: Final = {
    "fastapi-app-wiring": RulePin(
        applies_if=_FASTAPI,
        globs=(*_APP_GLOBS, "**/settings.py", "**/config.py"),
        priority=44,
        name="FastAPI app wiring",
        tags=("python", "fastapi"),
        section="app-structure",
    ),
    "fastapi-dependency-providers": RulePin(
        applies_if=_FASTAPI,
        globs=(*_APP_GLOBS, *_ROUTE_GLOBS),
        priority=45,
        name="FastAPI dependency providers",
        tags=("python", "fastapi"),
        section="app-structure",
    ),
    "fastapi-thin-routes": RulePin(
        applies_if=_FASTAPI,
        globs=(*_ROUTE_GLOBS, *_SERVICE_GLOBS),
        priority=46,
        name="FastAPI thin routes",
        tags=("python", "fastapi"),
        section="app-structure",
    ),
}

_OBSERVABILITY_AND_TESTING_RULES: Final = {
    "fastapi-request-id-logging": RulePin(
        applies_if=_FASTAPI,
        globs=(
            *_APP_GLOBS,
            "**/middleware.py",
            "**/middleware/**/*.py",
            "**/observability.py",
        ),
        priority=60,
        name="FastAPI request ID logging",
        tags=("python", "fastapi", "logging"),
        section="observability",
    ),
    "fastapi-dependency-overrides": RulePin(
        applies_if=_FASTAPI_PYTEST,
        globs=TEST_FILE_GLOBS,
        priority=61,
        name="FastAPI dependency overrides in tests",
        tags=("python", "fastapi", "testing"),
        section="testing",
    ),
    "sqlalchemy-test-rollback": RulePin(
        applies_if={**_WEB_DB_GATE, "has_framework": ["pytest"]},
        globs=TEST_FILE_GLOBS,
        priority=62,
        name="SQLAlchemy test rollback",
        tags=("python", "sqlalchemy", "testing"),
        section="testing",
    ),
}

_API_CONVENTIONS_RULES: Final = {
    "fastapi-query-parameters": RulePin(
        applies_if=_FASTAPI,
        globs=(*_ROUTE_GLOBS, *_PROVIDER_FILES),
        priority=63,
        name="FastAPI query parameters",
        tags=("python", "fastapi", "api"),
        section="api-conventions",
    ),
    "web-api-resource-naming": RulePin(
        applies_if=_ANY_WEB_FRAMEWORK,
        globs=(*_ROUTE_GLOBS, *_APP_FILES, *_PROVIDER_FILES),
        priority=64,
        name="Resource naming",
        tags=("python", "web", "api"),
        section="api-conventions",
    ),
    "fastapi-openapi-metadata": RulePin(
        applies_if=_FASTAPI,
        globs=_ROUTE_GLOBS,
        priority=65,
        name="FastAPI OpenAPI metadata",
        tags=("python", "fastapi", "api"),
        section="api-conventions",
    ),
}

_RULES: Final = {
    **_DATABASE_RULES,
    **_ASYNC_IO_RULES,
    **_API_DESIGN_RULES,
    **_APP_STRUCTURE_RULES,
    **_OBSERVABILITY_AND_TESTING_RULES,
    **_API_CONVENTIONS_RULES,
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
        "web-api-schemas",
        "fastapi-error-boundaries",
        "web-api-pagination",
        "web-http-methods",
        "fastapi-app-wiring",
        "fastapi-dependency-providers",
        "fastapi-thin-routes",
        "fastapi-request-id-logging",
        "fastapi-dependency-overrides",
        "sqlalchemy-test-rollback",
        "fastapi-query-parameters",
        "web-api-resource-naming",
        "fastapi-openapi-metadata",
    ),
    # The reference probe has FastAPI, httpx and pytest but no SQLAlchemy or Alembic (D23).
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
