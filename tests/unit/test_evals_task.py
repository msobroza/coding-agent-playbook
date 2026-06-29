"""Tests for ``coding_agent_playbook.evals.task`` dataclasses (C7 schema)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.evals.task import (
    EvalTask,
    Layer,
    TaskInvocation,
    TaskSetup,
    Verdict,
    compile_eval_task,
)


def _minimal_dict() -> dict[str, Any]:
    return {
        "id": "demo-happy-path",
        "prompt_id": "demo",
        "description": "A demo task",
    }


def _full_dict() -> dict[str, Any]:
    """A representative task in the C7 ``[gate]``/``[rubric]``/``[verdict]`` shape."""
    return {
        "id": "generate-tests-happy-path",
        "prompt_id": "generate-tests",
        "description": "Generate tests for a simple pure function with no edge cases",
        "version": 1,
        "setup": {
            "files": ["src/calculator.py"],
            "project_kind": "python-application",
            "python_version": "3.12",
            "frameworks": ["pytest", "pytest-asyncio"],
        },
        "invocation": {
            "prompt_args": "for the add function in src/calculator.py",
            "input_variables": {"target": "src/calculator.py::add"},
        },
        "gate": {
            "expr": "created and contains and unchanged",
            "bind": {
                "created": {"check": "file_exists", "path": "tests/test_calculator.py"},
                "contains": {
                    "check": "file_contains",
                    "path": "tests/test_calculator.py",
                    "pattern": "def test_add",
                },
                "unchanged": {"check": "file_unchanged", "path": "src/calculator.py"},
            },
        },
        "rubric": {
            "expr": "quality",
            "bind": {
                "quality": {
                    "fail": 0.5,
                    "rubric": [
                        {"judge": "Tests use pytest.parametrize", "weight": 0.4},
                        {"judge": "Test file mirrors layout", "weight": 0.2},
                        {"judge": "All branches covered", "weight": 0.2},
                        {"judge": "No mocking is used", "weight": 0.2},
                    ],
                },
            },
        },
        "verdict": {"trial": "gate and rubric"},
    }


def _make(data: dict[str, Any], tmp_path: Path) -> EvalTask:
    return EvalTask.from_dict(
        data,
        source_path=tmp_path / "task.toml",
        source_package="coding_agent_playbook",
    )


# --- minimal / required-field parsing ----------------------------------------


def test_eval_task_from_dict_parses_minimal_task(tmp_path: Path) -> None:
    task = _make(_minimal_dict(), tmp_path)
    assert task.id == "demo-happy-path"
    assert task.prompt_id == "demo"
    assert task.description == "A demo task"
    assert task.version == 1
    assert task.source_path == tmp_path / "task.toml"
    assert task.source_package == "coding_agent_playbook"
    assert isinstance(task.setup, TaskSetup)
    assert isinstance(task.invocation, TaskInvocation)
    # No eval blocks => all None, verdict defaults.
    assert task.gate is None
    assert task.rubric is None
    assert task.aggregate is None
    assert task.verdict == Verdict(mode="boolean", trial="gate and rubric")


def test_eval_task_from_dict_parses_full_task(tmp_path: Path) -> None:
    task = _make(_full_dict(), tmp_path)
    assert task.id == "generate-tests-happy-path"
    assert task.prompt_id == "generate-tests"
    assert task.version == 1

    assert task.setup.files == [Path("src/calculator.py")]
    assert task.setup.project_kind == "python-application"
    assert task.setup.frameworks == ["pytest", "pytest-asyncio"]

    assert task.invocation.prompt_args.startswith("for the add function")
    assert task.invocation.input_variables == {"target": "src/calculator.py::add"}

    assert isinstance(task.gate, Layer)
    assert task.gate.expr == "created and contains and unchanged"
    assert set(task.gate.bind) == {"created", "contains", "unchanged"}
    assert task.gate.bind["created"] == {"check": "file_exists", "path": "tests/test_calculator.py"}

    assert isinstance(task.rubric, Layer)
    assert task.rubric.expr == "quality"
    assert task.rubric.bind["quality"]["fail"] == 0.5
    assert len(task.rubric.bind["quality"]["rubric"]) == 4

    assert task.verdict == Verdict(mode="boolean", trial="gate and rubric")


def test_eval_task_from_dict_rejects_missing_id(tmp_path: Path) -> None:
    data = _minimal_dict()
    del data["id"]
    with pytest.raises(ValueError, match="id"):
        _make(data, tmp_path)


def test_eval_task_from_dict_rejects_missing_prompt_id(tmp_path: Path) -> None:
    data = _minimal_dict()
    del data["prompt_id"]
    with pytest.raises(ValueError, match="prompt_id"):
        _make(data, tmp_path)


def test_eval_task_from_dict_rejects_missing_description(tmp_path: Path) -> None:
    data = _minimal_dict()
    del data["description"]
    with pytest.raises(ValueError, match="description"):
        _make(data, tmp_path)


def test_eval_task_from_dict_rejects_non_string_id(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["id"] = 42
    with pytest.raises(ValueError, match="id"):
        _make(data, tmp_path)


# --- block shape parsing (structural only; semantics is the compiler's job) ---


def test_gate_parses_bind_and_expr(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {
        "expr": "a",
        "bind": {"a": {"check": "file_exists", "path": "x.py"}},
    }
    task = _make(data, tmp_path)
    assert isinstance(task.gate, Layer)
    assert task.gate.expr == "a"
    assert task.gate.bind == {"a": {"check": "file_exists", "path": "x.py"}}


def test_gate_expr_optional(tmp_path: Path) -> None:
    """A single-handle gate may omit ``expr`` (the compiler defaults it)."""
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "file_exists", "path": "x.py"}}}
    task = _make(data, tmp_path)
    assert task.gate is not None
    assert task.gate.expr is None


def test_verdict_trial_parses(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "file_exists", "path": "x.py"}}}
    data["verdict"] = {"trial": "gate"}
    task = _make(data, tmp_path)
    assert task.verdict == Verdict(mode="boolean", trial="gate")


def test_aggregate_parses_bind_and_expr(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "file_exists", "path": "x.py"}}}
    data["verdict"] = {"trial": "gate"}
    data["aggregate"] = {
        "expr": "pass_rate",
        "bind": {"pass_rate": {"metric": "pass_at_k", "k": 3, "over": "verdict"}},
    }
    task = _make(data, tmp_path)
    assert isinstance(task.aggregate, Layer)
    assert task.aggregate.expr == "pass_rate"
    assert task.aggregate.bind["pass_rate"] == {"metric": "pass_at_k", "k": 3, "over": "verdict"}


def test_gate_must_be_table(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = []
    with pytest.raises(ValueError, match="gate"):
        _make(data, tmp_path)


def test_gate_bind_must_be_table(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"bind": "nope"}
    with pytest.raises(ValueError, match="bind"):
        _make(data, tmp_path)


def test_gate_bind_handle_must_be_table(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": "nope"}}
    with pytest.raises(ValueError, match=r"bind\.a"):
        _make(data, tmp_path)


def test_gate_expr_must_be_string(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"expr": 42, "bind": {"a": {"check": "file_exists", "path": "x"}}}
    with pytest.raises(ValueError, match="expr"):
        _make(data, tmp_path)


def test_verdict_trial_must_be_string(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["verdict"] = {"trial": 1}
    with pytest.raises(ValueError, match="trial"):
        _make(data, tmp_path)


# --- compile_eval_task / EvalTask.compiled -----------------------------------


def test_compiled_builds_layer_checks(tmp_path: Path) -> None:
    task = _make(_full_dict(), tmp_path)
    compiled = compile_eval_task(task)
    assert [c.id for c in compiled.per_trial.checks] == ["gate", "rubric"]
    assert compiled.layers == frozenset({"gate", "rubric"})


def test_compiled_method_matches_free_function(tmp_path: Path) -> None:
    task = _make(_full_dict(), tmp_path)
    via_method = task.compiled()
    assert via_method.layers == frozenset({"gate", "rubric"})
    assert [c.id for c in via_method.per_trial.checks] == ["gate", "rubric"]


def test_compile_raises_on_no_layer(tmp_path: Path) -> None:
    """A task with no [gate] and no [rubric] cannot compile (at-least-one rule)."""
    task = _make(_minimal_dict(), tmp_path)
    with pytest.raises(ValueError, match="at least one"):
        compile_eval_task(task)


def test_compile_raises_on_unknown_check(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "not_a_real_check", "path": "x"}}}
    data["verdict"] = {"trial": "gate"}
    task = _make(data, tmp_path)
    with pytest.raises(KeyError):
        compile_eval_task(task)


# --- C10: weighted-composite verdict parsing + compile-time guards -----------


def _weighted_layers_data() -> dict[str, Any]:
    """A task with both layers present so a weighted-verdict tests have a valid base."""
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "file_exists", "path": "x.py"}}}
    data["rubric"] = {
        "bind": {
            "q": {
                "fail": 0.5,
                "rubric": [{"judge": "c", "weight": 1.0}],
            }
        }
    }
    return data


def test_verdict_weighted_form_parses(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {"weights": {"gate": 0.4, "rubric": 0.6}, "fail": 0.7}
    task = _make(data, tmp_path)
    assert task.verdict.mode == "weighted"
    assert task.verdict.trial is None
    assert task.verdict.weights == {"gate": 0.4, "rubric": 0.6}
    assert task.verdict.fail == 0.7
    assert task.verdict.warn is None


def test_verdict_weighted_form_with_warn_parses(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {
        "weights": {"gate": 0.4, "rubric": 0.6},
        "fail": 0.5,
        "warn": 0.8,
    }
    task = _make(data, tmp_path)
    assert task.verdict.warn == 0.8


def test_verdict_weighted_form_rejects_trial_alongside_weights(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {
        "trial": "gate and rubric",
        "weights": {"gate": 0.4, "rubric": 0.6},
        "fail": 0.5,
    }
    with pytest.raises(ValueError, match="cannot set both"):
        _make(data, tmp_path)


def test_verdict_weighted_form_rejects_weights_not_summing_to_one(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {"weights": {"gate": 0.3, "rubric": 0.5}, "fail": 0.5}
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        _make(data, tmp_path)


def test_verdict_weighted_form_requires_fail(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {"weights": {"gate": 0.4, "rubric": 0.6}}
    with pytest.raises(ValueError, match="requires 'fail'"):
        _make(data, tmp_path)


def test_verdict_weighted_form_rejects_empty_weights(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {"weights": {}, "fail": 0.5}
    with pytest.raises(ValueError, match="non-empty"):
        _make(data, tmp_path)


def test_verdict_weighted_form_rejects_fail_out_of_range(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {"weights": {"gate": 0.4, "rubric": 0.6}, "fail": 1.5}
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        _make(data, tmp_path)


def test_compile_raises_on_unknown_layer_in_weights(tmp_path: Path) -> None:
    """Weights referencing a non-present layer is caught at compile time."""
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "file_exists", "path": "x.py"}}}
    # No [rubric], yet weights mention it.
    data["verdict"] = {"weights": {"gate": 0.4, "rubric": 0.6}, "fail": 0.5}
    task = _make(data, tmp_path)
    with pytest.raises(ValueError, match="unknown layer"):
        compile_eval_task(task)
