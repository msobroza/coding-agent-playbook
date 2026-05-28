"""Eval-task subsystem (SPEC §15).

Tier 0 active in v1; runner/judge land in v2 (see
:mod:`coding_agent_playbook.evals.runner` and
:mod:`coding_agent_playbook.evals.judge` for the placeholder ABCs).

The names re-exported here are the public surface that overlay authors and
tooling should import:

- The canonical dataclasses: :class:`EvalTask`, :class:`TaskSetup`,
  :class:`TaskInvocation`, :class:`ExpectedOutcome`, :class:`Rubric`.
- The loader entry points: :func:`load_eval_task_from_dir` and
  :func:`discover_eval_task_dirs`.
- The validator: :func:`validate_tasks` plus the
  :class:`EvalValidationError` it returns.
"""

from coding_agent_playbook.evals.loader import (
    discover_eval_task_dirs,
    load_eval_task_from_dir,
)
from coding_agent_playbook.evals.task import (
    EvalTask,
    ExpectedOutcome,
    Rubric,
    TaskInvocation,
    TaskSetup,
)
from coding_agent_playbook.evals.validator import EvalValidationError, validate_tasks

__all__ = [
    "EvalTask",
    "EvalValidationError",
    "ExpectedOutcome",
    "Rubric",
    "TaskInvocation",
    "TaskSetup",
    "discover_eval_task_dirs",
    "load_eval_task_from_dir",
    "validate_tasks",
]
