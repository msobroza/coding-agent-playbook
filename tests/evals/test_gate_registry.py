"""Tests for the Gate registry — ``evals/compile/gate_registry.py``.

A *gate* is a named, composed boolean :class:`~coding_agent_playbook.evaluators.check.Check`
(typically built from the boolean composers ``AllOf``/``AnyOf``/``Not``) that an
out-of-tree package ships and a task references by name. The registry is a verbatim
mirror of the rubric registry: :func:`register_gate` is a decorator factory keyed on
an explicit name, in-tree registrations win over an entry-point plugin of the same
name, and the engine ships **no** builtin gates (this group is purely the extension
point), so these tests register their own stub gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.checks.files import FileExistsCheck, FileForbiddenCheck
from coding_agent_playbook.evals.compile import gate_registry as gates_mod
from coding_agent_playbook.evals.compile.gate_registry import (
    all_gate_names,
    get_gate,
    register_gate,
)
from coding_agent_playbook.evaluators.checks.compose import AllOf

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.check import Check


def _stub_gate() -> Check:
    """A composed boolean gate: both file predicates must hold."""
    return AllOf(FileExistsCheck("a.py"), FileForbiddenCheck("b.py"))


def test_register_and_get_gate_returns_composed_check() -> None:
    name = "_test_gate"

    @register_gate(name)
    def _gate() -> Check:
        return _stub_gate()

    try:
        gate = get_gate(name)
        assert isinstance(gate, AllOf)
    finally:
        gates_mod._GATE_REGISTRY.pop(name, None)


def test_get_gate_unknown_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_gate("_no_such_gate_anywhere")


def test_all_gate_names_membership() -> None:
    name = "_test_membership_gate"
    assert name not in all_gate_names()

    @register_gate(name)
    def _gate() -> Check:
        return _stub_gate()

    try:
        assert name in all_gate_names()
    finally:
        gates_mod._GATE_REGISTRY.pop(name, None)


def test_entry_point_gate_is_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    def _plugin_gate() -> Check:
        return _stub_gate()

    class _FakeEntryPoint:
        name = "_plugin_gate"

        def load(self) -> object:
            return _plugin_gate

    def _fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        assert group == "coding_agent_playbook.gates"
        return [_FakeEntryPoint()]

    monkeypatch.setattr(
        "coding_agent_playbook.evals.compile.gate_registry.metadata.entry_points",
        _fake_entry_points,
    )
    assert "_plugin_gate" in all_gate_names()
    assert isinstance(get_gate("_plugin_gate"), AllOf)


def test_in_tree_registration_wins_over_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "_clash_gate"

    @register_gate(name)
    def _registered() -> Check:
        return _stub_gate()

    def _imposter() -> Check:
        raise AssertionError("the in-tree gate must win")

    class _FakeEntryPoint:
        name = "_clash_gate"

        def load(self) -> object:
            return _imposter

    def _fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        return [_FakeEntryPoint()]

    monkeypatch.setattr(
        "coding_agent_playbook.evals.compile.gate_registry.metadata.entry_points",
        _fake_entry_points,
    )
    try:
        assert isinstance(get_gate(name), AllOf)
        assert all_gate_names().count(name) == 1
    finally:
        gates_mod._GATE_REGISTRY.pop(name, None)
