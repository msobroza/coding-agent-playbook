"""Tests for the evaluator scope/value-kind/determinism enums (SPEC prM §A)."""

from __future__ import annotations

from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind


def test_scope_members() -> None:
    assert {s.name for s in Scope} == {"FUNCTION", "METHOD", "CLASS", "FILE", "MODULE"}


def test_value_kind_members() -> None:
    assert {v.name for v in ValueKind} == {"NUMERIC", "SCORE", "BOOL"}


def test_determinism_members() -> None:
    assert {d.name for d in Determinism} == {"DETERMINISTIC", "JUDGED"}
