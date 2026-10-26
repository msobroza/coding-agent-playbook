"""Tests for the eval-block → per-trial compile wiring (C7).

The C7 cutover replaces the fused ``[expected]``/``[metrics]``/``[rubric]`` blocks
with ``[gate]``/``[rubric]``/``[verdict]``. A sample compiles (via
:func:`~coding_agent_playbook.evals.sample.compile_eval_sample`) into one per-trial
:class:`~coding_agent_playbook.grading.rubric.Rubric` carrying the two named
layer checks (``id="gate"`` / ``id="rubric"``) plus a derived verdict AST. These
tests cover the compile result shape, the file/metric/judged check leaves, and the
judge-dormancy of the rubric layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.evals.checks.files import (
    FileExistsCheck,
    FileUnchangedCheck,
)
from coding_agent_playbook.evals.sample import EvalSample, compile_eval_sample
from coding_agent_playbook.grading.check import ThresholdCheck
from coding_agent_playbook.grading.compose import AllOf
from coding_agent_playbook.grading.rubric import Rubric
from coding_agent_playbook.grading.types import EvalContext


def _sample(data: dict[str, Any]) -> EvalSample:
    base: dict[str, Any] = {"id": "t", "description": "d"}
    base.update(data)
    return EvalSample.from_dict(
        base, prompt_id="p", source_path=Path("/tmp/sample.toml"), source_package="<test>"
    )


def _empty_ctx() -> EvalContext:
    return EvalContext(module=None, source="", label="output")


# --- compile shape -----------------------------------------------------------


def test_gate_and_rubric_compile_to_named_layers() -> None:
    sample = _sample(
        {
            "gate": {"bind": {"a": {"check": "file_exists", "path": "out.py"}}},
            "rubric": {"bind": {"q": {"fail": 0.5, "rubric": [{"judge": "clear", "weight": 1.0}]}}},
            "verdict": {"trial": "gate and rubric"},
        }
    )
    compiled = compile_eval_sample(sample)
    assert [c.id for c in compiled.per_trial.checks] == ["gate", "rubric"]
    assert compiled.layers == frozenset({"gate", "rubric"})
    assert isinstance(compiled.per_trial, Rubric)


def test_gate_only_compiles_one_layer() -> None:
    sample = _sample(
        {
            "gate": {"bind": {"a": {"check": "file_exists", "path": "out.py"}}},
            "verdict": {"trial": "gate"},
        }
    )
    compiled = compile_eval_sample(sample)
    assert [c.id for c in compiled.per_trial.checks] == ["gate"]
    assert compiled.layers == frozenset({"gate"})


def test_rubric_only_compiles_one_layer() -> None:
    sample = _sample(
        {
            "rubric": {"bind": {"q": {"fail": 0.5, "rubric": [{"judge": "clear", "weight": 1.0}]}}},
            "verdict": {"trial": "rubric"},
        }
    )
    compiled = compile_eval_sample(sample)
    assert [c.id for c in compiled.per_trial.checks] == ["rubric"]
    assert compiled.layers == frozenset({"rubric"})


# --- gate layer: file checks under the composed handle -----------------------


def test_gate_handles_compile_to_file_checks() -> None:
    sample = _sample(
        {
            "gate": {
                "expr": "created and unchanged",
                "bind": {
                    "created": {"check": "file_exists", "path": "out.py"},
                    "unchanged": {"check": "file_unchanged", "path": "src/m.py"},
                },
            },
            "verdict": {"trial": "gate"},
        }
    )
    compiled = compile_eval_sample(sample)
    (gate_layer,) = compiled.per_trial.checks
    assert isinstance(gate_layer, AllOf)
    # The layer wraps an AllOf("created and unchanged") over the two file checks.
    leaves = _file_check_leaves(gate_layer)
    kinds = {type(c) for c in leaves}
    assert FileExistsCheck in kinds
    assert FileUnchangedCheck in kinds


def _file_check_leaves(check: Any) -> list[Any]:
    """Collect the file-check leaves under a composed check tree."""
    out: list[Any] = []
    if isinstance(check, (FileExistsCheck, FileUnchangedCheck)):
        out.append(check)
    children = getattr(check, "children", ())
    for child in children:
        out.extend(_file_check_leaves(child))
    return out


# --- rubric layer: judge-dormant without a judge -----------------------------


def test_rubric_layer_is_dormant_without_a_judge() -> None:
    """The rubric layer wraps a ThresholdCheck over a judged Rubric; with no judge
    on the ctx the underlying rubric reports unavailable (so the layer skips)."""
    sample = _sample(
        {
            "rubric": {"bind": {"q": {"fail": 0.5, "rubric": [{"judge": "clear", "weight": 1.0}]}}},
            "verdict": {"trial": "rubric"},
        }
    )
    compiled = compile_eval_sample(sample)
    (rubric_layer,) = compiled.per_trial.checks
    # The threshold's metric is a judged Rubric: unavailable without ctx.judge.
    threshold = _threshold_under(rubric_layer)
    assert isinstance(threshold, ThresholdCheck)
    rubric_metric = threshold.metric
    assert isinstance(rubric_metric, Rubric)
    assert rubric_metric.available(_empty_ctx()) is False


def _threshold_under(check: Any) -> Any:
    """Find the first ThresholdCheck leaf under a composed check tree."""
    if isinstance(check, ThresholdCheck):
        return check
    for child in getattr(check, "children", ()):
        found = _threshold_under(child)
        if found is not None:
            return found
    return None


# --- compile faults are raised, not swallowed --------------------------------


def test_unknown_check_raises_on_compile() -> None:
    sample = _sample(
        {
            "gate": {"bind": {"a": {"check": "no_such", "path": "x"}}},
            "verdict": {"trial": "gate"},
        }
    )
    with pytest.raises(KeyError):
        compile_eval_sample(sample)


def test_rubric_weight_sum_raises_on_compile() -> None:
    sample = _sample(
        {
            "rubric": {
                "bind": {
                    "q": {
                        "fail": 0.5,
                        "rubric": [{"judge": "a", "weight": 0.3}, {"judge": "b", "weight": 0.3}],
                    }
                }
            },
            "verdict": {"trial": "rubric"},
        }
    )
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        compile_eval_sample(sample)
