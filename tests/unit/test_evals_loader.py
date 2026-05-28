"""Tests for ``coding_agent_playbook.evals.loader``."""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent_playbook.evals.loader import (
    discover_eval_task_dirs,
    load_eval_task_from_dir,
)
from coding_agent_playbook.evals.task import EvalTask


_FULL_TASK_TOML = """\
id = "generate-tests-happy-path"
prompt_id = "generate-tests"
description = "Generate tests for a simple pure function with no edge cases"
version = 1

[setup]
files = ["src/calculator.py"]
project_kind = "python-application"
python_version = "3.12"
frameworks = ["pytest", "pytest-asyncio"]

[invocation]
prompt_args = "for the add function in src/calculator.py"
input_variables = { target = "src/calculator.py::add" }

[expected]
files_created = ["tests/test_calculator.py"]
files_must_contain = [
  { path = "tests/test_calculator.py", pattern = "def test_add" },
  { path = "tests/test_calculator.py", pattern = "parametrize" },
]
files_unchanged = ["src/calculator.py"]
files_forbidden = ["__pycache__/", "tests/conftest.py"]

[rubric]
criteria = [
  "Tests use pytest.parametrize for table-driven cases",
  "Test file lives at tests/test_calculator.py (mirror layout)",
  "All public branches of `add` are covered",
  "No mocking is used (function is pure)",
]
weights = [0.2, 0.2, 0.4, 0.2]
"""


def test_load_eval_task_from_dir_parses_well_formed_task(tmp_path: Path) -> None:
    task_dir = tmp_path / "generate-tests-happy-path"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(_FULL_TASK_TOML, encoding="utf-8")

    task = load_eval_task_from_dir(task_dir, source_package="coding_agent_playbook")
    assert isinstance(task, EvalTask)
    assert task.id == "generate-tests-happy-path"
    assert task.prompt_id == "generate-tests"
    assert task.source_path == task_dir / "task.toml"
    assert task.source_package == "coding_agent_playbook"
    assert task.expected is not None
    assert task.rubric is not None
    assert task.rubric.weights == [0.2, 0.2, 0.4, 0.2]


def test_load_eval_task_from_dir_raises_when_task_toml_missing(tmp_path: Path) -> None:
    empty = tmp_path / "no-toml-here"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="task.toml"):
        load_eval_task_from_dir(empty, source_package="coding_agent_playbook")


def test_load_eval_task_from_dir_raises_on_malformed_toml(tmp_path: Path) -> None:
    task_dir = tmp_path / "broken-task"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text("not = valid = toml = at = all\n", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        load_eval_task_from_dir(task_dir, source_package="coding_agent_playbook")
    assert "task.toml" in str(excinfo.value)
    assert str(task_dir) in str(excinfo.value)


def test_load_eval_task_from_dir_raises_with_path_on_schema_violation(tmp_path: Path) -> None:
    task_dir = tmp_path / "missing-fields"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text(
        'description = "no id, no prompt_id"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError) as excinfo:
        load_eval_task_from_dir(task_dir, source_package="coding_agent_playbook")
    assert str(task_dir / "task.toml") in str(excinfo.value)


def test_discover_eval_task_dirs_walks_eval_tasks_subtree(tmp_path: Path) -> None:
    base = tmp_path / "eval_tasks"
    base.mkdir()
    for name in ("task-a", "task-b"):
        d = base / name
        d.mkdir()
        (d / "task.toml").write_text(f'id = "{name}"\n', encoding="utf-8")

    discovered = list(discover_eval_task_dirs(base))
    assert [d.name for d in discovered] == ["task-a", "task-b"]


def test_discover_eval_task_dirs_skips_dirs_without_task_toml(tmp_path: Path) -> None:
    base = tmp_path / "eval_tasks"
    base.mkdir()
    (base / "empty-dir").mkdir()
    real = base / "real-task"
    real.mkdir()
    (real / "task.toml").write_text('id = "real"\n', encoding="utf-8")

    discovered = list(discover_eval_task_dirs(base))
    assert [d.name for d in discovered] == ["real-task"]


def test_discover_eval_task_dirs_skips_dot_prefixed_dirs(tmp_path: Path) -> None:
    base = tmp_path / "eval_tasks"
    base.mkdir()
    hidden = base / ".cache"
    hidden.mkdir()
    (hidden / "task.toml").write_text('id = "hidden"\n', encoding="utf-8")

    discovered = list(discover_eval_task_dirs(base))
    assert discovered == []


def test_discover_eval_task_dirs_handles_nonexistent_root(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    discovered = list(discover_eval_task_dirs(missing))
    assert discovered == []
