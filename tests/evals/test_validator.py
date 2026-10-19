"""Tests for ``coding_agent_playbook.evals.validator`` (C7 compile-based rules).

The schema rules (``[gate]``/``[rubric]``/``[verdict]``) are checked by trial-
compiling the task; the non-schema rules (setup.files, prompt_id, prompt↔task
back-references) and a light ``[aggregate]`` shape check are kept. Each rule has a
passing case and a failing case.
"""

from __future__ import annotations

from pathlib import Path

from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.evals.task import EvalTask, Layer, TaskSetup, Verdict
from coding_agent_playbook.evals.validator import (
    EvalValidationError,
    validate_tasks,
)


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


def _gate(*, path: str = "x.py") -> Layer:
    """A one-handle gate that compiles cleanly (single-handle default expr)."""
    return Layer(bind={"a": {"check": "file_exists", "path": path}})


def _make_task(
    *,
    task_id: str,
    prompt_id: str,
    task_dir: Path,
    setup_files: list[str] | None = None,
    gate: Layer | None = None,
    rubric: Layer | None = None,
    verdict: str = "gate",
    aggregate: Layer | None = None,
) -> EvalTask:
    return EvalTask(
        id=task_id,
        prompt_id=prompt_id,
        description="a task",
        source_path=task_dir / "task.toml",
        source_package="<test>",
        setup=TaskSetup(files=[Path(p) for p in (setup_files or [])]),
        gate=gate if gate is not None else _gate(),
        rubric=rubric,
        verdict=Verdict(mode="boolean", trial=verdict),
        aggregate=aggregate,
    )


# Rule 1 / 2: a well-formed task (clean-compiling schema) passes.
def test_validate_tasks_passes_well_formed(tmp_path: Path) -> None:
    task_dir = tmp_path / "ok-task"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["ok-task"])
    task = _make_task(task_id="ok-task", prompt_id="demo", task_dir=task_dir)
    assert validate_tasks([task], [prompt]) == []


# Rule 2 (negative): an unknown check id surfaces as a compile error.
def test_validate_tasks_flags_unknown_check(tmp_path: Path) -> None:
    task_dir = tmp_path / "bad-check"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["bad-check"])
    task = _make_task(
        task_id="bad-check",
        prompt_id="demo",
        task_dir=task_dir,
        gate=Layer(bind={"a": {"check": "no_such_check", "path": "x"}}),
    )
    errors = validate_tasks([task], [prompt])
    assert any("no_such_check" in e.message for e in errors)


# Rule 2 (negative): a gate expr identifier not in the bind table is a compile error.
def test_validate_tasks_flags_expr_ident_not_in_bind(tmp_path: Path) -> None:
    task_dir = tmp_path / "bad-expr"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["bad-expr"])
    task = _make_task(
        task_id="bad-expr",
        prompt_id="demo",
        task_dir=task_dir,
        gate=Layer(bind={"a": {"check": "file_exists", "path": "x"}}, expr="a and ghost"),
    )
    errors = validate_tasks([task], [prompt])
    assert any("ghost" in e.message for e in errors)


# Rule 2 (negative): a verdict naming an absent layer is a compile error.
def test_validate_tasks_flags_verdict_missing_layer(tmp_path: Path) -> None:
    task_dir = tmp_path / "bad-verdict"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["bad-verdict"])
    # Default verdict mentions 'rubric' but there is no [rubric] block.
    task = _make_task(
        task_id="bad-verdict",
        prompt_id="demo",
        task_dir=task_dir,
        verdict="gate and rubric",
    )
    errors = validate_tasks([task], [prompt])
    assert any("rubric" in e.message for e in errors)


# Rule 2 (negative): a rubric group whose weights don't sum to 1.0 is a compile error.
def test_validate_tasks_flags_rubric_weight_sum(tmp_path: Path) -> None:
    task_dir = tmp_path / "bad-weights"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["bad-weights"])
    task = _make_task(
        task_id="bad-weights",
        prompt_id="demo",
        task_dir=task_dir,
        rubric=Layer(
            bind={
                "q": {
                    "fail": 0.5,
                    "rubric": [{"judge": "a", "weight": 0.3}, {"judge": "b", "weight": 0.3}],
                }
            }
        ),
        verdict="gate and rubric",
    )
    errors = validate_tasks([task], [prompt])
    assert any("weight" in e.message.lower() and "sum" in e.message.lower() for e in errors)


# Rule 2 (negative): weighted [verdict] referencing an absent layer is a compile error (C10).
def test_validate_tasks_flags_weighted_verdict_unknown_layer(tmp_path: Path) -> None:
    task_dir = tmp_path / "bad-weighted"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["bad-weighted"])
    task = EvalTask(
        id="bad-weighted",
        prompt_id="demo",
        description="d",
        source_path=task_dir / "task.toml",
        source_package="<test>",
        setup=TaskSetup(),
        gate=_gate(),
        # No [rubric] block, yet weights name it.
        verdict=Verdict(
            mode="weighted",
            weights={"gate": 0.4, "rubric": 0.6},
            fail=0.5,
        ),
    )
    errors = validate_tasks([task], [prompt])
    assert any("unknown layer" in e.message for e in errors)


