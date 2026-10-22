"""Pins of core skill ``domino-agents`` (prU D52, D63, C-domino-agents-01).

Every member gates on ``domino_project``, so the reference probe activates none
and the skill is checked on the Domino probe instead (``domino_only``).
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
)

PINS: Final = CoreSkillPins(
    skill_id="domino-agents",
    where="Agent service code, launch script, agent config, evaluation Jobs and their tests",
    members=_MEMBERS,
    probe_inactive=frozenset(_MEMBERS),
    section_ids=(
        "secrets",
        "service",
        "configuration",
        "tracing",
        "evaluation",
        "a2a",
        "testing",
    ),
    domino_only=True,
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
    },
)
