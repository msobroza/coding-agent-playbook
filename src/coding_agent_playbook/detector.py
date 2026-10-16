"""Detector subsystem: inspect a consumer repo and produce a Facts dict.

See SPEC.md §8. The Facts dict feeds the renderer's context (SPEC §9.4) and the
``applies_if`` predicate evaluator (SPEC §6.4). Detector runs at ``playbook init``,
is cached in ``.coding-agent-playbook.toml``, and refreshes on ``pyproject.toml``
mtime change or ``playbook check --refresh``.

The detector never opens a secret path (SPEC §17.3): its only file read is
``pyproject.toml``, and its filesystem walks skip every
``security.paths.is_secret_path`` match.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from coding_agent_playbook._pep503 import canonical_name
from coding_agent_playbook._pyproject_deps import dependency_specs
from coding_agent_playbook.security.files import user_home
from coding_agent_playbook.security.paths import is_secret_path
from coding_agent_playbook.security.patterns import WALK_SKIP_DIRS

if TYPE_CHECKING:
    from pathlib import Path

#: One source with the secret guards' repository walk (``security.patterns``).
_IGNORE_DIRS: frozenset[str] = WALK_SKIP_DIRS


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


def _parse_python_version(requires_python: str | None) -> str | None:
    """Extract a ``"major.minor"`` python_version from ``requires-python``.

    Accepts the common shapes ``">=3.12"``, ``">=3.12,<4"``, ``"~=3.12"``,
    ``"==3.12.*"``. Returns the minimum bound's major.minor, or ``None`` if
    no minimum can be inferred.
    """
    if not requires_python:
        return None
    # Walk comma-separated constraints, find a min-bound.
    for raw in requires_python.split(","):
        spec = raw.strip()
        # Only lower-bound operators (>=, ~=, ==, >) yield a meaningful
        # python_version; upper-bound operators (<, <=) don't pin a minimum
        # and are silently skipped.
        for op in (">=", "~=", "==", ">"):
            if spec.startswith(op):
                version = spec[len(op) :].strip().rstrip(".*")
                parts = version.split(".")
                if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                    return f"{parts[0]}.{parts[1]}"
    return None


def _detect_package_manager(
    repo_root: Path, pyproject: dict[str, Any] | None
) -> Literal["uv", "poetry", "pip-tools", "pip"] | None:
    """Lockfile / pyproject cascade per SPEC §8.

    ``uv.lock`` → ``uv``; ``poetry.lock`` → ``poetry``; ``[tool.poetry]`` in
    pyproject → ``poetry``; ``requirements.in`` → ``pip-tools``;
    ``requirements.txt`` → ``pip``; otherwise ``pip`` (only if a pyproject
    exists — a totally empty directory leaves ``package_manager`` unset).
    """
    if (repo_root / "uv.lock").is_file():
        return "uv"
    if (repo_root / "poetry.lock").is_file():
        return "poetry"
    if pyproject is not None and "poetry" in pyproject.get("tool", {}):
        return "poetry"
    if (repo_root / "requirements.in").is_file():
        return "pip-tools"
    if (repo_root / "requirements.txt").is_file():
        return "pip"
    if pyproject is not None:
        return "pip"
    return None


def _read_pyproject(repo_root: Path) -> dict[str, Any] | None:
    """Read and parse ``pyproject.toml`` if present.

    Returns ``None`` when the file is missing OR malformed — a corrupted
    pyproject is treated identically to a missing one so that ``detect()``
    can honour its "never raises" docstring guarantee (SPEC §8).
    """
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        with pyproject.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError:
        # Malformed TOML — fall back to python-unknown as if no pyproject existed.
        return None


def _dev_tools_from_config_sections(pyproject: dict[str, Any]) -> set[str]:
    """Tools whose ``[tool.<x>]`` table appears in pyproject."""
    tool = pyproject.get("tool", {}) or {}
    found: set[str] = set()
    for name in KNOWN_DEV_TOOLS:
        if name in tool:
            found.add(name)
    return found


def _walk_skips(path: Path, repo_root: Path, *, home: str) -> bool:
    """Whether a detector walk must skip ``path`` (found under ``repo_root``).

    Skips anything inside an ``_IGNORE_DIRS`` directory and every secret path
    (SPEC §17.3; the one catalog lives in ``security/patterns.py``), so the
    detector never opens, or counts, a credential file. ``home`` anchors the
    catalog's ``~/`` globs.
    """
    if any(part in _IGNORE_DIRS for part in path.relative_to(repo_root).parts):
        return True
    return is_secret_path(path, home=home)


def _has_notebooks(repo_root: Path) -> bool:
    home = user_home()
    return any(not _walk_skips(path, repo_root, home=home) for path in repo_root.rglob("*.ipynb"))


def _has_dockerfile(repo_root: Path) -> bool:
    return (repo_root / "Dockerfile").exists() or (repo_root / "docker").is_dir()


def _has_ci(repo_root: Path) -> bool:
    return (
        (repo_root / ".github" / "workflows").is_dir()
        or (repo_root / "Jenkinsfile").is_file()
        or (repo_root / ".gitlab-ci.yml").is_file()
        or (repo_root / ".circleci").is_dir()
    )


def _infer_kind(
    facts: Facts, repo_root: Path
) -> Literal[
    "python-application",
    "python-library",
    "ml-research",
    "notebook",
    "python-unknown",
]:
    has_src = (repo_root / "src").is_dir()
    notebooks = facts.get("has_notebooks", False)
    frameworks = set(facts.get("frameworks", {}).keys())

    if notebooks and not has_src:
        return "notebook"
    if notebooks and has_src:
        return "ml-research"
    if has_src and "fastapi" in frameworks:
        return "python-application"
    if has_src:
        return "python-library"
    return "python-unknown"


def detect(repo_root: Path) -> Facts:
    """Run all detector passes against ``repo_root`` and return Facts.

    Reads ``pyproject.toml`` if present, walks for lockfiles and config files,
    and only sets dict keys it can determine. Never raises — a repo with no
    ``pyproject.toml`` returns ``Facts(project_kind="python-unknown")``.
    """
    facts: Facts = {}
    pyproject = _read_pyproject(repo_root)

    package_manager = _detect_package_manager(repo_root, pyproject)
    if package_manager is not None:
        facts["package_manager"] = package_manager

    if pyproject is not None:
        project = pyproject.get("project", {})

        python_version = _parse_python_version(project.get("requires-python"))
        if python_version is not None:
            facts["python_version"] = python_version

        # One parser with the resync hook's cheap comparison (_pyproject_deps).
        dependencies, dev_dependencies = dependency_specs(pyproject)
        if dependencies:
            facts["dependencies"] = dependencies

        if dev_dependencies:
            facts["dev_dependencies"] = dev_dependencies

        # Frameworks include testing frameworks declared as dev deps.
        framework_pool: dict[str, str] = {**dependencies, **dev_dependencies}
        frameworks = {n: v for n, v in framework_pool.items() if n in KNOWN_FRAMEWORKS}
        if frameworks:
            facts["frameworks"] = frameworks

        # ml_stack is runtime deps only.
        ml_stack = {n: v for n, v in dependencies.items() if n in KNOWN_ML_STACK}
        if ml_stack:
            facts["ml_stack"] = ml_stack

        dev_tools = {n for n in dev_dependencies if n in KNOWN_DEV_TOOLS}
        dev_tools |= _dev_tools_from_config_sections(pyproject)
        if dev_tools:
            facts["dev_tools"] = dev_tools

    has_notebooks = _has_notebooks(repo_root)
    if has_notebooks:
        facts["has_notebooks"] = True

    facts["has_dockerfile"] = _has_dockerfile(repo_root)
    facts["has_ci"] = _has_ci(repo_root)

    facts["project_kind"] = _infer_kind(facts, repo_root)

    return facts


_SUPPORTED_OPERATORS = (">=", "<=", "==", "~=", ">", "<")


# Boolean facts that may appear in an ``applies_if`` predicate. Gating the
# boolean dispatch branch on this set means a typo'd key (e.g. ``has_dokerfile``)
# raises ``ValueError`` instead of silently matching by value-type alone.
_KNOWN_BOOL_FACT_KEYS: frozenset[str] = frozenset(
    {"has_notebooks", "has_dockerfile", "has_ci", "banking_mode"}
)


def _coerce_string_list(value: Any, key: str) -> list[str]:
    """Validate a predicate value is a list of strings; raise with a clear message otherwise."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"predicate {key!r} must be a list of strings; got {value!r}")
    return value


