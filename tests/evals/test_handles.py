"""Tests for the handle builder (Track C5).

The handle builder turns a ``[<layer>.bind]`` TOML table into a ``name -> Check``
map for the new task config. Each binding (and any nested child) is exactly one of
five mutually exclusive shapes:

* a **boolean group** - ``all_of`` / ``any_of`` / ``not``;
* a **rubric group** - ``rubric`` (a list of ``{judge, weight}`` pairs) wrapped in
  a :class:`~coding_agent_playbook.grading.check.ThresholdCheck` over the built
  :class:`~coding_agent_playbook.grading.rubric.Rubric`;
* a **standalone check** - ``check`` plus that factory's kwargs;
* a **ref** - ``ref`` resolving via the gate registry (``layer="gate"``) or the
  rubric registry (otherwise).

These tests drive each shape (including nesting), the gate-vs-rubric ``ref``
dispatch by layer, the full-table map, and the ``ValueError`` cases (zero/two
shape-keys, and a non-normalized rubric weight set when enforcement is on).
"""

from __future__ import annotations

import ast
import math

import pytest

from coding_agent_playbook.evals.checks.files import FileExistsCheck
from coding_agent_playbook.evals.compile import _handles
from coding_agent_playbook.evals.compile import gate_registry as gates_mod
from coding_agent_playbook.evals.compile import rubric_registry as rubrics_mod
from coding_agent_playbook.evals.compile._handles import build_handles
from coding_agent_playbook.evals.compile.gate_registry import register_gate
from coding_agent_playbook.evals.compile.rubric_registry import register_rubric
from coding_agent_playbook.grading.check import Check, ThresholdCheck
from coding_agent_playbook.grading.check_registry import all_check_ids, get_check
from coding_agent_playbook.grading.compose import AllOf, AnyOf
from coding_agent_playbook.grading.compose import Not as NotCheck
from coding_agent_playbook.grading.judged import JudgeCheck
from coding_agent_playbook.grading.rubric import Rubric
from tests.import_probe import run_python_probe

# --------------------------------------------------------------------------- #
# Standalone check shape.
# --------------------------------------------------------------------------- #


def test_standalone_file_exists_check() -> None:
    handle = build_handles({"x": {"check": "file_exists", "path": "x.py"}}, layer="gate")["x"]
    assert isinstance(handle, FileExistsCheck)
    assert handle.path == "x.py"


def test_standalone_threshold_check() -> None:
    handle = build_handles(
        {"x": {"check": "threshold", "metric": "cyclomatic_complexity", "fail": 0.5}},
        layer="gate",
    )["x"]
    assert isinstance(handle, ThresholdCheck)
    assert handle.metric.name == "cyclomatic_complexity"


# --------------------------------------------------------------------------- #
# Boolean group shapes.
# --------------------------------------------------------------------------- #


def test_all_of_group_builds_allof_with_two_children() -> None:
    handle = build_handles(
        {
            "x": {
                "all_of": [
                    {"check": "tests_pass"},
                    {"check": "threshold", "metric": "coverage", "fail": 0.8},
                ]
            }
        },
        layer="gate",
    )["x"]
    assert isinstance(handle, AllOf)
    assert len(handle._children) == 2
    assert handle.id == "x"


def test_any_of_group_with_nested_all_of() -> None:
    handle = build_handles(
        {
            "x": {
                "any_of": [
                    {"check": "file_exists", "path": "a.py"},
                    {"all_of": [{"check": "file_exists", "path": "b.py"}]},
                ]
            }
        },
        layer="gate",
    )["x"]
    assert isinstance(handle, AnyOf)
    assert len(handle._children) == 2
    assert isinstance(handle._children[0], FileExistsCheck)
    assert isinstance(handle._children[1], AllOf)
    # nested child ids are namespaced under the parent
    assert handle._children[1].id == "x[1]"


def test_not_group_builds_not() -> None:
    handle = build_handles(
        {"x": {"not": {"check": "file_exists", "path": "a.py"}}},
        layer="gate",
    )["x"]
    assert isinstance(handle, NotCheck)
    assert isinstance(handle._child, FileExistsCheck)
    assert handle.id == "x"


