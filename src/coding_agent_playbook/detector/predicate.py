"""The ``applies_if`` predicate evaluator (SPEC §6.4) and the shared artifact filter.

``evaluate_predicate`` checks one predicate against the detector's Facts;
``filter_applies_if`` applies it to a list of rules or prompts the same way in
every render (``sync``, ``render``, the eval runner).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from coding_agent_playbook.detector.facts import KNOWN_PACKAGE_MANAGERS
from coding_agent_playbook.detector.pep503 import canonical_name

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
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

#: How each list-valued ``applies_if`` key combines its names: ``all`` or ``any``.
#: An explicit map rather than a key-name test, so a lookup that misses raises
#: ``KeyError`` instead of silently falling into any-semantics.
_LIST_COMBINERS: dict[str, Callable[[Iterable[object]], bool]] = {
    "has_framework": all,
    "any_framework": any,
    "has_ml_stack": all,
    "any_ml_stack": any,
    "has_dev_dependency": all,
    "has_dependency": all,
    "any_dependency": any,
    "has_file": all,
    "any_file": any,
}

#: Every ``applies_if`` key whose value is a list of strings. The one home of
#: that fact: ``playbook check`` quotes these keys as written in its skip reason.
LIST_PREDICATE_KEYS: frozenset[str] = frozenset(_LIST_COMBINERS)


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


def _fact_keys(facts: Facts, field: str) -> Mapping[str, object]:
    """The mapping fact ``field`` (``frameworks``, ``ml_stack``, a dependency table); empty if absent.

    A non-mapping value (a hand-written eval mock fact such as ``"torch"``) raises:
    a membership test on a string would match substrings and silently pass.

    >>> _fact_keys({"ml_stack": "torch"}, "ml_stack")
    Traceback (most recent call last):
    ValueError: fact 'ml_stack' must be a mapping of name to version; got 'torch'
    """
    value = cast("Mapping[str, object]", facts).get(field, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"fact {field!r} must be a mapping of name to version; got {value!r}")
    return value


def _canonical_keys(facts: Facts, *fields: str) -> frozenset[str]:
    """The PEP 503 names of the keys of the dependency facts ``fields`` (D23).

    The one place dependency fact keys are normalized: the detector already
    normalizes them, but an eval sample's mock facts are written by hand.

    >>> sorted(_canonical_keys({"dependencies": {"anyio": ""},
    ...                         "dev_dependencies": {"Pytest_Cov": ""}},
    ...                        "dependencies", "dev_dependencies"))
    ['anyio', 'pytest-cov']
    """
    return frozenset(canonical_name(name) for field in fields for name in _fact_keys(facts, field))


def _dependencies_match(value: object, key: str, facts: Facts, *fields: str) -> bool:
    """Whether the dependency predicate ``key`` holds over the dependency facts ``fields``.

    ``has_dev_dependency`` reads ``dev_dependencies`` (prK §F.1.2); ``has_dependency``
    and ``any_dependency`` read runtime and dev dependencies alike (D23).

    >>> _dependencies_match(["pandera"], "any_dependency", {"dependencies": {"pandera": ""}},
    ...                     "dependencies")
    True
    """
    wanted = [canonical_name(name) for name in _coerce_string_list(value, key)]
    present = _canonical_keys(facts, *fields)
    return _LIST_COMBINERS[key](name in present for name in wanted)


def _names_present(value: object, key: str, facts: Facts, field: str) -> bool:
    """Whether the names predicate ``key`` holds over the keys of ``facts[field]`` (exact names).

    >>> _names_present(["torch"], "has_ml_stack", {"ml_stack": {"torch": "2"}}, "ml_stack")
    True
    """
    wanted = _coerce_string_list(value, key)
    present = _fact_keys(facts, field)
    return _LIST_COMBINERS[key](name in present for name in wanted)


def _files_exist(value: object, key: str, repo_root: Path | None) -> bool:
    """Whether ``has_file`` (all) or ``any_file`` (any) holds under ``repo_root``.

    >>> _files_exist(["mkdocs.yml"], "any_file", None)
    Traceback (most recent call last):
    ValueError: predicate 'any_file' requires repo_root keyword argument
    """
    paths = _coerce_string_list(value, key)
    if repo_root is None:
        raise ValueError(f"predicate {key!r} requires repo_root keyword argument")
    return _LIST_COMBINERS[key]((repo_root / rel).exists() for rel in paths)


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
      - ``has_dependency: ["pandera"]`` — ALL declared as runtime or dev dependencies
        (facts["dependencies"] and facts["dev_dependencies"]; PEP 503-normalized)
      - ``any_dependency: ["pandera", "pyjwt"]`` — at least one declared as a runtime
        or dev dependency (same names and normalization as ``has_dependency``)
      - ``has_file: ["Dockerfile"]`` — file exists in repo root (relative paths)
      - ``any_file: ["mkdocs.yml", "docs/conf.py"]`` — at least one listed path exists
      - ``package_manager: "uv"`` or ``["uv", "poetry"]`` — facts["package_manager"]
        is that name, or any of the listed names; an absent fact never matches, and
        an unknown name raises even then
      - ``banking_mode: true`` — boolean facts compared by equality

    Multiple keys are AND-ed together. Unknown keys raise ``ValueError`` so
    typos fail loudly at validate time.

    ``repo_root`` is required when the predicate uses ``has_file`` or ``any_file`` (paths are
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
        elif key in ("has_framework", "any_framework"):
            if not _names_present(value, key, facts, "frameworks"):
                return False
        elif key in ("has_ml_stack", "any_ml_stack"):
            if not _names_present(value, key, facts, "ml_stack"):
                return False
        elif key == "has_dev_dependency":
            if not _dependencies_match(value, key, facts, "dev_dependencies"):
                return False
        elif key in ("has_dependency", "any_dependency"):
            if not _dependencies_match(value, key, facts, "dependencies", "dev_dependencies"):
                return False
        elif key in ("has_file", "any_file"):
            if not _files_exist(value, key, repo_root):
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
