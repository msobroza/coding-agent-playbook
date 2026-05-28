"""Tests for ``coding_agent_playbook.evals.validator``.

Each of the five SPEC §15.2 rules has a passing case and a failing case.
"""

from __future__ import annotations

from pathlib import Path

from coding_agent_playbook.evals.task import EvalTask, TaskSetup
from coding_agent_playbook.evals.validator import (
    EvalValidationError,
    validate_tasks,
)
from coding_agent_playbook.types import Prompt, PromptFrontmatter


def _make_prompt(prompt_id: str, eval_tasks: list[str] | None = None) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=prompt_id,
            name=prompt_id.title(),
            description="prompt",
            slash=prompt_id,
            eval_tasks=eval_tasks or [],
        ),
        body="body\n",
        template_body="body\n",
        is_templated=False,
        source_path=None,
        source_package="<test>",
    )


def _make_task(
    *,
    task_id: str,
    prompt_id: str,
    task_dir: Path,
    setup_files: list[str] | None = None,
) -> EvalTask:
    return EvalTask(
        id=task_id,
        prompt_id=prompt_id,
        description="a task",
        source_path=task_dir / "task.toml",
        source_package="<test>",
        setup=TaskSetup(files=[Path(p) for p in (setup_files or [])]),
    )


# Rule 1: well-formed tasks pass the validator unchanged.
def test_validate_tasks_skips_malformed(tmp_path: Path) -> None:
    """Loader rejects malformed task.toml before the validator runs; a
    well-formed EvalTask instance passes without spurious errors."""
    task_dir = tmp_path / "ok-task"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text("placeholder\n", encoding="utf-8")
    prompt = _make_prompt("demo", eval_tasks=["ok-task"])
    task = _make_task(task_id="ok-task", prompt_id="demo", task_dir=task_dir)
    errors = validate_tasks([task], [prompt])
    assert errors == []


# Rule 2 (positive): setup.files entries that exist in setup/ → no error.
def test_validate_tasks_passes_when_setup_files_present(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-1"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text("placeholder\n", encoding="utf-8")
    setup_dir = task_dir / "setup"
    (setup_dir / "src").mkdir(parents=True)
    (setup_dir / "src" / "calculator.py").write_text("def add(a, b): return a + b\n")

    prompt = _make_prompt("demo", eval_tasks=["task-1"])
    task = _make_task(
        task_id="task-1",
        prompt_id="demo",
        task_dir=task_dir,
        setup_files=["src/calculator.py"],
    )
    errors = validate_tasks([task], [prompt])
    assert errors == []


# Rule 2 (negative): setup.files declares a file not in setup/ → error.
def test_validate_tasks_flags_missing_setup_file(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-2"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text("placeholder\n", encoding="utf-8")
    # Note: no setup/ directory created at all.

    prompt = _make_prompt("demo", eval_tasks=["task-2"])
    task = _make_task(
        task_id="task-2",
        prompt_id="demo",
        task_dir=task_dir,
        setup_files=["src/missing.py"],
    )
    errors = validate_tasks([task], [prompt])
    assert any(
        isinstance(e, EvalValidationError)
        and "setup.files" in e.message
        and "src/missing.py" in e.message
        for e in errors
    )


# Rule 3 (positive): prompt_id resolves → no error.
def test_validate_tasks_passes_when_prompt_id_exists(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-3"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["task-3"])
    task = _make_task(task_id="task-3", prompt_id="demo", task_dir=task_dir)
    errors = validate_tasks([task], [prompt])
    assert errors == []


# Rule 3 (negative): unknown prompt_id → error.
def test_validate_tasks_flags_unknown_prompt_id(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-4"
    task_dir.mkdir()
    task = _make_task(task_id="task-4", prompt_id="missing", task_dir=task_dir)
    errors = validate_tasks([task], [])
    assert any(
        "prompt_id" in e.message and "missing" in e.message for e in errors
    )


# Rule 4 (positive): prompt's eval_tasks lists the task id → no error.
def test_validate_tasks_passes_when_prompt_back_references_task(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-5"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["task-5"])
    task = _make_task(task_id="task-5", prompt_id="demo", task_dir=task_dir)
    errors = validate_tasks([task], [prompt])
    assert errors == []


# Rule 4 (negative): prompt's eval_tasks omits the task id → error.
def test_validate_tasks_flags_prompt_missing_back_reference(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-6"
    task_dir.mkdir()
    prompt = _make_prompt("foo", eval_tasks=[])  # eval_tasks is empty
    task = _make_task(task_id="foo-happy-path", prompt_id="foo", task_dir=task_dir)
    errors = validate_tasks([task], [prompt])
    assert any(
        "foo" in e.message
        and "foo-happy-path" in e.message
        and "eval_tasks" in e.message
        for e in errors
    )


# Rule 5: weights are validated at load time, not by the validator.
def test_validate_tasks_does_not_recheck_weights(tmp_path: Path) -> None:
    """Weights sum is enforced in :meth:`EvalTask.from_dict`; the validator
    must not re-check it. Locks the contract so misbalanced rubrics that
    somehow made it past the loader (e.g. an in-Python construction) don't
    fail validation with a misleading message."""
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "task-7"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["task-7"])
    task = _make_task(task_id="task-7", prompt_id="demo", task_dir=task_dir)
    # Bypass from_dict; assign a Rubric with weights that DON'T sum to 1.
    task.rubric = Rubric(criteria=["A"], weights=[0.5])  # sum=0.5
    errors = validate_tasks([task], [prompt])
    assert all("weight" not in e.message.lower() for e in errors)


# Rule 5 (positive): prompt's eval_tasks references all resolve.
def test_validate_tasks_passes_when_prompt_to_task_refs_resolve(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-8"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["task-8"])
    task = _make_task(task_id="task-8", prompt_id="demo", task_dir=task_dir)
    errors = validate_tasks([task], [prompt])
    assert errors == []


# Rule 5 (negative): prompt declares an eval_task that doesn't exist on-disk.
def test_validate_tasks_flags_prompt_referencing_missing_task(tmp_path: Path) -> None:
    prompt = _make_prompt("demo", eval_tasks=["missing-task"])
    errors = validate_tasks([], [prompt])
    assert any(
        "missing-task" in e.message and "not found" in e.message for e in errors
    )


def test_validate_tasks_aggregates_multiple_errors(tmp_path: Path) -> None:
    """The validator collects every violation rather than bailing on the first."""
    task_dir = tmp_path / "bad-task"
    task_dir.mkdir()
    task = _make_task(
        task_id="bad-task",
        prompt_id="nobody-home",
        task_dir=task_dir,
        setup_files=["src/ghost.py"],
    )
    errors = validate_tasks([task], [])
    # Expect two: setup.files miss + prompt_id miss. (Rule 4 short-circuits
    # since the prompt is missing entirely.)
    assert len(errors) >= 2
