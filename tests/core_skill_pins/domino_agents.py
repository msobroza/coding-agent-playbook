"""Pins of core skill ``domino-agents`` (prU D4, D50, D63; mapping-domino-agents.md).

Every member gates on ``domino_project``, so the standard reference probe activates
none of them (D63): they are all probe-inactive, and the skill is ``domino_only``, so
the probe gates check it on the Domino probe instead.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_DOMINO: Final = {"domino_project": True}
_CONFIG_GLOBS: Final = (
    "**/settings.py",
    "**/config.py",
    "**/*config*.yaml",
    "**/*config*.yml",
    "**/.env.example",
)
_TRACING_GLOBS: Final = ("**/*agent*.py", "**/tracing.py", "**/chat_app.py", "**/main.py")
_EVAL_GLOBS: Final = (
    "**/*_eval*.py",
    "**/eval_*.py",
    "**/evaluat*.py",
    "**/evals/**/*.py",
    "**/*questions*.csv",
    "**/evaluators.py",
)
_MEMBERS: Final = (
    "domino-agent-settings",
    "domino-agent-config-file",
    "domino-agent-trace-entrypoint",
    "domino-agent-manual-spans",
    "domino-agent-sdk-names",
    "domino-agent-dev-eval-job",
    "domino-agent-evaluators",
    "domino-agent-eval-out-of-band",
    "domino-agent-prod-eval-watermark",
)

PINS: Final = CoreSkillPins(
    skill_id="domino-agents",
    where="Agent service code, launch script, agent config, evaluation Jobs and their tests",
    members=_MEMBERS,
    probe_inactive=frozenset(_MEMBERS),
    domino_only=True,
    section_ids=(
        "secrets",
        "service",
        "configuration",
        "tracing",
        "evaluation",
        "a2a",
        "testing",
    ),
    rules={
        "domino-agent-settings": RulePin(
            applies_if=_DOMINO,
            globs=_CONFIG_GLOBS,
            priority=45,
            name="Domino agent settings",
            tags=("python", "domino", "agents", "settings"),
            section="configuration",
        ),
        "domino-agent-config-file": RulePin(
            applies_if=_DOMINO,
            globs=_CONFIG_GLOBS,
            priority=46,
            name="Agent config file",
            tags=("python", "domino", "agents", "config"),
            section="configuration",
        ),
        "domino-agent-trace-entrypoint": RulePin(
            applies_if=_DOMINO,
            globs=_TRACING_GLOBS,
            priority=47,
            name="Traced request function",
            tags=("python", "domino", "agents", "tracing"),
            section="tracing",
        ),
        "domino-agent-manual-spans": RulePin(
            applies_if=_DOMINO,
            globs=_TRACING_GLOBS,
            priority=48,
            name="Manual agent spans",
            tags=("python", "domino", "agents", "tracing"),
            section="tracing",
        ),
        "domino-agent-sdk-names": RulePin(
            applies_if=_DOMINO,
            globs=(*_TRACING_GLOBS, "**/pyproject.toml", "**/requirements*.txt"),
            priority=49,
            name="Domino agent SDK names",
            tags=("python", "domino", "agents", "tracing"),
            section="tracing",
        ),
        "domino-agent-dev-eval-job": RulePin(
            applies_if=_DOMINO,
            globs=_EVAL_GLOBS,
            priority=50,
            name="Development evaluation Job",
            tags=("python", "domino", "agents", "evaluation"),
            section="evaluation",
        ),
        "domino-agent-evaluators": RulePin(
            applies_if=_DOMINO,
            globs=_EVAL_GLOBS,
            priority=51,
            name="Agent evaluators",
            tags=("python", "domino", "agents", "evaluation"),
            section="evaluation",
        ),
        "domino-agent-eval-out-of-band": RulePin(
            applies_if=_DOMINO,
            globs=(*_EVAL_GLOBS, *_TRACING_GLOBS),
            priority=52,
            name="Production evaluation out of band",
            tags=("python", "domino", "agents", "evaluation"),
            section="evaluation",
        ),
        "domino-agent-prod-eval-watermark": RulePin(
            applies_if=_DOMINO,
            globs=_EVAL_GLOBS,
            priority=53,
            name="Production evaluation watermark",
            tags=("python", "domino", "agents", "evaluation"),
            section="evaluation",
        ),
    },
)
