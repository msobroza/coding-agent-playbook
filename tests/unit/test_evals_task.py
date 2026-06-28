"""Tests for ``coding_agent_playbook.evals.task`` dataclasses (SPEC §15.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.evals.task import (
    EvalTask,
    ExpectedOutcome,
    Rubric,
    TaskInvocation,
    TaskSetup,
)


def _minimal_dict() -> dict[str, Any]:
    return {
        "id": "demo-happy-path",
        "prompt_id": "demo",
        "description": "A demo task",
    }


def _full_dict() -> dict[str, Any]:
    """The SPEC §6.5.3 example, top-level table form (already parsed by tomllib)."""
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
        "expected": {
            "files_created": ["tests/test_calculator.py"],
            "files_must_contain": [
                {"path": "tests/test_calculator.py", "pattern": "def test_add"},
                {"path": "tests/test_calculator.py", "pattern": "parametrize"},
            ],
            "files_unchanged": ["src/calculator.py"],
            "files_forbidden": ["__pycache__/", "tests/conftest.py"],
        },
        "rubric": {
            "criteria": [
                "Tests use pytest.parametrize for table-driven cases",
                "Test file lives at tests/test_calculator.py (mirror layout)",
                "All public branches of `add` are covered",
                "No mocking is used (function is pure)",
            ],
            "weights": [0.2, 0.2, 0.4, 0.2],
        },
    }


def test_eval_task_from_dict_parses_minimal_task(tmp_path: Path) -> None:
    task = EvalTask.from_dict(
        _minimal_dict(),
        source_path=tmp_path / "task.toml",
        source_package="coding_agent_playbook",
    )
    assert task.id == "demo-happy-path"
    assert task.prompt_id == "demo"
    assert task.description == "A demo task"
    assert task.version == 1
    assert task.source_path == tmp_path / "task.toml"
    assert task.source_package == "coding_agent_playbook"
    assert isinstance(task.setup, TaskSetup)
    assert isinstance(task.invocation, TaskInvocation)
    assert task.expected is None
    assert task.rubric is None


def test_eval_task_from_dict_parses_full_task(tmp_path: Path) -> None:
    task = EvalTask.from_dict(
        _full_dict(),
        source_path=tmp_path / "task.toml",
        source_package="coding_agent_playbook",
    )
    assert task.id == "generate-tests-happy-path"
    assert task.prompt_id == "generate-tests"
    assert task.version == 1

    assert task.setup.files == [Path("src/calculator.py")]
    assert task.setup.project_kind == "python-application"
    assert task.setup.python_version == "3.12"
    assert task.setup.frameworks == ["pytest", "pytest-asyncio"]

    assert task.invocation.prompt_args.startswith("for the add function")
    assert task.invocation.input_variables == {"target": "src/calculator.py::add"}

    assert isinstance(task.expected, ExpectedOutcome)
    assert task.expected.files_created == ["tests/test_calculator.py"]
    assert task.expected.files_must_contain == [
        {"path": "tests/test_calculator.py", "pattern": "def test_add"},
        {"path": "tests/test_calculator.py", "pattern": "parametrize"},
    ]
    assert task.expected.files_unchanged == ["src/calculator.py"]
    assert task.expected.files_forbidden == ["__pycache__/", "tests/conftest.py"]

    assert isinstance(task.rubric, Rubric)
    assert len(task.rubric.criteria) == 4
    assert task.rubric.weights == [0.2, 0.2, 0.4, 0.2]


def test_eval_task_from_dict_rejects_missing_id(tmp_path: Path) -> None:
    data = _minimal_dict()
    del data["id"]
    with pytest.raises(ValueError, match="id"):
        EvalTask.from_dict(
            data,
            source_path=tmp_path / "task.toml",
            source_package="coding_agent_playbook",
        )


def test_eval_task_from_dict_rejects_missing_prompt_id(tmp_path: Path) -> None:
    data = _minimal_dict()
    del data["prompt_id"]
    with pytest.raises(ValueError, match="prompt_id"):
        EvalTask.from_dict(
            data,
            source_path=tmp_path / "task.toml",
            source_package="coding_agent_playbook",
        )


def test_eval_task_from_dict_rejects_missing_description(tmp_path: Path) -> None:
    data = _minimal_dict()
    del data["description"]
    with pytest.raises(ValueError, match="description"):
        EvalTask.from_dict(
            data,
            source_path=tmp_path / "task.toml",
            source_package="coding_agent_playbook",
        )


def test_eval_task_from_dict_rejects_non_string_id(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["id"] = 42
    with pytest.raises(ValueError, match="id"):
        EvalTask.from_dict(
            data,
            source_path=tmp_path / "task.toml",
            source_package="coding_agent_playbook",
        )


def test_eval_task_rubric_weights_must_sum_to_one(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["rubric"] = {
        "criteria": ["A", "B"],
        "weights": [0.3, 0.3],  # sums to 0.6
    }
    with pytest.raises(ValueError, match="weights"):
        EvalTask.from_dict(
            data,
            source_path=tmp_path / "task.toml",
            source_package="coding_agent_playbook",
        )


def test_eval_task_rubric_weights_length_must_match_criteria(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["rubric"] = {
        "criteria": ["A", "B", "C"],
        "weights": [0.5, 0.5],  # length mismatch
    }
    with pytest.raises(ValueError, match="weights"):
        EvalTask.from_dict(
            data,
            source_path=tmp_path / "task.toml",
            source_package="coding_agent_playbook",
        )


def test_eval_task_rubric_weights_omitted_is_fine(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["rubric"] = {"criteria": ["A", "B"]}
    task = EvalTask.from_dict(
        data,
        source_path=tmp_path / "task.toml",
        source_package="coding_agent_playbook",
    )
    assert isinstance(task.rubric, Rubric)
    assert task.rubric.weights is None


# --- [rubric] ref = "<name>" (named-rubric registry) -------------------------


def test_eval_task_rubric_ref_parses(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["rubric"] = {"ref": "code-review"}
    task = EvalTask.from_dict(
        data,
        source_path=tmp_path / "task.toml",
        source_package="coding_agent_playbook",
    )
    assert isinstance(task.rubric, Rubric)
    assert task.rubric.ref == "code-review"
    # ref-mode keeps criteria/weights empty — the referenced rubric supplies them.
    assert task.rubric.criteria == []
    assert task.rubric.weights is None


def test_eval_task_rubric_ref_and_criteria_are_mutually_exclusive(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["rubric"] = {"ref": "code-review", "criteria": ["A"]}
    with pytest.raises(ValueError, match="both 'ref' and 'criteria'"):
        EvalTask.from_dict(
            data,
            source_path=tmp_path / "task.toml",
            source_package="coding_agent_playbook",
        )


def test_eval_task_rubric_with_neither_ref_nor_criteria_raises(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["rubric"] = {}
    with pytest.raises(ValueError, match="either 'criteria' or 'ref'"):
        EvalTask.from_dict(
            data,
            source_path=tmp_path / "task.toml",
            source_package="coding_agent_playbook",
        )


def test_eval_task_rubric_ref_must_be_string(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["rubric"] = {"ref": 42}
    with pytest.raises(ValueError, match="ref"):
        EvalTask.from_dict(
            data,
            source_path=tmp_path / "task.toml",
            source_package="coding_agent_playbook",
        )