# Rule 2 (negative): a task with no layer at all cannot compile.
def test_validate_tasks_flags_no_layer(tmp_path: Path) -> None:
    task_dir = tmp_path / "no-layer"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["no-layer"])
    task = EvalTask(
        id="no-layer",
        prompt_id="demo",
        description="d",
        source_path=task_dir / "task.toml",
        source_package="<test>",
        setup=TaskSetup(),
        gate=None,
        rubric=None,
        verdict=Verdict(mode="boolean", trial="gate"),
    )
    errors = validate_tasks([task], [prompt])
    assert any("at least one" in e.message for e in errors)


# Rule 3 (positive): a well-formed [aggregate] passes.
def test_validate_tasks_accepts_valid_aggregate(tmp_path: Path) -> None:
    task_dir = tmp_path / "agg-ok"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["agg-ok"])
    task = _make_task(
        task_id="agg-ok",
        prompt_id="demo",
        task_dir=task_dir,
        aggregate=Layer(bind={"r": {"metric": "pass_at_k", "k": 3, "over": "verdict"}}),
    )
    errors = validate_tasks([task], [prompt])
    assert [e for e in errors if "aggregate" in e.message.lower()] == []


# Rule 3 (negative): a bad aggregate metric / k / over is flagged.
def test_validate_tasks_flags_bad_aggregate(tmp_path: Path) -> None:
    task_dir = tmp_path / "agg-bad"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["agg-bad"])
    task = _make_task(
        task_id="agg-bad",
        prompt_id="demo",
        task_dir=task_dir,
        aggregate=Layer(bind={"r": {"metric": "nope", "k": 0, "over": "sideways"}}),
    )
    errors = validate_tasks([task], [prompt])
    msgs = " ".join(e.message for e in errors)
    assert "nope" in msgs
    assert "k must be an integer" in msgs
    assert "sideways" in msgs


# Rule 4 (positive): setup.files entries that exist in setup/ → no error.
def test_validate_tasks_passes_when_setup_files_present(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-1"
    task_dir.mkdir()
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
    assert validate_tasks([task], [prompt]) == []


# Rule 4 (negative): setup.files declares a file not in setup/ → error.
def test_validate_tasks_flags_missing_setup_file(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-2"
    task_dir.mkdir()
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


# Rule 5 (positive): prompt_id resolves → no error.
def test_validate_tasks_passes_when_prompt_id_exists(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-3"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["task-3"])
    task = _make_task(task_id="task-3", prompt_id="demo", task_dir=task_dir)
    assert validate_tasks([task], [prompt]) == []


# Rule 5 (negative): unknown prompt_id → error.
def test_validate_tasks_flags_unknown_prompt_id(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-4"
    task_dir.mkdir()
    task = _make_task(task_id="task-4", prompt_id="missing", task_dir=task_dir)
    errors = validate_tasks([task], [])
    assert any("prompt_id" in e.message and "missing" in e.message for e in errors)


# Rule 6 (positive): prompt's eval_tasks lists the task id → no error.
def test_validate_tasks_passes_when_prompt_back_references_task(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-5"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["task-5"])
    task = _make_task(task_id="task-5", prompt_id="demo", task_dir=task_dir)
    assert validate_tasks([task], [prompt]) == []


# Rule 6 (negative): prompt's eval_tasks omits the task id → error.
def test_validate_tasks_flags_prompt_missing_back_reference(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-6"
    task_dir.mkdir()
    prompt = _make_prompt("foo", eval_tasks=[])  # eval_tasks is empty
    task = _make_task(task_id="foo-happy-path", prompt_id="foo", task_dir=task_dir)
    errors = validate_tasks([task], [prompt])
    assert any(
        "foo" in e.message and "foo-happy-path" in e.message and "eval_tasks" in e.message
        for e in errors
    )


# Rule 7 (positive): prompt's eval_tasks references all resolve.
def test_validate_tasks_passes_when_prompt_to_task_refs_resolve(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-8"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["task-8"])
    task = _make_task(task_id="task-8", prompt_id="demo", task_dir=task_dir)
    assert validate_tasks([task], [prompt]) == []


# Rule 7 (negative): prompt declares an eval_task that doesn't exist on-disk.
def test_validate_tasks_flags_prompt_referencing_missing_task(tmp_path: Path) -> None:
    prompt = _make_prompt("demo", eval_tasks=["missing-task"])
    errors = validate_tasks([], [prompt])
    assert any("missing-task" in e.message and "not found" in e.message for e in errors)


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
    # Expect two: setup.files miss + prompt_id miss. (Rule 6 short-circuits
    # since the prompt is missing entirely.)
    assert len(errors) >= 2
