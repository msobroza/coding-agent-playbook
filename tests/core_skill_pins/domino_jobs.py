"""Pins of core skill ``domino-jobs`` (prU D4, D50, D63; mapping-domino-jobs.md).

Every member gates on ``domino_project``, so the standard reference probe activates
none of them (D63): they are all probe-inactive, and the skill is ``domino_only``, so
the probe gates check it on the Domino probe instead.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_DOMINO: Final = {"domino_project": True}
_FLOW_GLOBS: Final = ("**/*.py", "**/flows/**/*.py", "**/workflow*.py")
_MEMBERS: Final = (
    "domino-job-schedules",
    "domino-idempotent-jobs",
    "domino-spot-checkpoints",
    "domino-launch-jobs-from-code",
    "domino-flow-task-io",
    "domino-flow-task-purity",
    "domino-job-results",
    "domino-job-logging",
    "domino-job-stats-file",
    "domino-job-email-report",
)

PINS: Final = CoreSkillPins(
    skill_id="domino-jobs",
    where="Job and Launcher scripts, requirements.txt and Domino dotfiles",
    members=_MEMBERS,
    probe_inactive=frozenset(_MEMBERS),
    domino_only=True,
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
        "domino-job-schedules": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py", "**/*.sh", "README.md"),
            priority=44,
            name="Job schedules",
            tags=("python", "domino", "jobs", "scheduling"),
            section="scheduling-and-launching",
        ),
        "domino-idempotent-jobs": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py",),
            priority=45,
            name="Idempotent jobs",
            tags=("python", "domino", "jobs", "scheduling"),
            section="scheduling-and-launching",
        ),
        "domino-spot-checkpoints": RulePin(
            applies_if=_DOMINO,
            globs=("**/train*.py", "**/*.py"),
            priority=46,
            name="Spot checkpoints",
            tags=("python", "domino", "jobs", "scheduling"),
            section="scheduling-and-launching",
        ),
        "domino-launch-jobs-from-code": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py", "**/dags/**/*.py"),
            priority=47,
            name="Launching jobs from code",
            tags=("python", "domino", "jobs", "scheduling"),
            section="scheduling-and-launching",
        ),
        "domino-flow-task-io": RulePin(
            applies_if=_DOMINO,
            globs=_FLOW_GLOBS,
            priority=48,
            name="Flow task inputs and outputs",
            tags=("python", "domino", "jobs", "flows"),
            section="flow-tasks",
        ),
        "domino-flow-task-purity": RulePin(
            applies_if=_DOMINO,
            globs=("**/flows/**/*.py", "**/workflow*.py", "**/*.py"),
            priority=49,
            name="Pure Flow tasks",
            tags=("python", "domino", "jobs", "flows"),
            section="flow-tasks",
        ),
        "domino-job-results": RulePin(
            applies_if=_DOMINO,
            globs=(".dominoresults", ".dominoignore", ".dominokeep", "**/*.py"),
            priority=60,
            name="Job results",
            tags=("python", "domino", "jobs", "results"),
            section="results-and-metrics",
        ),
        "domino-job-logging": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py", "**/*.sh"),
            priority=61,
            name="Job logging",
            tags=("python", "domino", "jobs", "logging"),
            section="results-and-metrics",
        ),
        "domino-job-stats-file": RulePin(
            applies_if=_DOMINO,
            globs=("**/*.py", "dominostats.json"),
            priority=62,
            name="Job stats file",
            tags=("python", "domino", "jobs", "metrics"),
            section="results-and-metrics",
        ),
        "domino-job-email-report": RulePin(
            applies_if=_DOMINO,
            globs=("email.html", "**/*.py"),
            priority=63,
            name="Job email report",
            tags=("python", "domino", "jobs", "results"),
            section="results-and-metrics",
        ),
    },
)
