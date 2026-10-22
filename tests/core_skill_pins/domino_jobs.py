"""Pins of core skill ``domino-jobs`` (prU D50, D52, D63, D65; mapping-domino-jobs.md).

Every member gates on ``domino_project``, so the skill is checked on the Domino
probe, which activates every member pinned here.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_DOMINO: Final = {"domino_project": True}
_TAGS: Final = ("python", "domino", "jobs")
#: The globs both Launcher rules share (mapping-domino-jobs.md).
_LAUNCHER_GLOBS: Final = ("**/launcher*.py", "**/launcher*.sh", "**/launchers/**/*.py")

PINS: Final = CoreSkillPins(
    skill_id="domino-jobs",
    where="Domino Job and Launcher scripts, requirements.txt, environments and dotfiles",
    members=(
        "domino-job-exit-codes",
        "domino-job-entry-point",
        "domino-launcher-arguments",
        "domino-launcher-uploads",
        "domino-datasets-for-large-data",
        "domino-run-scoped-writes",
        "domino-dataset-snapshots",
        "domino-materialize-external-data",
    ),
    probe_inactive=frozenset(),
    probe="domino",
    section_ids=(
        "project-and-run-environment",
        "entry-points-and-exit-codes",
        "datasets",
        "scheduling-and-launching",
        "flow-tasks",
        "results-and-metrics",
        "reproducibility",
    ),
    rules={
        "domino-job-exit-codes": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py", "**/*.sh"),
            priority=27,
            name="Domino job exit codes",
            tags=_TAGS,
            section="entry-points-and-exit-codes",
        ),
        "domino-job-entry-point": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py", "**/*.sh", "**/*.ipynb"),
            priority=28,
            name="Domino job entry point",
            tags=_TAGS,
            section="entry-points-and-exit-codes",
        ),
        "domino-launcher-arguments": RulePin(
            applies_if=_DOMINO,
            globs=_LAUNCHER_GLOBS,
            priority=29,
            name="Domino Launcher arguments",
            tags=_TAGS,
            section="entry-points-and-exit-codes",
        ),
        "domino-launcher-uploads": RulePin(
            applies_if=_DOMINO,
            globs=_LAUNCHER_GLOBS,
            priority=30,
            name="Domino Launcher uploads",
            tags=_TAGS,
            section="entry-points-and-exit-codes",
        ),
        "domino-datasets-for-large-data": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py", ".dominoignore"),
            priority=40,
            name="Domino Datasets for large data",
            tags=_TAGS,
            section="datasets",
        ),
        "domino-run-scoped-writes": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py",),
            priority=41,
            name="Domino run-scoped writes",
            tags=_TAGS,
            section="datasets",
        ),
        "domino-dataset-snapshots": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py",),
            priority=42,
            name="Domino dataset snapshots",
            tags=_TAGS,
            section="datasets",
        ),
        "domino-materialize-external-data": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py",),
            priority=43,
            name="Domino materialized external data",
            tags=_TAGS,
            section="datasets",
        ),
    },
)
