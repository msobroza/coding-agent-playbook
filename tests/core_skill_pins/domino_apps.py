"""Pins of core skill ``domino-apps`` (prU D50, D63; C-domino-apps-02).

Every member gates on ``domino_project``, so the skill is checked on the Domino
probe (``tests/_budget_probe.py`` ``write_domino_probe``). That probe has no Dash,
Flask, Streamlit or Shiny dependency, so it leaves those framework rules off.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

#: The globs the persistence and state rules share (mapping-domino-apps.md).
_STATE_GLOBS: Final = (
    "**/app.py",
    "**/run.py",
    "**/views.py",
    "**/callbacks.py",
    "**/pages/*.py",
    "**/storage.py",
    "**/store.py",
)
_DOMINO: Final = {"domino_project": True}
_TAGS: Final = ("python", "domino", "apps")

PINS: Final = CoreSkillPins(
    skill_id="domino-apps",
    where="Domino App code and its launch scripts (app.sh, start.sh)",
    members=(
        "domino-app-external-persistence",
        "domino-app-concurrent-writes",
        "domino-app-replica-state",
        "domino-app-dash",
        "domino-app-flask",
        "domino-app-streamlit",
        "domino-app-shiny",
        "domino-app-static-site",
    ),
    probe_inactive=frozenset(
        {"domino-app-dash", "domino-app-flask", "domino-app-streamlit", "domino-app-shiny"}
    ),
    probe="domino",
    section_ids=("launch", "access", "state", "frameworks", "serving", "publishing"),
    rules={
        "domino-app-external-persistence": RulePin(
            applies_if=_DOMINO,
            globs=_STATE_GLOBS,
            priority=30,
            name="Domino App external persistence",
            tags=_TAGS,
            section="state",
        ),
        "domino-app-concurrent-writes": RulePin(
            applies_if=_DOMINO,
            globs=_STATE_GLOBS,
            priority=31,
            name="Domino App concurrent writes",
            tags=_TAGS,
            section="state",
        ),
        "domino-app-replica-state": RulePin(
            applies_if=_DOMINO,
            globs=_STATE_GLOBS[:5],
            priority=32,
            name="Domino App replica state",
            tags=_TAGS,
            section="state",
        ),
        "domino-app-dash": RulePin(
            applies_if={"domino_project": True, "has_dependency": ["dash"]},
            globs=("**/app.py", "**/callbacks.py", "**/layout.py", "**/app.sh"),
            priority=40,
            name="Dash on Domino",
            tags=(*_TAGS, "dash"),
            section="frameworks",
        ),
        "domino-app-flask": RulePin(
            applies_if={"domino_project": True, "has_framework": ["flask"]},
            globs=(
                "**/app.py",
                "**/run.py",
                "**/wsgi.py",
                "**/views.py",
                "**/templates/**/*.html",
            ),
            priority=41,
            name="Flask on Domino",
            tags=(*_TAGS, "flask"),
            section="frameworks",
        ),
        "domino-app-streamlit": RulePin(
            applies_if={"domino_project": True, "has_dependency": ["streamlit"]},
            globs=(
                "**/app.sh",
                "**/.streamlit/config.toml",
                "**/streamlit_app.py",
                "**/app.py",
                "**/pages/*.py",
            ),
            priority=42,
            name="Streamlit on Domino",
            tags=(*_TAGS, "streamlit"),
            section="frameworks",
        ),
        "domino-app-shiny": RulePin(
            applies_if={"domino_project": True, "has_dependency": ["shiny"]},
            globs=("**/app.sh", "**/app.py"),
            priority=43,
            name="Shiny for Python on Domino",
            tags=(*_TAGS, "shiny"),
            section="frameworks",
        ),
        "domino-app-static-site": RulePin(
            applies_if=_DOMINO,
            globs=("**/app.py", "**/site/**/*.html", "**/index.html"),
            priority=44,
            name="Static site on Domino",
            tags=_TAGS,
            section="frameworks",
        ),
    },
)
