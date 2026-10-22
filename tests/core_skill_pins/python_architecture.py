"""Pins of core skill ``python-architecture`` (prU D4, D14): how modules depend on each other.

C-python-architecture-01 creates the skill with its seven sections and the eight rules
of the layers, boundaries and domain sections; later lanes append theirs.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_PY: Final = ("**/*.py",)
_DOMAIN: Final = (
    "**/domain/**/*.py",
    "**/models/**/*.py",
    "**/entities/**/*.py",
    "**/domain.py",
    "**/models.py",
)
_ROOTS: Final = (
    "**/main.py",
    "**/app.py",
    "**/__main__.py",
    "**/deps.py",
    "**/dependencies.py",
    "**/container.py",
    "**/bootstrap.py",
    "**/wiring.py",
    "**/cli.py",
)

PINS: Final = CoreSkillPins(
    skill_id="python-architecture",
    where="Package layout, entry points and imports between layers",
    members=(
        "arch-dependency-direction",
        "arch-composition-root",
        "arch-break-import-cycles",
        "arch-use-case-functions",
        "arch-typed-records-across-layers",
        "arch-ports",
        "arch-rich-domain-model",
        "arch-ubiquitous-language",
    ),
    probe_inactive=frozenset(),
    section_ids=(
        "layers",
        "boundaries",
        "domain",
        "persistence",
        "testing",
        "layout",
        "read-models",
    ),
    rules={
        "arch-dependency-direction": RulePin(
            applies_if={},
            globs=_PY,
            priority=20,
            name="Dependency direction",
            tags=("python", "architecture", "layers"),
            section="layers",
        ),
        "arch-composition-root": RulePin(
            applies_if={},
            globs=_ROOTS,
            priority=21,
            name="Composition root",
            tags=("python", "architecture", "di"),
            section="layers",
        ),
        "arch-break-import-cycles": RulePin(
            applies_if={},
            globs=_PY,
            priority=22,
            name="Break import cycles",
            tags=("python", "architecture", "imports"),
            section="layers",
        ),
        "arch-use-case-functions": RulePin(
            applies_if={},
            globs=_PY,
            priority=40,
            name="Use case functions",
            tags=("python", "architecture", "use-cases"),
            section="boundaries",
        ),
        "arch-typed-records-across-layers": RulePin(
            applies_if={},
            globs=_PY,
            priority=41,
            name="Typed records across layers",
            tags=("python", "architecture", "records"),
            section="boundaries",
        ),
        "arch-ports": RulePin(
            applies_if={},
            globs=_PY,
            priority=42,
            name="Ports at real seams",
            tags=("python", "architecture", "ports"),
            section="boundaries",
        ),
        "arch-rich-domain-model": RulePin(
            applies_if={},
            globs=_DOMAIN,
            priority=43,
            name="Rich domain model",
            tags=("python", "architecture", "ddd"),
            section="domain",
        ),
        "arch-ubiquitous-language": RulePin(
            applies_if={},
            globs=(*_DOMAIN, "**/services/**/*.py", "**/application/**/*.py"),
            priority=44,
            name="Ubiquitous language",
            tags=("python", "architecture", "ddd"),
            section="domain",
        ),
    },
)
