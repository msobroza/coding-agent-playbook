"""Pins of core skill ``domino-agents`` (prU D50, D52, D63, C-domino-agents-01 to -03).

Every member gates on ``domino_project``, so the reference probe activates none
and the skill is checked on the Domino probe instead (``probe="domino"``), which
activates every member but the A2A rules, which also need an A2A
dependency the probe does not declare.
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
#: The shared test-file glob set of test-related rules (prU D41).
_TEST_GLOBS: Final = (
    "**/test_*.py",
    "**/*_test.py",
    "**/tests/**/*.py",
    "**/conftest.py",
    "**/fakes.py",
)
#: The A2A rules' globs.
_A2A_GLOBS: Final = ("**/a2a.py", "**/*agent*.py", "**/main.py", "**/chat_app.py")
#: The packages that bring an A2A server or client in (pydantic-ai's a2a extra pulls fasta2a).
#: A tuple, so the pins cannot share a mutable list; each gate takes its own list copy.
_A2A_DEPENDENCIES: Final = ("fasta2a", "a2a-sdk", "pydantic-ai", "pydantic-ai-slim")
_A2A_MEMBERS: Final = ("a2a-mount-lifespan", "a2a-agent-card", "a2a-client-deadlines")
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
    "a2a-mount-lifespan",
    "a2a-agent-card",
    "a2a-client-deadlines",
    "domino-agent-fake-llm-tests",
    "domino-agent-fake-domino-tests",
)

PINS: Final = CoreSkillPins(
    skill_id="domino-agents",
    where="Agent service code, launch script, agent config, evaluation Jobs and their tests",
    members=_MEMBERS,
    probe_inactive=frozenset(_A2A_MEMBERS),
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
        "a2a-mount-lifespan": RulePin(
            applies_if={
                "domino_project": True,
                "has_framework": ["fastapi"],
                "any_dependency": list(_A2A_DEPENDENCIES),
            },
            globs=_A2A_GLOBS,
            priority=60,
            name="A2A mount and lifespan",
            tags=("python", "domino", "a2a", "fastapi"),
            section="a2a",
        ),
        "a2a-agent-card": RulePin(
            applies_if={"domino_project": True, "any_dependency": list(_A2A_DEPENDENCIES)},
            globs=_A2A_GLOBS,
            priority=61,
            name="A2A agent card",
            tags=("python", "domino", "a2a"),
            section="a2a",
        ),
        "a2a-client-deadlines": RulePin(
            applies_if={"domino_project": True, "any_dependency": list(_A2A_DEPENDENCIES)},
            globs=_A2A_GLOBS,
            priority=62,
            name="A2A client deadlines",
            tags=("python", "domino", "a2a", "httpx"),
            section="a2a",
        ),
        "domino-agent-fake-llm-tests": RulePin(
            applies_if={"domino_project": True, "has_framework": ["pytest"]},
            globs=_TEST_GLOBS,
            priority=63,
            name="Agent tests on a fake model",
            tags=("python", "domino", "pytest"),
            section="testing",
        ),
        "domino-agent-fake-domino-tests": RulePin(
            applies_if={"domino_project": True, "has_framework": ["pytest"]},
            globs=_TEST_GLOBS,
            priority=64,
            name="Agent tests on Domino fakes",
            tags=("python", "domino", "pytest"),
            section="testing",
        ),
    },
)
