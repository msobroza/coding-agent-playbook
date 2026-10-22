"""Pins of core skill ``domino-jobs`` (prU D50, D63; C-domino-jobs-04).

Every member gates on ``domino_project``, so the skill is checked on the Domino
probe (``tests/_budget_probe.py`` ``write_domino_probe``), which activates both
reproducibility rules.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_DOMINO: Final = {"domino_project": True}
_TAGS: Final = ("python", "domino", "jobs")

PINS: Final = CoreSkillPins(
    skill_id="domino-jobs",
    where="Job and Launcher scripts, requirements.txt, Dockerfiles and Domino dotfiles",
    members=("domino-run-manifest", "domino-mlflow-tracking"),
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
        "domino-run-manifest": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py",),
            priority=64,
            name="Domino run manifest",
            tags=(*_TAGS, "reproducibility"),
            section="reproducibility",
        ),
        "domino-mlflow-tracking": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py",),
            priority=65,
            name="Domino MLflow tracking",
            tags=(*_TAGS, "mlflow"),
            section="reproducibility",
        ),
    },
)
