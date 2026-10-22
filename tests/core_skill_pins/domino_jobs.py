"""Pins of core skill ``domino-jobs`` (prU D51, D52, D63; C-domino-jobs-01).

Sections and priorities follow mapping-domino-jobs.md (prU D17). Every member
gates on ``domino_project``, so the skill is checked on the Domino probe, which
activates every member pinned here.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_DOMINO: Final = {"domino_project": True}
_TAGS: Final = ("python", "domino", "jobs")
_SECTION: Final = "project-and-run-environment"

PINS: Final = CoreSkillPins(
    skill_id="domino-jobs",
    where="Domino Job and Launcher scripts, requirements.txt, environments and dotfiles",
    members=(
        "domino-project-types",
        "domino-secrets-in-env-vars",
        "domino-paths-from-env",
        "domino-api-proxy-auth",
        "domino-env-var-names",
        "domino-pinned-environments",
        "domino-environment-revisions",
    ),
    probe_inactive=frozenset(),
    probe="domino",
    section_ids=(
        _SECTION,
        "entry-points-and-exit-codes",
        "datasets",
        "scheduling-and-launching",
        "flow-tasks",
        "results-and-metrics",
        "reproducibility",
    ),
    rules={
        "domino-project-types": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py", "**/*.sh", ".dominoignore", ".dominoresults"),
            priority=20,
            name="Project types",
            tags=_TAGS,
            section=_SECTION,
        ),
        "domino-secrets-in-env-vars": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py", "**/*.sh", "requirements*.txt", "**/*.ipynb"),
            priority=21,
            name="Secrets in variables",
            tags=(*_TAGS, "security"),
            section=_SECTION,
        ),
        "domino-paths-from-env": RulePin(
            applies_if=_DOMINO,
            globs=("**/settings.py", "**/config.py", "**/paths.py", "**/*.py"),
            priority=22,
            name="Paths from the environment",
            tags=(*_TAGS, "configuration"),
            section=_SECTION,
        ),
        "domino-api-proxy-auth": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py", "**/dags/**/*.py"),
            priority=23,
            name="API proxy auth",
            tags=(*_TAGS, "security"),
            section=_SECTION,
        ),
        "domino-env-var-names": RulePin(
            applies_if=_DOMINO,
            globs=(
                "**/settings.py",
                "**/config.py",
                "**/*.sh",
                ".env.example",
                "**/Dockerfile*",
            ),
            priority=24,
            name="Variable names",
            tags=(*_TAGS, "configuration"),
            section=_SECTION,
        ),
        "domino-pinned-environments": RulePin(
            applies_if=_DOMINO,
            globs=("requirements*.txt", "**/Dockerfile*", "**/*.dockerfile", "pyproject.toml"),
            priority=25,
            name="Pinned environments",
            tags=("domino", "jobs", "dependencies"),
            section=_SECTION,
        ),
        "domino-environment-revisions": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py", "**/flows/**/*.py", "**/workflow*.py"),
            priority=26,
            name="Environment revisions",
            tags=_TAGS,
            section=_SECTION,
        ),
    },
)
