"""Every string a skill with member rules adds (specs/prS-skills-context.md 6.4.4, 6.8.3).

Expected texts are the spec's worked examples, copied verbatim, so a test can
disagree with the code instead of recomputing it.
"""

from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.skill_document import (
    DESCRIPTION_MAX_CHARS,
    DescriptionOverflowError,
    compose_description,
    covers_clause,
    worst_case_description,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

#: The nine python-coding member names, in (priority, id) order (spec section 6.5.1).
PYTHON_CODING_NAMES = (
    "Dependency injection",
    "Pure core",
    "Data shapes",
    "Typing",
    "Error handling",
    "Context managers",
    "Docstrings",
    "Timeouts and retries",
    "Idioms",
)

#: An overlay that lengthens both authored parts of python-coding (spec section 6.4.4).
LONG_DESCRIPTION = (
    "Library-agnostic Python conventions for code in this repo, whatever library it uses."
)
LONG_USE_WHEN = (
    "writing, changing, refactoring or reviewing any Python module, script or notebook in this repo"
)

#: Twelve member names whose longest is not first (spec section 6.8.3, E7 regression).
TWELVE_NAMES = (
    "Typing",
    "Docstrings",
    "Idioms",
    "Pure core",
    "Data shapes",
    "Error handling",
    "Context managers",
    "Timeouts and retries for every network call",
    "Dependency injection",
    "Records",
    "Paths",
    "Imports",
)


def test_compose_description_joins_capability_covers_and_use_when() -> None:
    text = compose_description(
        "Library-agnostic Python conventions.",
        PYTHON_CODING_NAMES,
        "writing, changing or reviewing Python code",
    )
    assert text == (
        "Library-agnostic Python conventions. Covers Dependency injection, Pure core, "
        "Data shapes, Typing, Error handling, Context managers, Docstrings, Timeouts and "
        "retries, Idioms. Use when writing, changing or reviewing Python code."
    )
    assert len(text) == 226
    testing = compose_description(
        "Test conventions for this repo's pytest suite.",
        ["pytest conventions"],
        "writing, changing or reviewing tests, fixtures or conftest.py",
    )
    assert testing == (
        "Test conventions for this repo's pytest suite. Covers pytest conventions. Use when "
        "writing, changing or reviewing tests, fixtures or conftest.py."
    )
    assert len(testing) == 145


def test_compose_description_without_use_when_ends_with_covers() -> None:
    text = compose_description("Test conventions.", ["pytest conventions"], None)
    assert text == "Test conventions. Covers pytest conventions."


def test_compose_description_adds_missing_periods_once() -> None:
    text = compose_description("Python conventions", ["Docstrings.", "Typing"], "editing code.")
    assert text == "Python conventions. Covers Docstrings, Typing. Use when editing code."
    assert ".." not in text


def test_compose_description_truncates_covers_with_and_n_more() -> None:
    text = compose_description(LONG_DESCRIPTION, PYTHON_CODING_NAMES, LONG_USE_WHEN)
    assert text == (
        "Library-agnostic Python conventions for code in this repo, whatever library it uses. "
        "Covers Dependency injection, Pure core, Data shapes, Typing, Error handling, Context "
        "managers and 3 more. Use when writing, changing, refactoring or reviewing any Python "
        "module, script or notebook in this repo."
    )
    assert len(text) == 295 <= DESCRIPTION_MAX_CHARS


def test_compose_description_names_the_highest_priority_members_when_truncated() -> None:
    reversed_names = PYTHON_CODING_NAMES[::-1]
    text = compose_description(LONG_DESCRIPTION, reversed_names, LONG_USE_WHEN)
    assert "Covers Idioms, Timeouts and retries, Docstrings, Context managers," in text
    assert "Dependency injection" not in text
    assert len(text) <= DESCRIPTION_MAX_CHARS


def test_compose_description_raises_when_one_name_cannot_fit() -> None:
    with pytest.raises(DescriptionOverflowError) as caught:
        compose_description("x" * 250, ["Typing", "Error handling"], "editing Python code")
    expected = "x" * 250 + ". Covers Typing and 1 more. Use when editing Python code."
    assert caught.value.text == expected
    assert caught.value.length == len(expected) == 307
    assert isinstance(caught.value, ValueError)
    assert "307 chars" in str(caught.value)


def test_covers_clause_with_every_member_has_no_more_tail() -> None:
    assert covers_clause(["Typing", "Docstrings", "Idioms"], 3) == (
        "Covers Typing, Docstrings, Idioms."
    )
    assert covers_clause(["Typing", "Docstrings", "Idioms"], 1) == "Covers Typing and 2 more."


@pytest.mark.parametrize("shown", [0, 4])
def test_covers_clause_rejects_a_count_outside_the_names(shown: int) -> None:
    with pytest.raises(ValueError, match=f"got shown={shown}"):
        covers_clause(["Typing", "Docstrings", "Idioms"], shown)


def test_worst_case_description_includes_the_and_n_more_tail() -> None:
    longest = "Timeouts and retries for every network call"
    no_tail = "x" * 210 + f". Covers {longest}. Use when editing Python code."
    assert len(no_tail) == 293  # a one-name clause without its tail would fit
    worst = worst_case_description("x" * 210, TWELVE_NAMES, "editing Python code")
    assert worst == "x" * 210 + f". Covers {longest} and 11 more. Use when editing Python code."
    assert len(worst) == 305 > DESCRIPTION_MAX_CHARS  # so V11 fails this skill


def test_compose_description_never_raises_for_any_subset_when_the_worst_case_fits() -> None:
    description, use_when = "x" * 200, "editing Python code"
    assert len(worst_case_description(description, TWELVE_NAMES, use_when)) == 295
    for size in range(1, len(TWELVE_NAMES) + 1):
        for subset in combinations(TWELVE_NAMES, size):
            text = compose_description(description, subset, use_when)
            assert len(text) <= DESCRIPTION_MAX_CHARS, subset


def test_worst_case_description_has_no_tail_for_one_member() -> None:
    assert worst_case_description("X.", ["Typing"], None) == "X. Covers Typing."
    assert worst_case_description("X.", ["Typing", "Error handling"], None) == (
        "X. Covers Error handling and 1 more."
    )


@pytest.mark.parametrize("compose", [compose_description, worst_case_description])
def test_composing_without_members_is_an_error(
    compose: Callable[[str, Sequence[str], str | None], str],
) -> None:
    with pytest.raises(ValueError, match=r"at least one member name, got \[\]"):
        compose("X.", [], None)
