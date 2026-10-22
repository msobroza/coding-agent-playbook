"""Pins of core skill ``domino-apps`` (prU D51, D52, D63; C-domino-apps-03).

Every member gates on ``domino_project``, so the skill is checked on the Domino
probe. ``domino-app-production-server`` also needs Flask or Dash, which the probe
does not declare, so the probe leaves that one member off.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_DOMINO: Final = {"domino_project": True}
_TAGS: Final = ("python", "domino", "apps")
_DOCS_TAGS: Final = ("domino", "apps", "docs")

PINS: Final = CoreSkillPins(
    skill_id="domino-apps",
    where="Domino App code and its launch scripts (app.sh, start.sh)",
    members=(
        "domino-app-production-server",
        "domino-app-proxy-limits",
        "domino-app-external-resources",
        "domino-app-publish-from-commit",
        "domino-app-deployment-record",
        "domino-app-sharing-mode",
        "domino-app-workspace-preview",
        "domino-app-logging",
    ),
    probe_inactive=frozenset({"domino-app-production-server"}),
    probe="domino",
    section_ids=("launch", "access", "state", "frameworks", "serving", "publishing"),
    rules={
        "domino-app-production-server": RulePin(
            applies_if={"domino_project": True, "any_dependency": ["flask", "dash"]},
            globs=("**/app.sh", "**/start.sh", "**/wsgi.py", "**/gunicorn.conf.py"),
            priority=45,
            name="Production server",
            tags=(*_TAGS, "gunicorn"),
            section="serving",
        ),
        "domino-app-proxy-limits": RulePin(
            applies_if=_DOMINO,
            globs=(
                "**/app.py",
                "**/run.py",
                "**/views.py",
                "**/callbacks.py",
                "**/pages/*.py",
            ),
            priority=46,
            name="Proxy limits",
            tags=_TAGS,
            section="serving",
        ),
        "domino-app-external-resources": RulePin(
            applies_if=_DOMINO,
            globs=("**/templates/**/*.html", "**/assets/**", "**/static/**", "**/app.py"),
            priority=47,
            name="External resources",
            tags=(*_TAGS, "security"),
            section="serving",
        ),
        "domino-app-publish-from-commit": RulePin(
            applies_if=_DOMINO,
            globs=("**/app.sh", "**/start.sh"),
            priority=60,
            name="Publish from a commit",
            tags=("domino", "apps", "git"),
            section="publishing",
        ),
        "domino-app-deployment-record": RulePin(
            applies_if=_DOMINO,
            globs=("**/README.md", "**/app.sh", "docs/**/*.md"),
            priority=61,
            name="Deployment record",
            tags=_DOCS_TAGS,
            section="publishing",
        ),
        "domino-app-sharing-mode": RulePin(
            applies_if=_DOMINO,
            globs=("**/README.md",),
            priority=62,
            name="Sharing mode",
            tags=(*_DOCS_TAGS, "security"),
            section="publishing",
        ),
        "domino-app-workspace-preview": RulePin(
            applies_if=_DOMINO,
            globs=("**/app.sh", "**/start.sh", "**/dev.sh"),
            priority=63,
            name="Workspace preview",
            tags=("domino", "apps", "shell"),
            section="publishing",
        ),
        "domino-app-logging": RulePin(
            applies_if=_DOMINO,
            globs=("**/app.py", "**/logging_config.py", "**/app.sh"),
            priority=64,
            name="App logging",
            tags=(*_TAGS, "logging"),
            section="publishing",
        ),
    },
)
