"""Eval-task validator. Enforces the five rules in SPEC §15.2.

Run by :mod:`coding_agent_playbook.commands.validate` to catch authoring
mistakes at commit time. Each violation is aggregated; callers print them in
order and exit non-zero if the list is non-empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.task import EvalTask
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

    The five rules:

    1. Each ``task.toml`` is well-formed — enforced upstream by the loader;
       a task object reaching the validator has already passed parsing.
    2. Each task's ``setup.files`` must exist under ``<task_dir>/setup/``.
    3. Each task's ``prompt_id`` resolves to a known prompt.
    4. Each task is listed in its referenced prompt's ``eval_tasks:``
       frontmatter (bi-directional symmetry).
    5. Weights, if present, sum to ``1.0 ± 0.001`` — enforced upstream by
       :meth:`EvalTask.from_dict` at load time; the validator does not
       re-check (locked by ``test_validate_tasks_does_not_recheck_weights``).

    Aggregates every violation; never raises. Empty list means OK.
    """
    errors: list[EvalValidationError] = []
    prompts_by_id = {p.frontmatter.id: p for p in prompts}

    for task in tasks:
        # Rule 2: setup.files must exist relative to <task_dir>/setup/.
        task_dir = task.source_path.parent
        setup_root = task_dir / "setup"
        for declared in task.setup.files:
            absolute = setup_root / declared
            if not absolute.is_file():
                errors.append(
                    EvalValidationError(
                        path=task.source_path,
                        message=(
                            f"setup.files declares {declared} but {absolute} not found"
                        ),
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

    return errors
