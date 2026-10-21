"""Tests for coding_agent_playbook.detector.predicate: the ``applies_if`` predicate (SPEC §6.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.detector.facts import Facts, detect
from coding_agent_playbook.detector.predicate import (
    LIST_PREDICATE_KEYS,
    evaluate_predicate,
    filter_applies_if,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("constraint", "version", "expected"),
    [
        (">=3.11", "3.12", True),
        (">=3.11", "3.10", False),
        (">3.11", "3.12", True),
        (">3.11", "3.11", False),
        ("==3.12", "3.12", True),
        ("==3.12", "3.13", False),
        ("<=3.12", "3.12", True),
        ("<=3.12", "3.13", False),
        ("<3.13", "3.12", True),
        ("<3.13", "3.13", False),
        ("~=3.12", "3.12.5", True),
        ("~=3.12", "4.0", False),
    ],
)
def test_evaluate_predicate_python_version(constraint: str, version: str, expected: bool) -> None:
    facts: Facts = {"python_version": version}
    assert evaluate_predicate({"python_version": constraint}, facts) is expected


def test_evaluate_predicate_python_version_absent_returns_false() -> None:
    # If facts lack python_version, the constraint can't be satisfied.
    assert evaluate_predicate({"python_version": ">=3.11"}, {}) is False


def test_evaluate_predicate_python_version_rejects_unknown_operator() -> None:
    facts: Facts = {"python_version": "3.12"}
    with pytest.raises(ValueError, match=r"must start with"):
        evaluate_predicate({"python_version": "@3.12"}, facts)


def test_evaluate_predicate_has_framework_all_present() -> None:
    facts: Facts = {"frameworks": {"fastapi": ">=0.110", "pydantic": ">=2.0"}}
    assert evaluate_predicate({"has_framework": ["fastapi", "pydantic"]}, facts) is True


def test_evaluate_predicate_has_framework_one_missing_false() -> None:
    facts: Facts = {"frameworks": {"fastapi": ">=0.110"}}
    assert evaluate_predicate({"has_framework": ["fastapi", "django"]}, facts) is False


def test_evaluate_predicate_has_framework_no_frameworks_in_facts_false() -> None:
    assert evaluate_predicate({"has_framework": ["fastapi"]}, {}) is False


def test_evaluate_predicate_has_framework_requires_list() -> None:
    facts: Facts = {"frameworks": {"fastapi": ""}}
    with pytest.raises(ValueError, match="list of strings"):
        evaluate_predicate({"has_framework": "fastapi"}, facts)


def test_evaluate_predicate_any_framework_one_present() -> None:
    facts: Facts = {"frameworks": {"pytest": ">=8.0"}}
    assert evaluate_predicate({"any_framework": ["pytest", "unittest"]}, facts) is True


def test_evaluate_predicate_any_framework_none_present_false() -> None:
    facts: Facts = {"frameworks": {"fastapi": ">=0.110"}}
    assert evaluate_predicate({"any_framework": ["pytest", "unittest"]}, facts) is False


def test_evaluate_predicate_any_framework_empty_list_false() -> None:
    # Vacuous "any of nothing" is False — there's no framework satisfying it.
    facts: Facts = {"frameworks": {"fastapi": ">=0.110"}}
    assert evaluate_predicate({"any_framework": []}, facts) is False


def test_evaluate_predicate_has_ml_stack_all_present() -> None:
    facts: Facts = {"ml_stack": {"torch": ">=2.0", "numpy": ">=1.26"}}
    assert evaluate_predicate({"has_ml_stack": ["torch", "numpy"]}, facts) is True


def test_evaluate_predicate_has_ml_stack_one_missing_false() -> None:
    facts: Facts = {"ml_stack": {"torch": ">=2.0"}}
    assert evaluate_predicate({"has_ml_stack": ["torch", "tensorflow"]}, facts) is False


def test_evaluate_predicate_has_ml_stack_no_ml_stack_in_facts_false() -> None:
    # ML-stack operators read facts["ml_stack"], never facts["frameworks"].
    assert evaluate_predicate({"has_ml_stack": ["torch"]}, {}) is False


def test_evaluate_predicate_has_ml_stack_does_not_read_frameworks() -> None:
    # A framework is not an ML-stack dep — gating must not cross the two facts.
    facts: Facts = {"frameworks": {"torch": ">=2.0"}}
    assert evaluate_predicate({"has_ml_stack": ["torch"]}, facts) is False


def test_evaluate_predicate_any_ml_stack_one_present() -> None:
    facts: Facts = {"ml_stack": {"scikit-learn": ">=1.4"}}
    assert evaluate_predicate({"any_ml_stack": ["torch", "scikit-learn"]}, facts) is True


def test_evaluate_predicate_any_ml_stack_none_present_false() -> None:
    facts: Facts = {"ml_stack": {"numpy": ">=1.26"}}
    assert evaluate_predicate({"any_ml_stack": ["torch", "tensorflow"]}, facts) is False


def test_evaluate_predicate_any_ml_stack_empty_list_false() -> None:
    facts: Facts = {"ml_stack": {"torch": ">=2.0"}}
    assert evaluate_predicate({"any_ml_stack": []}, facts) is False


@pytest.mark.parametrize(
    ("wanted", "expected"),
    [
        (["pytest-cov"], True),
        (["pytest-cov", "pytest"], True),
        (["Pytest_Cov"], True),  # compared PEP 503-normalized, like the fact's keys
        (["pytest-cov", "hypothesis"], False),
        (["fastapi"], False),  # a runtime dependency is not a dev dependency
    ],
)
def test_has_dev_dependency_all_required(wanted: list[str], expected: bool) -> None:
    """prK §F.1.2: every named package must be a declared dev dependency."""
    facts: Facts = {
        "dependencies": {"fastapi": ">=0.110"},
        "dev_dependencies": {"pytest": ">=8", "pytest-cov": ">=5"},
    }
    assert evaluate_predicate({"has_dev_dependency": wanted}, facts) is expected


def test_has_dev_dependency_absent_fact_is_false() -> None:
    assert evaluate_predicate({"has_dev_dependency": ["pytest-cov"]}, {}) is False


def test_has_dev_dependency_requires_a_list_of_strings() -> None:
    with pytest.raises(ValueError, match="'has_dev_dependency' must be a list of strings"):
        evaluate_predicate({"has_dev_dependency": "pytest-cov"}, {})


def test_has_dev_dependency_reads_the_detected_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n[project.optional-dependencies]\ndev = ["pytest_cov>=5"]\n',
        encoding="utf-8",
    )
    assert evaluate_predicate({"has_dev_dependency": ["pytest-cov"]}, detect(tmp_path)) is True


# --- has_dependency / any_dependency (D23): runtime OR dev, PEP 503-normalized ---

_RUNTIME_PANDERA: Facts = {"dependencies": {"pandera": ">=0.20"}}
_DEV_PANDERA: Facts = {"dev_dependencies": {"pandera": ">=0.20"}}
_SPLIT_DEPS: Facts = {
    "dependencies": {"pydantic-settings": ">=2", "anyio": ">=4"},
    "dev_dependencies": {"pytest": ">=8"},
}


@pytest.mark.parametrize("key", ["has_dependency", "any_dependency"])
@pytest.mark.parametrize("facts", [_RUNTIME_PANDERA, _DEV_PANDERA], ids=["runtime", "dev"])
def test_dependency_predicates_read_runtime_and_dev_dependencies(key: str, facts: Facts) -> None:
    assert evaluate_predicate({key: ["pandera"]}, facts) is True


@pytest.mark.parametrize("key", ["has_dependency", "any_dependency"])
def test_dependency_predicates_are_false_without_dependency_facts(key: str) -> None:
    assert evaluate_predicate({key: ["pandera"]}, {}) is False


@pytest.mark.parametrize("key", ["has_dependency", "any_dependency"])
def test_dependency_predicates_compare_pep_503_names(key: str) -> None:
    assert evaluate_predicate({key: ["Pydantic_Settings"]}, _SPLIT_DEPS) is True


@pytest.mark.parametrize(
    ("wanted", "expected"),
    [
        (["pydantic-settings", "pytest"], True),  # one runtime, one dev: both declared
        (["pydantic-settings", "pandera"], False),
        (["pandera"], False),
    ],
)
def test_has_dependency_requires_every_name(wanted: list[str], expected: bool) -> None:
    assert evaluate_predicate({"has_dependency": wanted}, _SPLIT_DEPS) is expected


@pytest.mark.parametrize(
    ("wanted", "expected"),
    [
        (["pandera", "anyio"], True),
        (["pandera", "pyjwt"], False),
        ([], False),
    ],
)
def test_any_dependency_requires_one_name(wanted: list[str], expected: bool) -> None:
    assert evaluate_predicate({"any_dependency": wanted}, _SPLIT_DEPS) is expected


@pytest.mark.parametrize("key", ["has_dependency", "any_dependency"])
def test_dependency_predicates_require_a_list_of_strings(key: str) -> None:
    with pytest.raises(ValueError, match=f"'{key}' must be a list of strings; got 'pandera'"):
        evaluate_predicate({key: "pandera"}, _RUNTIME_PANDERA)


def test_any_dependency_reads_the_detected_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["Pandera>=0.20"]\n', encoding="utf-8"
    )
    assert evaluate_predicate({"any_dependency": ["pandera"]}, detect(tmp_path)) is True


# --- any_file (D78(10)): at least one listed path exists ---


def test_any_file_true_when_one_listed_path_exists(tmp_path: Path) -> None:
    (tmp_path / "mkdocs.yml").write_text("site_name: x\n")
    predicate = {"any_file": ["docs/conf.py", "mkdocs.yml"]}
    assert evaluate_predicate(predicate, {}, repo_root=tmp_path) is True


def test_any_file_false_when_no_listed_path_exists(tmp_path: Path) -> None:
    predicate = {"any_file": ["docs/conf.py", "mkdocs.yml"]}
    assert evaluate_predicate(predicate, {}, repo_root=tmp_path) is False


def test_any_file_requires_a_list_of_strings(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="'any_file' must be a list of strings"):
        evaluate_predicate({"any_file": "mkdocs.yml"}, {}, repo_root=tmp_path)


def test_any_file_without_repo_root_raises() -> None:
    with pytest.raises(ValueError, match="'any_file' requires repo_root"):
        evaluate_predicate({"any_file": ["mkdocs.yml"]}, {})


def test_evaluate_predicate_ml_stack_requires_list() -> None:
    facts: Facts = {"ml_stack": {"torch": ""}}
    with pytest.raises(ValueError, match="list of strings"):
        evaluate_predicate({"any_ml_stack": "torch"}, facts)


def test_evaluate_predicate_has_file_true(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n")
    assert evaluate_predicate({"has_file": ["Dockerfile"]}, {}, repo_root=tmp_path) is True


def test_evaluate_predicate_has_file_missing_false(tmp_path: Path) -> None:
    assert evaluate_predicate({"has_file": ["Dockerfile"]}, {}, repo_root=tmp_path) is False


def test_evaluate_predicate_has_file_all_must_exist(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n")
    # Only one of two files exists → False.
    assert (
        evaluate_predicate({"has_file": ["Dockerfile", "Makefile"]}, {}, repo_root=tmp_path)
        is False
    )


def test_evaluate_predicate_has_file_supports_nested_paths(tmp_path: Path) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n")
    assert (
        evaluate_predicate({"has_file": [".github/workflows/ci.yml"]}, {}, repo_root=tmp_path)
        is True
    )


def test_evaluate_predicate_has_file_without_repo_root_raises() -> None:
    with pytest.raises(ValueError, match="repo_root"):
        evaluate_predicate({"has_file": ["Dockerfile"]}, {})


def test_evaluate_predicate_boolean_true_matches_true_fact() -> None:
    facts: Facts = {"has_dockerfile": True}
    assert evaluate_predicate({"has_dockerfile": True}, facts) is True


def test_evaluate_predicate_boolean_true_false_when_fact_false() -> None:
    facts: Facts = {"has_dockerfile": False}
    assert evaluate_predicate({"has_dockerfile": True}, facts) is False


def test_evaluate_predicate_boolean_true_false_when_fact_absent() -> None:
    assert evaluate_predicate({"has_dockerfile": True}, {}) is False


def test_evaluate_predicate_boolean_false_matches_false_fact() -> None:
    # Explicit False matches an explicit False fact, but NOT absence.
    facts: Facts = {"has_dockerfile": False}
    assert evaluate_predicate({"has_dockerfile": False}, facts) is True


def test_evaluate_predicate_boolean_false_does_not_match_absent_fact() -> None:
    # The plan calls out "explicit False vs absent both fail" for True; the
    # symmetric case here is: False predicate against absent fact is False —
    # absence is not equivalent to False.
    assert evaluate_predicate({"has_dockerfile": False}, {}) is False


def test_evaluate_predicate_multiple_keys_anded_all_true() -> None:
    facts: Facts = {
        "python_version": "3.12",
        "frameworks": {"fastapi": ">=0.110"},
    }
    assert (
        evaluate_predicate({"python_version": ">=3.11", "has_framework": ["fastapi"]}, facts)
        is True
    )


def test_evaluate_predicate_multiple_keys_anded_one_false() -> None:
    facts: Facts = {
        "python_version": "3.10",
        "frameworks": {"fastapi": ">=0.110"},
    }
    assert (
        evaluate_predicate({"python_version": ">=3.11", "has_framework": ["fastapi"]}, facts)
        is False
    )


def test_evaluate_predicate_empty_predicate_returns_true() -> None:
    # Vacuous truth — no constraints means the predicate is satisfied.
    assert evaluate_predicate({}, {}) is True


def test_evaluate_predicate_unknown_key_raises() -> None:
    with pytest.raises(ValueError, match="unknown predicate"):
        evaluate_predicate({"wat": 1}, {})


def test_evaluate_predicate_unknown_key_with_string_value_raises() -> None:
    # Strings are not boolean, not a structured operator — must raise.
    with pytest.raises(ValueError, match="unknown predicate"):
        evaluate_predicate({"frobnicate": "yes"}, {})


def test_evaluate_predicate_unknown_key_with_bool_value_raises() -> None:
    """A typo'd predicate key paired with a bool value must raise ValueError,
    not silently match the boolean branch (code-quality review I1).
    Previously the dispatch matched on value-type-only, letting typos through."""
    with pytest.raises(ValueError, match="unknown predicate key"):
        evaluate_predicate({"has_dokerfile": True}, {"has_dockerfile": True})
    with pytest.raises(ValueError, match="unknown predicate key"):
        evaluate_predicate({"banking_mode_typo": False}, {})


def test_evaluate_predicate_python_version_with_non_string_raises() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        evaluate_predicate({"python_version": 3}, {"python_version": "3.12"})


def test_evaluate_predicate_python_version_invalid_value_in_facts_raises() -> None:
    # If facts carry a syntactically-invalid version, packaging surfaces it.
    with pytest.raises(ValueError, match="invalid python_version"):
        evaluate_predicate({"python_version": ">=3.11"}, {"python_version": "not.a.version"})


def _rule(rule_id: str, applies_if: dict[str, object]) -> Rule:
    frontmatter = RuleFrontmatter(
        id=rule_id, name=rule_id, description="d", scope="always", applies_if=applies_if
    )
    return Rule(frontmatter, "body", "body", False, None, "coding_agent_playbook")


def test_filter_applies_if_keeps_empty_and_true_predicates_in_order(tmp_path: Path) -> None:
    rules = [
        _rule("no-predicate", {}),
        _rule("fastapi-only", {"has_framework": ["fastapi"]}),
        _rule("needs-dockerfile", {"has_file": ["Dockerfile"]}),
    ]
    facts: Facts = {"frameworks": {"fastapi": ">=0.110"}}

    kept = filter_applies_if(rules, facts, tmp_path)

    assert [rule.frontmatter.id for rule in kept] == ["no-predicate", "fastapi-only"]


def test_filter_applies_if_raises_on_an_unknown_predicate_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown predicate key: 'has_dokerfile'"):
        filter_applies_if([_rule("typo", {"has_dokerfile": True})], {}, tmp_path)


#: Every key ``evaluate_predicate`` accepts (SPEC §6.4). A new key goes here too.
_EVERY_PREDICATE_KEY = (
    "python_version",
    "has_framework",
    "any_framework",
    "has_ml_stack",
    "any_ml_stack",
    "has_dev_dependency",
    "has_dependency",
    "any_dependency",
    "has_file",
    "any_file",
    "package_manager",
    "has_notebooks",
    "has_dockerfile",
    "has_ci",
    "banking_mode",
)


def _rejects_as_non_list(key: str, tmp_path: Path) -> bool:
    """Whether ``key`` with a non-list value fails the list-of-strings check."""
    try:
        evaluate_predicate({key: 5}, {}, repo_root=tmp_path)
    except ValueError as exc:
        return "must be a list of strings" in str(exc)
    return False


def test_list_predicate_keys_are_exactly_the_keys_that_take_a_list(tmp_path: Path) -> None:
    """One home for the list-valued keys: ``playbook check`` imports this set."""
    takes_a_list = {key for key in _EVERY_PREDICATE_KEY if _rejects_as_non_list(key, tmp_path)}
    assert takes_a_list == LIST_PREDICATE_KEYS


def test_has_dev_dependency_normalizes_the_fact_keys_too() -> None:
    """Hand-written facts (an eval sample's) match like detected ones: both sides are PEP 503."""
    facts: Facts = {"dev_dependencies": {"Pytest_Cov": ">=5"}}
    assert evaluate_predicate({"has_dev_dependency": ["pytest-cov"]}, facts)
