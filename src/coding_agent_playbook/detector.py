"""Detector subsystem: inspect a consumer repo and produce a Facts dict.

See SPEC.md §8. The Facts dict feeds the renderer's context (SPEC §9.4) and the
``applies_if`` predicate evaluator (SPEC §6.4). Detector runs at ``cap init``,
is cached in ``.coding-agent-playbook.toml``, and refreshes on ``pyproject.toml``
mtime change or ``cap check --refresh``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict


# All entries are optional — the detector only sets keys it can determine.
class Facts(TypedDict, total=False):
    python_version: str
    package_manager: Literal["uv", "poetry", "pip-tools", "pip"]
    project_kind: Literal[
        "python-application",
        "python-library",
        "ml-research",
        "notebook",
        "python-unknown",
    ]
    dependencies: dict[str, str]
    dev_dependencies: dict[str, str]
    frameworks: dict[str, str]
    ml_stack: dict[str, str]
    has_notebooks: bool
    has_dockerfile: bool
    has_ci: bool
    dev_tools: set[str]


# Frameworks the detector recognises (subset of dependencies treated as frameworks).
KNOWN_FRAMEWORKS: frozenset[str] = frozenset(
    {
        "fastapi",
        "flask",
        "django",
        "starlette",
        "pydantic",
        "sqlalchemy",
        "alembic",
        "pytest",
        "pytest-asyncio",
        "pytest-mock",
        "unittest",
        "httpx",
        "requests",
        "aiohttp",
        "click",
        "typer",
    }
)

KNOWN_ML_STACK: frozenset[str] = frozenset(
    {
        "torch",
        "tensorflow",
        "jax",
        "transformers",
        "scikit-learn",
        "xgboost",
        "lightgbm",
        "numpy",
        "pandas",
        "matplotlib",
        "seaborn",
        "polars",
        "duckdb",
    }
)

KNOWN_DEV_TOOLS: frozenset[str] = frozenset(
    {
        "ruff",
        "black",
        "flake8",
        "isort",
        "mypy",
        "pyright",
        "pylint",
    }
)


def detect(repo_root: Path) -> Facts:
    """Run all detector passes against ``repo_root`` and return Facts.

    Reads ``pyproject.toml`` if present, walks for lockfiles and config files,
    and only sets dict keys it can determine. Never raises — a repo with no
    ``pyproject.toml`` returns ``Facts(project_kind="python-unknown")``.
    """
    raise NotImplementedError("detector.detect not yet implemented")


def evaluate_predicate(predicate: dict[str, Any], facts: Facts) -> bool:
    """Evaluate an ``applies_if`` predicate against facts (SPEC §6.4).

    Supported keys:
      - ``python_version: ">=3.11"`` — semver-style comparison
      - ``has_framework: ["fastapi"]`` — ALL must be present in facts["frameworks"]
      - ``any_framework: ["pytest", "unittest"]`` — at least one present
      - ``has_file: ["Dockerfile"]`` — file exists in repo root (relative paths)
      - ``banking_mode: true`` — boolean facts compared by equality

    Multiple keys are AND-ed together. Unknown keys raise ``ValueError`` so
    typos fail loudly at validate time.
    """
    raise NotImplementedError("detector.evaluate_predicate not yet implemented")
