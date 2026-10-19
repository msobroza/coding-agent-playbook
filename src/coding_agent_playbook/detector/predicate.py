"""The ``applies_if`` predicate evaluator (SPEC §6.4) and the shared artifact filter.

``evaluate_predicate`` checks one predicate against the detector's Facts;
``filter_applies_if`` applies it to a list of rules or prompts the same way in
every render (``sync``, ``render``, the eval runner).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from coding_agent_playbook.detector.facts import KNOWN_PACKAGE_MANAGERS
from coding_agent_playbook.detector.pep503 import canonical_name

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.detector.facts import Facts


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


def _package_manager_names(value: object) -> frozenset[str]:
    """The managers an ``applies_if.package_manager`` value allows; ``ValueError`` when malformed.

    >>> sorted(_package_manager_names(["uv", "poetry"]))
    ['poetry', 'uv']
    """
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise ValueError(
            f"predicate 'package_manager' must be one of {sorted(KNOWN_PACKAGE_MANAGERS)} "
            f"or a non-empty list of them; got {value!r}"
        )
    unknown = sorted(set(names) - KNOWN_PACKAGE_MANAGERS)
    if unknown:
        raise ValueError(
            f"predicate 'package_manager' names unknown package manager(s) {unknown}; "
            f"expected any of {sorted(KNOWN_PACKAGE_MANAGERS)}"
        )
    return frozenset(names)


def _package_manager_matches(value: object, facts: Facts) -> bool:
    """Whether ``facts["package_manager"]`` is one ``value`` allows; an absent fact never matches.

    >>> _package_manager_matches("uv", {"package_manager": "uv"})
    True
    """
    allowed = _package_manager_names(value)  # validates even when the fact is absent
    return facts.get("package_manager") in allowed


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
      - ``package_manager: "uv"`` or ``["uv", "poetry"]`` — facts["package_manager"]
        is that name, or any of the listed names; an absent fact never matches, and
        an unknown name raises even then
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
        elif key == "package_manager":
            if not _package_manager_matches(value, facts):
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


def filter_applies_if[T: "Rule | Prompt"](
    artifacts: list[T],
    facts: Facts,
    repo_root: Path,
) -> list[T]:
    """Drop the artifacts whose ``applies_if`` is false for ``facts`` (SPEC §6.4).

    An empty predicate always passes. ``repo_root`` anchors ``has_file`` paths.

    Example::

        rules = filter_applies_if(ctx.rules_resolved, ctx.facts, ctx.repo_root)
    """
    kept: list[T] = []
    for artifact in artifacts:
        predicate = artifact.frontmatter.applies_if or {}
        if not predicate or evaluate_predicate(predicate, facts, repo_root=repo_root):
            kept.append(artifact)
    return kept
