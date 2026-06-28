"""Eval-task validator. Enforces the five rules in SPEC §15.2.

Run by :mod:`coding_agent_playbook.commands.validate` to catch authoring
mistakes at commit time. Each violation is aggregated; callers print them in
order and exit non-zero if the list is non-empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_args

if TYPE_CHECKING:
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.evaluators.types import Mode
    from coding_agent_playbook.types import Prompt


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
    2. Each task's ``setup.files`` must exist under ``<task_dir>/setup/``.
    3. Each task's ``prompt_id`` resolves to a known prompt.
    4. Each task is listed in its referenced prompt's ``eval_tasks:``
       frontmatter (task → prompt direction of the symmetry check).
    5. Each prompt's ``eval_tasks:`` references an on-disk task
       (prompt → task direction, per SPEC §6.5.5 rule 1).
    6. Weights, if present, sum to ``1.0 ± 0.001`` — enforced upstream by
       :meth:`EvalTask.from_dict` at load time; the validator does not
       re-check (locked by ``test_validate_tasks_does_not_recheck_weights``).
    7. The ``[metrics]`` block (SPEC prM §D), if present, is well-formed: a
       valid ``mode``, every named evaluator is registered (static or
       execution), and all bounds/deltas/weights are numbers.
    8. The ``[rubric]`` block, if present, is well-formed: a ``ref`` resolves to
       a registered named rubric, and ``ref``/``criteria`` are not both set (nor
       both absent). The mutual-exclusion cases also raise at parse time; the
       validator mirrors them so a directly-built task still surfaces them.

    Aggregates every violation; never raises. Empty list means OK.
    """
    errors: list[EvalValidationError] = []
    prompts_by_id = {p.frontmatter.id: p for p in prompts}
    tasks_by_id = {t.id: t for t in tasks}

    for task in tasks:
        # Rule 7: validate the [metrics] block when present.
        if task.metrics is not None:
            errors.extend(_validate_metrics(task))

        # Rule 8: validate the [rubric] block when present (ref resolves to a
        # registered rubric; ref/criteria mutual-exclusion).
        if task.rubric is not None:
            errors.extend(_validate_rubric(task))

        # Rule 2: setup.files must exist relative to <task_dir>/setup/.
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

        # Rule 3: prompt_id must resolve to a known prompt.
        prompt = prompts_by_id.get(task.prompt_id)
        if prompt is None:
            errors.append(
                EvalValidationError(
                    path=task.source_path,
                    message=f"prompt_id {task.prompt_id!r} does not exist",
                )
            )
            # Rule 4 only meaningful when the prompt exists — skip the
            # back-reference check to avoid a confusing follow-on error.
            continue

        # Rule 4: the prompt's eval_tasks: frontmatter must list this task.
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

    # Rule 5 (prompt → task direction): every eval_tasks: reference must
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


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_metrics(task: EvalTask) -> list[EvalValidationError]:
    """Validate a task's ``[metrics]`` block (SPEC prM §D).

    Checks the ``mode`` is one of ``regression``/``absolute``/``both``; that
    every metric named in ``thresholds``/``regression``/``weights`` is a known
    registered metric (static **or** execution, e.g. ``coverage`` /
    ``test_pass_rate``); and that all bounds, regression deltas, and weights are
    numbers. Aggregates every violation; never raises.
    """
    # Imported lazily so the validator module stays import-light and free of any
    # eval ↔ evaluator import cycle at module load.
    from coding_agent_playbook.evaluators.metric import all_metrics
    from coding_agent_playbook.evaluators.types import Mode

    metrics = task.metrics
    assert metrics is not None  # caller guards; narrows the type for mypy.
    errors: list[EvalValidationError] = []

    valid_modes: tuple[Mode, ...] = get_args(Mode)
    if metrics.mode not in valid_modes:
        errors.append(
            EvalValidationError(
                path=task.source_path,
                message=(
                    f"[metrics].mode {metrics.mode!r} is invalid; "
                    f"must be one of {', '.join(valid_modes)}"
                ),
            )
        )

    known = {m.name for m in all_metrics()}

    def _check_name(name: str) -> None:
        if name not in known:
            errors.append(
                EvalValidationError(
                    path=task.source_path,
                    message=f"[metrics] names unknown evaluator {name!r}",
                )
            )

    def _check_number(name: str, label: str, value: Any) -> None:
        if value is None:
            return
        if not _is_number(value):
            errors.append(
                EvalValidationError(
                    path=task.source_path,
                    message=f"[metrics] {label} for {name!r} must be numeric, got {value!r}",
                )
            )

    for name, threshold in metrics.thresholds.items():
        _check_name(name)
        _check_number(name, "thresholds.warn", threshold.warn)
        _check_number(name, "thresholds.fail", threshold.fail)

    for name, policy in metrics.regression.items():
        _check_name(name)
        _check_number(name, "regression.max_worsening", policy.max_worsening)

    for name, weight in metrics.weights.items():
        _check_name(name)
        _check_number(name, "weights", weight)

    return errors


def _validate_rubric(task: EvalTask) -> list[EvalValidationError]:
    """Validate a task's ``[rubric]`` block (named-rubric registry).

    When ``[rubric] ref`` is set, the named rubric must be registered (in the
    :mod:`coding_agent_playbook.evaluators.rubrics` registry). The
    ref/criteria mutual-exclusion and neither-set cases already raise at parse
    time (:func:`coding_agent_playbook.evals.task._parse_rubric`); they are
    mirrored here defensively so a task object built directly (not via
    ``from_dict``) still surfaces the same violation rather than crashing the
    compiler. Aggregates every violation; never raises.
    """
    # Imported lazily so the validator stays import-light and free of any
    # eval ↔ evaluator import cycle at module load.
    from coding_agent_playbook.evaluators.rubrics import all_rubric_names

    rubric = task.rubric
    assert rubric is not None  # caller guards; narrows the type for mypy.
    errors: list[EvalValidationError] = []

    if rubric.ref is not None and rubric.criteria:
        errors.append(
            EvalValidationError(
                path=task.source_path,
                message="[rubric] cannot set both 'ref' and 'criteria'",
            )
        )
    if rubric.ref is None and not rubric.criteria:
        errors.append(
            EvalValidationError(
                path=task.source_path,
                message="[rubric] must set either 'criteria' or 'ref'",
            )
        )

    if rubric.ref is not None:
        known = all_rubric_names()
        if rubric.ref not in known:
            errors.append(
                EvalValidationError(
                    path=task.source_path,
                    message=(
                        f"[rubric] ref {rubric.ref!r} is not a registered rubric; "
                        f"known: {sorted(known)}"
                    ),
                )
            )

    return errors
