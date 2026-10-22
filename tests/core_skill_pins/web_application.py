"""Pins of core skill ``web-application`` (prU D4, L0-15): the two FastAPI rules re-homed.

The api-conventions section is vendored (C-web-application-04): its three rules are
pinned at the mapping's priorities 63-65.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

#: Route modules under the common layouts (prU mapping: the api-conventions rules' globs).
_ROUTE_FILES: Final = (
    "**/routers/**/*.py",
    "**/routes/**/*.py",
    "**/api/**/*.py",
    "**/endpoints/**/*.py",
    "**/views.py",
    "**/views/**/*.py",
)
_PROVIDER_FILES: Final = ("**/deps.py", "**/dependencies.py")
_APP_FILES: Final = ("**/main.py", "**/app.py", "**/asgi.py")
#: prU D23: a web-application rule that is not FastAPI-specific gates on any web framework.
_ANY_WEB_FRAMEWORK: Final = {"any_framework": ["fastapi", "flask", "django", "starlette"]}

PINS: Final = CoreSkillPins(
    skill_id="web-application",
    where="Web endpoints, database access and migrations",
    members=(
        "fastapi-error-boundaries",
        "fastapi-app-wiring",
        "fastapi-query-parameters",
        "web-api-resource-naming",
        "fastapi-openapi-metadata",
    ),
    probe_inactive=frozenset(),
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
        "fastapi-query-parameters": RulePin(
            applies_if={"has_framework": ["fastapi"]},
            globs=(*_ROUTE_FILES, *_PROVIDER_FILES),
            priority=63,
            name="FastAPI query parameters",
            tags=("python", "fastapi", "api"),
            section="api-conventions",
        ),
        "web-api-resource-naming": RulePin(
            applies_if=_ANY_WEB_FRAMEWORK,
            globs=(*_ROUTE_FILES, *_APP_FILES, *_PROVIDER_FILES),
            priority=64,
            name="Resource naming",
            tags=("python", "web", "api"),
            section="api-conventions",
        ),
        "fastapi-openapi-metadata": RulePin(
            applies_if={"has_framework": ["fastapi"]},
            globs=_ROUTE_FILES,
            priority=65,
            name="FastAPI OpenAPI metadata",
            tags=("python", "fastapi", "api"),
            section="api-conventions",
        ),
    },
)
