"""Tests for the ``[expected]`` BOOL evaluators (R3) — ``evaluators/expected.py``.

The four checks are parameterized, **un-registered** evaluators (like
``JudgedCriterion``) that grade one BOOL over the candidate tree
(:attr:`EvalContext.tree`) — and, for ``file_unchanged``, the baseline tree
(:attr:`EvalContext.baseline_tree`). Each has a must-be-true ``fail`` floor so a
``0.0`` measurement breaches the absolute gate. Tests are hermetic: a tmp_path
tree stands in for the candidate, another for the baseline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evaluators.expected import (
    FileContains,
    FileExists,
    FileForbidden,
    FileUnchanged,
    _ExpectedEvaluator,
)
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import AbsoluteThreshold, EvalContext

if TYPE_CHECKING:
    from pathlib import Path


def _ctx(tree: Path | None, baseline_tree: Path | None = None) -> EvalContext:
    return EvalContext(
        module=None,
        source="",
        label="expected",
        tree=tree,
        baseline_tree=baseline_tree,
    )


# --------------------------------------------------------------------------- #
# Descriptor attributes (mirror JudgedCriterion's parameterized contract)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "evaluator",
    [
        FileExists("a.py"),
        FileContains("a.py", "x"),
        FileUnchanged("a.py"),
        FileForbidden("a.py"),
    ],
)
def test_expected_descriptor_attrs(evaluator: _ExpectedEvaluator) -> None:
    assert evaluator.value_kind is ValueKind.BOOL
    assert evaluator.determinism is Determinism.DETERMINISTIC
    assert evaluator.higher_is_worse is False
    assert evaluator.scope is Scope.FILE
    assert evaluator.needs_project is False
    assert evaluator.requires is None
    assert evaluator.default_weight == 0.0
    # Must-be-true: a False (0.0) must breach the absolute fail floor.
    assert evaluator.default_absolute == AbsoluteThreshold(fail=1.0)


def test_expected_names() -> None:
    assert FileExists("out.py").name == "expected:file_exists:out.py"
    assert FileUnchanged("src/m.py").name == "expected:file_unchanged:src/m.py"
    assert FileForbidden("bad.py").name == "expected:file_forbidden:bad.py"
    # file_contains keys on path + pattern so two patterns over one file differ.
    ev = FileContains("out.py", "def foo")
    assert ev.name == "expected:file_contains:out.py~/def foo/"


# --------------------------------------------------------------------------- #
# available() gating
# --------------------------------------------------------------------------- #


def test_available_false_without_tree() -> None:
    assert FileExists("a.py").available(_ctx(None)) is False


def test_available_true_with_tree(tmp_path: Path) -> None:
    assert FileExists("a.py").available(_ctx(tmp_path)) is True


def test_evaluate_without_tree_returns_empty() -> None:
    assert FileExists("a.py").evaluate(_ctx(None)) == []


# --------------------------------------------------------------------------- #
# file_exists
# --------------------------------------------------------------------------- #


def test_file_exists_pass(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    m = FileExists("a.py").evaluate(_ctx(tmp_path))[0]
    assert m.value == 1.0
    assert m.scope_key == "a.py"


def test_file_exists_fail_when_missing(tmp_path: Path) -> None:
    assert FileExists("missing.py").evaluate(_ctx(tmp_path))[0].value == 0.0


def test_file_exists_fail_on_directory(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    # A directory is not a regular file => the check does not hold.
    assert FileExists("pkg").evaluate(_ctx(tmp_path))[0].value == 0.0


# --------------------------------------------------------------------------- #
# file_contains (regex)
# --------------------------------------------------------------------------- #


def test_file_contains_pass_regex(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def _band(n):\n    return n\n", encoding="utf-8")
    assert FileContains("a.py", r"def _band\(").evaluate(_ctx(tmp_path))[0].value == 1.0


def test_file_contains_fail_no_match(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert FileContains("a.py", r"NOPE_not_present").evaluate(_ctx(tmp_path))[0].value == 0.0


def test_file_contains_fail_missing_file(tmp_path: Path) -> None:
    assert FileContains("missing.py", r".").evaluate(_ctx(tmp_path))[0].value == 0.0


# --------------------------------------------------------------------------- #
# file_unchanged (vs baseline tree)
# --------------------------------------------------------------------------- #


def test_file_unchanged_pass_identical(tmp_path: Path) -> None:
    cand = tmp_path / "cand"
    base = tmp_path / "base"
    cand.mkdir()
    base.mkdir()
    (cand / "a.py").write_text("same\n", encoding="utf-8")
    (base / "a.py").write_text("same\n", encoding="utf-8")
    assert FileUnchanged("a.py").evaluate(_ctx(cand, base))[0].value == 1.0


def test_file_unchanged_fail_when_modified(tmp_path: Path) -> None:
    cand = tmp_path / "cand"
    base = tmp_path / "base"
    cand.mkdir()
    base.mkdir()
    (cand / "a.py").write_text("changed\n", encoding="utf-8")
    (base / "a.py").write_text("original\n", encoding="utf-8")
    assert FileUnchanged("a.py").evaluate(_ctx(cand, base))[0].value == 0.0


def test_file_unchanged_fail_without_baseline_tree(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("same\n", encoding="utf-8")
    # No baseline tree => the check cannot hold.
    assert FileUnchanged("a.py").evaluate(_ctx(tmp_path, None))[0].value == 0.0


def test_file_unchanged_fail_when_candidate_missing(tmp_path: Path) -> None:
    """A file present in the baseline but deleted in the candidate is *changed*."""
    cand = tmp_path / "cand"
    base = tmp_path / "base"
    cand.mkdir()
    base.mkdir()
    (base / "a.py").write_text("original\n", encoding="utf-8")  # candidate lacks a.py
    assert FileUnchanged("a.py").evaluate(_ctx(cand, base))[0].value == 0.0


# --------------------------------------------------------------------------- #
# file_forbidden
# --------------------------------------------------------------------------- #


def test_file_forbidden_pass_when_absent(tmp_path: Path) -> None:
    assert FileForbidden("nope.py").evaluate(_ctx(tmp_path))[0].value == 1.0


def test_file_forbidden_fail_when_present(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("x = 1\n", encoding="utf-8")
    assert FileForbidden("bad.py").evaluate(_ctx(tmp_path))[0].value == 0.0


def test_file_forbidden_fail_when_dir_present(tmp_path: Path) -> None:
    (tmp_path / "__pycache__").mkdir()
    # A forbidden *directory* present also breaches (exists(), not is_file()).
    assert FileForbidden("__pycache__").evaluate(_ctx(tmp_path))[0].value == 0.0


# --------------------------------------------------------------------------- #
# Not registered (parameterized per entry, like JudgedCriterion)
# --------------------------------------------------------------------------- #


def test_expected_evaluators_are_not_registered() -> None:
    from coding_agent_playbook.evaluators.registry import all_evaluators

    names = {ev.name for ev in all_evaluators()}
    assert not any(n.startswith("expected:") for n in names)
