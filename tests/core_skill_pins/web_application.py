"""Pins of core skill ``web-application`` (prU D4, L0-15, C-web-application-03)."""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

#: D23: ``web-*`` rules gate on any web framework.
_ANY_WEB_FRAMEWORK: Final = {"any_framework": ["fastapi", "flask", "django", "starlette"]}
#: D46(3): ``fastapi-*`` rules gate on FastAPI only.
_FASTAPI: Final = {"has_framework": ["fastapi"]}
#: The route-module globs the API rules share.
_ROUTE_GLOBS: Final = (
    "**/routers/**/*.py",
    "**/routes/**/*.py",
    "**/api/**/*.py",
    "**/endpoints/**/*.py",
    "**/views.py",
    "**/views/**/*.py",
)
#: The app-entry and provider-module globs the app-structure rules share.
_ENTRY_GLOBS: Final = (
    "**/main.py",
    "**/app.py",
    "**/asgi.py",
    "**/deps.py",
    "**/dependencies.py",
)

PINS: Final = CoreSkillPins(
    skill_id="web-application",
    where="Web endpoints, database access and migrations",
    members=(
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
    ),
    probe_inactive=frozenset({"sqlalchemy-test-rollback"}),
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
    rules={
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
            globs=(*_ROUTE_GLOBS, "**/services/**/*.py"),
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
        "fastapi-app-wiring": RulePin(
            applies_if=_FASTAPI,
            globs=(*_ENTRY_GLOBS, "**/settings.py", "**/config.py"),
            priority=44,
            name="FastAPI app wiring",
            tags=("python", "fastapi"),
            section="app-structure",
        ),
        "fastapi-dependency-providers": RulePin(
            applies_if=_FASTAPI,
            globs=(*_ENTRY_GLOBS, *_ROUTE_GLOBS),
            priority=45,
            name="FastAPI dependency providers",
            tags=("python", "fastapi"),
            section="app-structure",
        ),
        "fastapi-thin-routes": RulePin(
            applies_if=_FASTAPI,
            globs=(*_ROUTE_GLOBS, "**/services/**/*.py"),
            priority=46,
            name="FastAPI thin routes",
            tags=("python", "fastapi"),
            section="app-structure",
        ),
        "fastapi-request-id-logging": RulePin(
            applies_if=_FASTAPI,
            globs=(
                *_ENTRY_GLOBS,
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
            applies_if={"has_framework": ["fastapi", "pytest"]},
            globs=("tests/**/*.py",),
            priority=61,
            name="FastAPI dependency overrides in tests",
            tags=("python", "fastapi", "testing"),
            section="testing",
        ),
        "sqlalchemy-test-rollback": RulePin(
            applies_if={
                **_ANY_WEB_FRAMEWORK,
                "any_dependency": ["sqlalchemy", "alembic"],
                "has_framework": ["pytest"],
            },
            globs=("tests/**/*.py",),
            priority=62,
            name="SQLAlchemy test rollback",
            tags=("python", "sqlalchemy", "testing"),
            section="testing",
        ),
    },
)