# --------------------------------------------------------------------------- #
# Rubric group shape.
# --------------------------------------------------------------------------- #


def test_rubric_group_wraps_rubric_in_threshold_check() -> None:
    handle = build_handles(
        {
            "x": {
                "rubric": [
                    {"judge": "clear naming", "weight": 0.4},
                    {"judge": "edge cases", "weight": 0.6},
                ],
                "fail": 0.8,
            }
        },
        layer="rubric",
    )["x"]
    assert isinstance(handle, ThresholdCheck)
    rubric = handle.metric
    assert isinstance(rubric, Rubric)
    assert len(rubric.checks) == 2
    assert all(isinstance(c, JudgeCheck) for c in rubric.checks)
    # the fail bound landed on the wrapping ThresholdCheck
    assert handle._absolute.fail == 0.8
    # criteria carry their (already-normalized) weights
    assert [c.criterion for c in rubric.checks] == ["clear naming", "edge cases"]  # type: ignore[attr-defined]


def test_rubric_group_preserves_normalized_weights() -> None:
    # An already-normalized authored set (the only set the sum rule accepts) flows
    # through ``Rubric.of(normalize=True)`` unchanged - normalization is a no-op.
    handle = build_handles(
        {
            "x": {
                "rubric": [
                    {"judge": "a", "weight": 0.25},
                    {"judge": "b", "weight": 0.75},
                ],
                "fail": 0.5,
            }
        },
        layer="rubric",
    )["x"]
    assert isinstance(handle, ThresholdCheck)
    rubric = handle.metric
    assert isinstance(rubric, Rubric)
    weights = [c.weight for c in rubric.checks]
    assert math.isclose(sum(weights), 1.0, abs_tol=1e-9)
    assert math.isclose(weights[0], 0.25, abs_tol=1e-9)
    assert math.isclose(weights[1], 0.75, abs_tol=1e-9)


def test_rubric_group_threshold_floors_judge_checks() -> None:
    handle = build_handles(
        {
            "x": {
                "rubric": [{"judge": "a", "weight": 1.0}],
                "fail": 0.5,
                "threshold": 0.7,
            }
        },
        layer="rubric",
    )["x"]
    assert isinstance(handle, ThresholdCheck)
    rubric = handle.metric
    assert isinstance(rubric, Rubric)
    (judge_check,) = rubric.checks
    assert isinstance(judge_check, JudgeCheck)
    assert judge_check.threshold == 0.7


def test_rubric_group_warn_passes_through() -> None:
    handle = build_handles(
        {
            "x": {
                "rubric": [{"judge": "a", "weight": 1.0}],
                "warn": 0.9,
                "fail": 0.6,
            }
        },
        layer="rubric",
    )["x"]
    assert isinstance(handle, ThresholdCheck)
    assert handle._absolute.warn == 0.9
    assert handle._absolute.fail == 0.6


# --------------------------------------------------------------------------- #
# Ref shape - gate vs rubric registry by layer.
# --------------------------------------------------------------------------- #


def test_ref_resolves_via_gate_registry_when_layer_is_gate() -> None:
    name = "_test_handle_gate"

    @register_gate(name)
    def _gate() -> Check:
        return AllOf(FileExistsCheck("a.py"))

    try:
        handle = build_handles({"x": {"ref": name}}, layer="gate")["x"]
        assert isinstance(handle, AllOf)
    finally:
        gates_mod._GATE_REGISTRY.pop(name, None)


def test_ref_resolves_via_rubric_registry_when_layer_is_rubric() -> None:
    name = "_test_handle_rubric"

    @register_rubric(name)
    class _Stub(Rubric):
        CRITERIA = (("clarity", 1.0),)

    try:
        handle = build_handles({"x": {"ref": name}}, layer="rubric")["x"]
        # A rubric ref is wrapped in a ThresholdCheck so its composite is a boolean
        # composable in the layer expression (the wrapped metric is the named Rubric).
        assert isinstance(handle, ThresholdCheck)
        assert isinstance(handle.metric, Rubric)
        assert all(isinstance(c, JudgeCheck) for c in handle.metric.checks)
    finally:
        rubrics_mod._RUBRIC_REGISTRY.pop(name, None)


