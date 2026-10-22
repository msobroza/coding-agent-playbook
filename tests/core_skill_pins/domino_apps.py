"""Pins of core skill ``domino-apps`` (prU D51, D52, D63; C-domino-apps-01).

Every member gates on ``domino_project``, so the skill is checked on the Domino
probe, which activates every member pinned here.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_DOMINO: Final = {"domino_project": True}
_TAGS: Final = ("python", "domino", "apps")
_SECURITY_TAGS: Final = (*_TAGS, "security")
_IDENTITY_GLOBS: Final = (
    "**/app.py",
    "**/views.py",
    "**/callbacks.py",
    "**/auth.py",
    "**/identity.py",
)

PINS: Final = CoreSkillPins(
    skill_id="domino-apps",
    where="Domino App code and its launch scripts (app.sh, start.sh)",
    members=(
        "domino-app-bind-host-port",
        "domino-app-url-prefix",
        "domino-app-launch-script",
        "domino-app-relative-urls",
        "domino-app-publisher-data-rights",
        "domino-app-viewer-identity",
        "domino-app-verify-viewer-jwt",
        "domino-app-viewer-token",
        "domino-app-starter-settings",
        "domino-app-endpoint-auth",
    ),
    probe_inactive=frozenset(),
    probe="domino",
    section_ids=("launch", "access", "state", "frameworks", "serving", "publishing"),
    rules={
        "domino-app-bind-host-port": RulePin(
            applies_if=_DOMINO,
            globs=("**/app.sh", "**/start.sh", "**/app.py", "**/run.py"),
            priority=20,
            name="Bind host and port",
            tags=_TAGS,
            section="launch",
        ),
        "domino-app-url-prefix": RulePin(
            applies_if=_DOMINO,
            globs=(
                "**/app.sh",
                "**/start.sh",
                "**/app.py",
                "**/run.py",
                "**/settings.py",
                "**/config.py",
            ),
            priority=21,
            name="URL prefix",
            tags=_TAGS,
            section="launch",
        ),
        "domino-app-launch-script": RulePin(
            applies_if=_DOMINO,
            globs=("**/app.sh", "**/start.sh"),
            priority=22,
            name="Launch script",
            tags=("domino", "apps", "shell"),
            section="launch",
        ),
        "domino-app-relative-urls": RulePin(
            applies_if=_DOMINO,
            globs=(
                "**/app.py",
                "**/run.py",
                "**/views.py",
                "**/callbacks.py",
                "**/pages/*.py",
                "**/templates/**/*.html",
                "**/static/**/*.js",
                "**/assets/**/*.js",
            ),
            priority=23,
            name="Relative URLs",
            tags=_TAGS,
            section="launch",
        ),
        "domino-app-publisher-data-rights": RulePin(
            applies_if=_DOMINO,
            globs=(*_IDENTITY_GLOBS, "**/data.py", "**/queries.py"),
            priority=24,
            name="Publisher data rights",
            tags=_SECURITY_TAGS,
            section="access",
        ),
        "domino-app-viewer-identity": RulePin(
            applies_if=_DOMINO,
            globs=_IDENTITY_GLOBS,
            priority=25,
            name="Viewer identity",
            tags=_SECURITY_TAGS,
            section="access",
        ),
        "domino-app-verify-viewer-jwt": RulePin(
            applies_if=_DOMINO,
            globs=_IDENTITY_GLOBS,
            priority=26,
            name="Verify the viewer token",
            tags=_SECURITY_TAGS,
            section="access",
        ),
        "domino-app-viewer-token": RulePin(
            applies_if=_DOMINO,
            globs=_IDENTITY_GLOBS,
            priority=27,
            name="Viewer token",
            tags=_SECURITY_TAGS,
            section="access",
        ),
        "domino-app-starter-settings": RulePin(
            applies_if=_DOMINO,
            globs=(
                "**/app.py",
                "**/run.py",
                "**/views.py",
                "**/callbacks.py",
                "**/pages/*.py",
                "**/settings.py",
                "**/config.py",
            ),
            priority=28,
            name="Starter's settings",
            tags=(*_TAGS, "configuration"),
            section="access",
        ),
        "domino-app-endpoint-auth": RulePin(
            applies_if=_DOMINO,
            globs=(
                "**/app.py",
                "**/run.py",
                "**/views.py",
                "**/callbacks.py",
                "**/pages/*.py",
                "**/clients.py",
                "**/settings.py",
            ),
            priority=29,
            name="Model endpoint auth",
            tags=_SECURITY_TAGS,
            section="access",
        ),
    },
)