def _check_python_version(constraint: str, facts: Facts) -> bool:
    """Compare ``facts["python_version"]`` against a PEP 440-style constraint."""
    spec = constraint.strip()
    if not any(spec.startswith(op) for op in _SUPPORTED_OPERATORS):
        raise ValueError(
            f"python_version constraint must start with one of {_SUPPORTED_OPERATORS}; "
            f"got {constraint!r}"
        )
    actual = facts.get("python_version")
    if actual is None:
        return False
    try:
        return Version(actual) in SpecifierSet(spec)
    except (InvalidVersion, InvalidSpecifier) as exc:
        raise ValueError(f"invalid python_version constraint or value: {exc}") from exc


def _has_dev_dependencies(wanted: list[str], facts: Facts) -> bool:
    """Whether every name in ``wanted`` is a declared dev dependency (prK §F.1.2).

    The fact's keys are PEP 503-normalized, so ``pytest_cov`` matches ``pytest-cov``.
    """
    present = set(facts.get("dev_dependencies", {}))
    return all(canonical_name(name) in present for name in wanted)


def evaluate_predicate(
    predicate: dict[str, Any], facts: Facts, *, repo_root: Path | None = None
) -> bool:
    """Evaluate an ``applies_if`` predicate against facts (SPEC §6.4).

    Supported keys:
      - ``python_version: ">=3.11"`` — semver-style comparison
      - ``has_framework: ["fastapi"]`` — ALL must be present in facts["frameworks"]
      - ``any_framework: ["pytest", "unittest"]`` — at least one present
      - ``has_ml_stack: ["torch", "numpy"]`` — ALL must be present in facts["ml_stack"]
      - ``any_ml_stack: ["torch", "tensorflow"]`` — at least one present in facts["ml_stack"]
      - ``has_dev_dependency: ["pytest-cov"]`` — ALL declared as dev dependencies
        (facts["dev_dependencies"]; names compared PEP 503-normalized)
      - ``has_file: ["Dockerfile"]`` — file exists in repo root (relative paths)
      - ``banking_mode: true`` — boolean facts compared by equality

    Multiple keys are AND-ed together. Unknown keys raise ``ValueError`` so
    typos fail loudly at validate time.

    ``repo_root`` is required when the predicate uses ``has_file`` (paths are
    resolved relative to it). Other operators read only from ``facts``.
    """
    for key, value in predicate.items():
        if key == "python_version":
            if not isinstance(value, str):
                raise ValueError(
                    f"python_version constraint must be a string; got {type(value).__name__}"
                )
            if not _check_python_version(value, facts):
                return False
        elif key == "has_framework":
            wanted = _coerce_string_list(value, key)
            present = set(facts.get("frameworks", {}).keys())
            if not all(name in present for name in wanted):
                return False
        elif key == "any_framework":
            wanted = _coerce_string_list(value, key)
            present = set(facts.get("frameworks", {}).keys())
            if not any(name in present for name in wanted):
                return False
        elif key == "has_ml_stack":
            wanted = _coerce_string_list(value, key)
            present = set(facts.get("ml_stack", {}).keys())
            if not all(name in present for name in wanted):
                return False
        elif key == "any_ml_stack":
            wanted = _coerce_string_list(value, key)
            present = set(facts.get("ml_stack", {}).keys())
            if not any(name in present for name in wanted):
                return False
        elif key == "has_dev_dependency":
            if not _has_dev_dependencies(_coerce_string_list(value, key), facts):
                return False
        elif key == "has_file":
            paths = _coerce_string_list(value, key)
            if repo_root is None:
                raise ValueError("predicate 'has_file' requires repo_root keyword argument")
            if not all((repo_root / rel).exists() for rel in paths):
                return False
        elif key in _KNOWN_BOOL_FACT_KEYS and isinstance(value, bool):
            # Boolean facts compared by equality. The fact must be explicitly
            # present AND equal — an absent fact never satisfies a boolean
            # predicate (neither True nor False). The ``key in _KNOWN_BOOL_FACT_KEYS``
            # guard ensures a typo'd predicate key paired with a bool value
            # raises ``ValueError`` rather than silently matching by value type.
            if key not in facts or facts[key] != value:  # type: ignore[literal-required]
                return False
        else:
            raise ValueError(f"unknown predicate key: {key!r}")
    return True
