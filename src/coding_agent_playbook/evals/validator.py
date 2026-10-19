"""Eval-task validator. Enforces the SPEC §15.2 structural rules.

Run by :mod:`coding_agent_playbook.commands.validate` to catch authoring mistakes
at commit time. Each violation is aggregated; callers print them in order and exit
non-zero if the list is non-empty.

The schema rules (``[gate]``/``[rubric]``/``[verdict]``) are checked by **trial-
compiling** the task via :func:`~coding_agent_playbook.evals.task.compile_eval_task`
and turning any :exc:`ValueError` / :exc:`KeyError` (incl.
:exc:`~coding_agent_playbook.evals.compile._expr.ExprError`, a ``ValueError`` subclass) into
an :class:`EvalValidationError`. The compiler already validates: at-least-one
layer present, unknown check ids / metric names / gate-refs / rubric-refs,
malformed handle bindings, expression identifiers ⊄ bind keys, the rubric
weight-sum, and verdict identifiers ⊄ present layers. The non-schema rules
(setup.files exist, an authored ``setup/pyproject.toml`` parses, prompt_id
resolves, prompt↔task back-reference symmetry) and a light ``[aggregate]``
shape check are kept here.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.types import Prompt

#: The aggregate handle ``metric`` axis the multi-trial layer recognizes.
_AGGREGATE_METRICS = frozenset({"pass_at_k", "pass_pow_k"})

#: The aggregate ``over`` axis a handle may reduce.
_AGGREGATE_OVER = frozenset({"gate", "rubric", "verdict"})


@dataclass(frozen=True)
class EvalValidationError:
    """One validation failure. ``path`` points at the offending ``task.toml``."""

    path: Path
    message: str


def validate_tasks(
    tasks: list[EvalTask],
    prompts: list[Prompt],
) -> list[EvalValidationError]:
    """Run the SPEC §15.2 checks against the loaded task + prompt lists.

    The rules:

    1. Each ``task.toml`` is well-formed — enforced upstream by the loader;
       a task object reaching the validator has already passed parsing.
    2. The ``[gate]``/``[rubric]``/``[verdict]`` schema compiles cleanly —
       trial-compile via :func:`compile_eval_task`, surfacing any compiler fault
       (unknown check/metric/ref, malformed binding, expr idents ⊄ bind keys,
       rubric weight-sum, verdict idents ⊄ present layers, no layer at all).
    3. A light ``[aggregate]`` shape check (each handle names a known aggregate
       ``metric``, an integer ``k >= 1``, and an ``over`` axis); the multi-trial
       grading itself runs in the runner.
    4. Each task's ``setup.files`` must exist under ``<task_dir>/setup/``.
       When ``setup/pyproject.toml`` is present it must parse as TOML; dep
       installability is the runner's concern (``uv sync``), not the validator's.
    5. Each task's ``prompt_id`` resolves to a known prompt.
    6. Each task is listed in its referenced prompt's ``eval_tasks:`` frontmatter
       (task → prompt direction of the symmetry check).
    7. Each prompt's ``eval_tasks:`` references an on-disk task (prompt → task
       direction, per SPEC §6.5.5 rule 1).

    Aggregates every violation; never raises. Empty list means OK.
    """
    errors: list[EvalValidationError] = []
    prompts_by_id = {p.frontmatter.id: p for p in prompts}
    tasks_by_id = {t.id: t for t in tasks}

    for task in tasks:
        # Rule 2: the gate/rubric/verdict schema must compile.
        errors.extend(_validate_schema(task))

        # Rule 3: light [aggregate] shape checks (multi-trial grading runs in the runner).
        if task.aggregate is not None:
            errors.extend(_validate_aggregate(task))

        # Rule 4: setup.files must exist relative to <task_dir>/setup/, and an
        # authored setup/pyproject.toml must parse as TOML. The runner installs
        # its deps via ``uv sync``; installability is not validated here.
        task_dir = task.source_path.parent
        setup_root = task_dir / "setup"
        for declared in task.setup.files:
            absolute = setup_root / declared
            if not absolute.is_file():
                errors.append(
                    EvalValidationError(
                        path=task.source_path,
                        message=(f"setup.files declares {declared} but {absolute} not found"),
                    )
                )
        pyproject = setup_root / "pyproject.toml"
        if pyproject.is_file():
            try:
                tomllib.loads(pyproject.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                errors.append(
                    EvalValidationError(
                        path=task.source_path,
                        message=f"setup/pyproject.toml is not valid TOML: {exc}",
                    )
                )

        # Rule 5: prompt_id must resolve to a known prompt.
        prompt = prompts_by_id.get(task.prompt_id)
        if prompt is None:
            errors.append(
                EvalValidationError(
                    path=task.source_path,
                    message=f"prompt_id {task.prompt_id!r} does not exist",
                )
            )
            # Rule 6 only meaningful when the prompt exists — skip the
            # back-reference check to avoid a confusing follow-on error.
            continue

        # Rule 6: the prompt's eval_tasks: frontmatter must list this task.
        prompt_eval_tasks = prompt.frontmatter.eval_tasks or []
        if task.id not in prompt_eval_tasks:
            errors.append(
                EvalValidationError(
                    path=task.source_path,
                    message=(
                        f"prompt {task.prompt_id!r} does not list eval_task "
                        f"{task.id!r} in its eval_tasks: frontmatter"
                    ),
                )
            )

    # Rule 7 (prompt → task direction): every eval_tasks: reference must
    # resolve to an on-disk task. Catches the case where a task was renamed
    # or deleted but its prompt still references it.
    for prompt in prompts:
        for declared_id in prompt.frontmatter.eval_tasks or []:
            if declared_id not in tasks_by_id:
                # Anchor the error at the prompt's source so users jump to
                # the prompt frontmatter to fix the dangling reference.
                anchor_path = prompt.source_path or Path(prompt.frontmatter.id)
                errors.append(
                    EvalValidationError(
                        path=anchor_path,
                        message=(
                            f"declares eval_task {declared_id!r} but "
                            f"eval_tasks/{declared_id}/ not found"
                        ),
                    )
                )

    return errors


def _validate_schema(task: EvalTask) -> list[EvalValidationError]:
    """Trial-compile the task; turn any compiler fault into a validation error.

    :func:`compile_eval_task` raises :exc:`ValueError` (incl.
    :exc:`~coding_agent_playbook.evals.compile._expr.ExprError`) or :exc:`KeyError` on any
    structural fault. A clean compile means the gate/rubric/verdict schema is
    well-formed. Imported lazily so the validator module stays import-light and
    free of any eval ↔ evaluator import cycle at module load.
    """
    from coding_agent_playbook.evals.task import compile_eval_task

    try:
        compile_eval_task(task)
    except (ValueError, KeyError) as exc:
        # KeyError's str() carries surrounding quotes; strip them for a clean message.
        detail = str(exc).strip("'\"") if isinstance(exc, KeyError) else str(exc)
        return [EvalValidationError(path=task.source_path, message=detail)]
    return []


def _validate_aggregate(task: EvalTask) -> list[EvalValidationError]:
    """Light shape check of the ``[aggregate.bind]`` handles (grading runs in the runner).

    Each aggregate handle must name a known ``metric`` (``pass_at_k`` /
    ``pass_pow_k``), an integer ``k >= 1``, and an ``over`` axis in
    ``{"gate", "rubric", "verdict"}``. Aggregates every violation; never raises.
    """
    aggregate = task.aggregate
    assert aggregate is not None  # caller guards; narrows for mypy.
    errors: list[EvalValidationError] = []

    for name, handle in aggregate.bind.items():
        metric = handle.get("metric")
        if metric not in _AGGREGATE_METRICS:
            errors.append(
                EvalValidationError(
                    path=task.source_path,
                    message=(
                        f"[aggregate.bind.{name}] metric {metric!r} is invalid; "
                        f"must be one of {', '.join(sorted(_AGGREGATE_METRICS))}"
                    ),
                )
            )
        k = handle.get("k")
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            errors.append(
                EvalValidationError(
                    path=task.source_path,
                    message=f"[aggregate.bind.{name}] k must be an integer >= 1, got {k!r}",
                )
            )
        over = handle.get("over")
        if over not in _AGGREGATE_OVER:
            errors.append(
                EvalValidationError(
                    path=task.source_path,
                    message=(
                        f"[aggregate.bind.{name}] over {over!r} is invalid; "
                        f"must be one of {', '.join(sorted(_AGGREGATE_OVER))}"
                    ),
                )
            )

    return errors
