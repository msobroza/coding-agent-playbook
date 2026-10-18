"""Tests for the ``package_manager`` applies_if key (SPEC §6.4, §8.2).

A sibling of ``test_detector.py``: the key reads the detector's existing
``package_manager`` fact, and these tests pin its predicate semantics (a name, or a
non-empty list meaning any of them; an absent fact never matches; a malformed value
raises even when the fact is absent) and that every value the detector can report is
one the predicate accepts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.detector import (
    KNOWN_PACKAGE_MANAGERS,
    _package_manager_matches,
    _package_manager_names,
    detect,
    evaluate_predicate,
)

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.detector import Facts

_ALLOWED = "['pip', 'pip-tools', 'poetry', 'uv']"


def test_evaluate_predicate_package_manager_string_matches() -> None:
    assert evaluate_predicate({"package_manager": "uv"}, {"package_manager": "uv"}) is True


def test_evaluate_predicate_package_manager_string_mismatch() -> None:
    assert evaluate_predicate({"package_manager": "uv"}, {"package_manager": "poetry"}) is False


def test_evaluate_predicate_package_manager_list_is_any_of() -> None:
    predicate = {"package_manager": ["uv", "poetry"]}

    assert evaluate_predicate(predicate, {"package_manager": "poetry"}) is True
    assert evaluate_predicate(predicate, {"package_manager": "pip"}) is False


def test_evaluate_predicate_package_manager_absent_fact_is_false() -> None:
    assert evaluate_predicate({"package_manager": "uv"}, {}) is False


def test_evaluate_predicate_package_manager_ands_with_other_keys() -> None:
    facts: Facts = {"package_manager": "uv", "python_version": "3.12"}

    assert evaluate_predicate({"package_manager": "uv", "python_version": ">=3.12"}, facts)
    assert not evaluate_predicate({"package_manager": "uv", "python_version": ">=3.13"}, facts)


@pytest.mark.parametrize(
    "value",
    ["pipenv", ["uv", "UV"], [], 3, ["uv", 3], None],
    ids=["unknown-name", "wrong-case", "empty-list", "int", "mixed-list", "none"],
)
def test_evaluate_predicate_package_manager_rejects_malformed_values(value: object) -> None:
    with pytest.raises(ValueError, match=r"predicate 'package_manager'.*\['pip', 'pip-tools'"):
        evaluate_predicate({"package_manager": value}, {"package_manager": "uv"})


def test_unknown_package_manager_message_names_the_value_and_the_allowed_names() -> None:
    with pytest.raises(ValueError) as excinfo:
        _package_manager_names(["uv", "pipenv"])

    assert str(excinfo.value) == (
        "predicate 'package_manager' names unknown package manager(s) ['pipenv']; "
        f"expected any of {_ALLOWED}"
    )


def test_malformed_package_manager_message_names_the_value_and_the_expected_shape() -> None:
    with pytest.raises(ValueError) as excinfo:
        _package_manager_names([])

    assert str(excinfo.value) == (
        f"predicate 'package_manager' must be one of {_ALLOWED} or a non-empty list of them; got []"
    )


def test_package_manager_names_accepts_a_name_or_a_list() -> None:
    assert _package_manager_names("uv") == frozenset({"uv"})
    assert _package_manager_names(["uv", "poetry"]) == frozenset({"uv", "poetry"})


def test_package_manager_matches_validates_before_reading_the_fact() -> None:
    # A typo must fail in every repo, including one with no package manager detected.
    with pytest.raises(ValueError, match="'pipenv'"):
        _package_manager_matches("pipenv", {})
    assert _package_manager_matches("pip", {"package_manager": "pip"}) is True


def _write_files(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (repo / rel).write_text(text, encoding="utf-8")


_BARE_PYPROJECT = '[project]\nname = "x"\n'


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"uv.lock": "# lock\n"}, "uv"),
        ({"poetry.lock": "# lock\n"}, "poetry"),
        ({"pyproject.toml": _BARE_PYPROJECT + '[tool.poetry]\nname = "x"\n'}, "poetry"),
        ({"requirements.in": "requests\n"}, "pip-tools"),
        ({"requirements.txt": "requests\n"}, "pip"),
        ({"pyproject.toml": _BARE_PYPROJECT}, "pip"),
    ],
    ids=["uv-lock", "poetry-lock", "tool-poetry", "requirements-in", "requirements-txt", "bare"],
)
def test_known_package_managers_cover_every_detected_value(
    tmp_path: Path, files: dict[str, str], expected: str
) -> None:
    # Regression guard: a fifth installer added to the Literal must reach the predicate too.
    _write_files(tmp_path, files)

    detected = detect(tmp_path).get("package_manager")

    assert detected == expected
    assert detected in KNOWN_PACKAGE_MANAGERS
    assert evaluate_predicate({"package_manager": detected}, detect(tmp_path)) is True
