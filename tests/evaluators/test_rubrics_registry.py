"""Tests for the named-rubric registry — ``evaluators/rubrics.py``.

The named-rubric registry is the out-of-tree extension point that bridges a
code-defined :class:`~coding_agent_playbook.evaluators.rubric.Rubric` subclass
(its :attr:`CRITERIA`) and a TOML ``[rubric] ref = "<name>"`` reference. It
mirrors the :mod:`coding_agent_playbook.evaluators.metric` registry idiom:
builtins/registered classes win over an entry-point plugin of the same name,
:func:`get_rubric` resolves a *built* :class:`Rubric` instance, and
:func:`all_rubric_names` lists every known name for validator messages.

The engine ships **no** builtin rubrics (this is the third-party extension
point), so these tests register stub subclasses via :func:`register_rubric`.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.evaluators import rubrics as rubrics_mod
from coding_agent_playbook.evaluators.checks.judged import JudgeCheck
from coding_agent_playbook.evaluators.rubric import Rubric
from coding_agent_playbook.evaluators.rubrics import (
    all_rubric_names,
    get_rubric,
    register_rubric,
)


def _register(name: str, criteria: tuple[tuple[str, float], ...]) -> type[Rubric]:
    """Register a stub Rubric subclass under ``name`` and return it."""

    @register_rubric(name)
    class _Stub(Rubric):
        CRITERIA = criteria

    return _Stub


def test_register_and_get_rubric_returns_built_instance() -> None:
    name = "_test_review_rubric"
    _register(
        name,
        (
            ("Findings prioritized correctly", 1.0),
            ("Each finding proposes a concrete fix", 3.0),
        ),
    )
    try:
        rubric = get_rubric(name)
        assert isinstance(rubric, Rubric)
        assert all(isinstance(c, JudgeCheck) for c in rubric.checks)
        assert [c.criterion for c in rubric.checks] == [  # type: ignore[attr-defined]
            "Findings prioritized correctly",
            "Each finding proposes a concrete fix",
        ]
        # define() normalizes 1:3 ⇒ 0.25 / 0.75.
        assert [c.weight for c in rubric.checks] == [0.25, 0.75]
    finally:
        rubrics_mod._RUBRIC_REGISTRY.pop(name, None)


def test_get_rubric_name_is_the_registry_key() -> None:
    name = "_test_named_rubric"
    _register(name, (("a", 1.0),))
    try:
        # define() defaults the rubric name to the class __name__; the registry
        # key is the explicit string arg to register_rubric.
        assert name in all_rubric_names()
        assert isinstance(get_rubric(name), Rubric)
    finally:
        rubrics_mod._RUBRIC_REGISTRY.pop(name, None)


def test_all_rubric_names_membership() -> None:
    name = "_test_membership_rubric"
    assert name not in all_rubric_names()
    _register(name, (("a", 1.0),))
    try:
        assert name in all_rubric_names()
    finally:
        rubrics_mod._RUBRIC_REGISTRY.pop(name, None)


def test_get_rubric_unknown_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_rubric("_no_such_rubric_anywhere")


def test_entry_point_rubric_is_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    class _PluginRubric(Rubric):
        CRITERIA = (("plugin criterion", 1.0),)

    class _FakeEntryPoint:
        name = "_plugin_rubric"

        def load(self) -> type[Rubric]:
            return _PluginRubric

    def _fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        assert group == "coding_agent_playbook.rubrics"
        return [_FakeEntryPoint()]

    monkeypatch.setattr(
        "coding_agent_playbook.evaluators.rubrics.metadata.entry_points",
        _fake_entry_points,
    )
    assert "_plugin_rubric" in all_rubric_names()
    rubric = get_rubric("_plugin_rubric")
    assert [c.criterion for c in rubric.checks] == ["plugin criterion"]  # type: ignore[attr-defined]


def test_in_tree_registration_wins_over_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "_clash_rubric"
    _register(name, (("registered criterion", 1.0),))

    class _Imposter(Rubric):
        CRITERIA = (("imposter criterion", 1.0),)

    class _FakeEntryPoint:
        name = "_clash_rubric"

        def load(self) -> type[Rubric]:
            return _Imposter

    def _fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        return [_FakeEntryPoint()]

    monkeypatch.setattr(
        "coding_agent_playbook.evaluators.rubrics.metadata.entry_points",
        _fake_entry_points,
    )
    try:
        rubric = get_rubric(name)
        # The in-tree registration wins: the registered criterion, not the imposter.
        assert [c.criterion for c in rubric.checks] == [  # type: ignore[attr-defined]
            "registered criterion"
        ]
        names = all_rubric_names()
        assert names.count(name) == 1
    finally:
        rubrics_mod._RUBRIC_REGISTRY.pop(name, None)