# --------------------------------------------------------------------------- #
# Multi-handle table.
# --------------------------------------------------------------------------- #


def test_build_handles_over_multi_handle_table() -> None:
    handles = build_handles(
        {
            "build": {"check": "file_exists", "path": "a.py"},
            "fast": {"check": "threshold", "metric": "coverage", "fail": 0.8},
            "both": {
                "all_of": [
                    {"check": "file_exists", "path": "b.py"},
                    {"check": "file_forbidden", "path": "c.py"},
                ]
            },
        },
        layer="gate",
    )
    assert set(handles) == {"build", "fast", "both"}
    assert isinstance(handles["build"], FileExistsCheck)
    assert isinstance(handles["fast"], ThresholdCheck)
    assert isinstance(handles["both"], AllOf)
    # top-level handle ids match their handle names
    assert handles["both"].id == "both"


# --------------------------------------------------------------------------- #
# Error cases.
# --------------------------------------------------------------------------- #


def test_no_shape_key_raises_value_error() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        build_handles({"x": {"path": "x.py"}}, layer="gate")


def test_two_shape_keys_raises_value_error() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        build_handles(
            {"x": {"check": "file_exists", "ref": "g", "path": "x.py"}},
            layer="gate",
        )


def test_rubric_weights_not_summing_to_one_raises() -> None:
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        build_handles(
            {
                "x": {
                    "rubric": [
                        {"judge": "a", "weight": 0.3},
                        {"judge": "b", "weight": 0.3},
                    ],
                    "fail": 0.5,
                }
            },
            layer="rubric",
        )


# --------------------------------------------------------------------------- #
# Registration by import: the handle builder alone sees every check family.
# --------------------------------------------------------------------------- #

#: Every check id the eval pipeline could look up before the eval-only families
#: (files, answer, aggregate) left the kernel's checks package (N24).
_BASELINE_CHECK_IDS = [
    "answer_matches",
    "coverage",
    "file_contains",
    "file_exists",
    "file_forbidden",
    "file_unchanged",
    "non_regression",
    "pass_at_k",
    "pass_pow_k",
    "tests_pass",
    "threshold",
]


def test_handles_sees_every_check_family() -> None:
    """Importing only the handle builder registers every family before its first lookup.

    A fresh interpreter, because this process has already imported the families
    through other tests, which would hide a family that registers too late.
    """
    probe = (
        f"import {_handles.__name__}; "
        f"from {all_check_ids.__module__} import all_check_ids; "
        "print(sorted(all_check_ids()))"
    )
    assert ast.literal_eval(run_python_probe(probe)) == _BASELINE_CHECK_IDS


def test_all_check_ids_lists_the_file_check_families() -> None:
    """The file-check ids register once the handle builder is imported (moved from the kernel tests)."""
    ids = all_check_ids()
    for expected in ("file_exists", "file_contains", "file_unchanged", "file_forbidden"):
        assert expected in ids


def test_get_check_file_exists_builds_file_check() -> None:
    check = get_check("file_exists", path="x.py")
    assert isinstance(check, FileExistsCheck)
    assert check.path == "x.py"


def test_in_tree_registration_wins_over_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    """A builtin id is resolved from the in-tree factory, not a clashing plugin."""

    def _imposter(**_kwargs: object) -> FileExistsCheck:
        raise AssertionError("the in-tree file_exists factory must win")

    class _FakeEntryPoint:
        name = "file_exists"

        def load(self) -> object:
            return _imposter

    def _fake_entry_points(*, group: str) -> list[_FakeEntryPoint]:
        assert group == "coding_agent_playbook.checks"
        return [_FakeEntryPoint()]

    monkeypatch.setattr(
        "coding_agent_playbook.grading.check_registry.metadata.entry_points",
        _fake_entry_points,
    )
    check = get_check("file_exists", path="y.py")
    assert isinstance(check, FileExistsCheck)
