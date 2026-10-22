"""Pins of core skill ``domino-agents`` (prU D50, D52, D63, C-domino-agents-01 and -02).

Every member gates on ``domino_project``, so the reference probe activates none
and the skill is checked on the Domino probe instead (``probe="domino"``), which
activates every member.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_DOMINO: Final = {"domino_project": True}
_DOMINO_FASTAPI: Final = {"domino_project": True, "has_framework": ["fastapi"]}
_SECRETS_GLOBS: Final = (
    "**/settings.py",
    "**/config.py",
    "**/*token*.py",
    "**/*auth*.py",
    "**/llm.py",
    "**/*agent*.py",
)
_SERVICE_GLOBS: Final = (
    "**/app.sh",
    "**/main.py",
    "**/asgi.py",
    "**/chat_app.py",
    "**/*agent*.py",
    "**/chat.py",
)
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
    "domino-agent-llm-keys",
    "domino-agent-access-token",
    "domino-agent-endpoint-auth",
    "domino-agent-redact-traces",
    "domino-agent-app-factory",
    "domino-agent-chat-endpoint",
    "domino-agent-run-limits",
    "domino-agent-conversation-state",
    "domino-agent-logging",
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
    probe_inactive=frozenset(),
    section_ids=(
        "secrets",
        "service",
        "configuration",
        "tracing",
        "evaluation",
        "a2a",
        "testing",
    ),
    probe="domino",
    rules={
        "domino-agent-llm-keys": RulePin(
            applies_if=_DOMINO,
            globs=(*_SECRETS_GLOBS, "**/*config*.yaml", "**/*config*.yml"),
            priority=20,
            name="Domino agent LLM provider keys",
            tags=("python", "domino", "agents", "security"),
            section="secrets",
        ),
        "domino-agent-access-token": RulePin(
            applies_if=_DOMINO,
            globs=_SECRETS_GLOBS,
            priority=21,
            name="Domino agent access token",
            tags=("python", "domino", "agents", "security"),
            section="secrets",
        ),
        "domino-agent-endpoint-auth": RulePin(
            applies_if=_DOMINO,
            globs=_SECRETS_GLOBS,
            priority=22,
            name="Domino agent model endpoint auth",
            tags=("python", "domino", "agents", "security", "httpx"),
            section="secrets",
        ),
        "domino-agent-redact-traces": RulePin(
            applies_if=_DOMINO,
            globs=(*_SECRETS_GLOBS, "**/tracing.py", "**/chat_app.py", "**/main.py"),
            priority=23,
            name="Domino agent secrets out of traces",
            tags=("python", "domino", "agents", "security", "tracing"),
            section="secrets",
        ),
        "domino-agent-app-factory": RulePin(
            applies_if=_DOMINO_FASTAPI,
            globs=_SERVICE_GLOBS,
            priority=40,
            name="Domino agent app factory",
            tags=("python", "domino", "agents", "fastapi"),
            section="service",
        ),
        "domino-agent-chat-endpoint": RulePin(
            applies_if=_DOMINO_FASTAPI,
            globs=_SERVICE_GLOBS,
            priority=41,
            name="Domino agent chat endpoint",
            tags=("python", "domino", "agents", "fastapi"),
            section="service",
        ),
        "domino-agent-run-limits": RulePin(
            applies_if=_DOMINO,
            globs=(*_SERVICE_GLOBS, "**/evals/**/*.py"),
            priority=42,
            name="Domino agent run limits",
            tags=("python", "domino", "agents"),
            section="service",
        ),
        "domino-agent-conversation-state": RulePin(
            applies_if=_DOMINO,
            globs=_SERVICE_GLOBS,
            priority=43,
            name="Domino agent conversation state",
            tags=("python", "domino", "agents"),
            section="service",
        ),
        "domino-agent-logging": RulePin(
            applies_if=_DOMINO,
            globs=(*_SERVICE_GLOBS, "**/logs.py", "**/logging_config.py"),
            priority=44,
            name="Domino agent logging",
            tags=("python", "domino", "agents", "logging"),
            section="service",
        ),
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
