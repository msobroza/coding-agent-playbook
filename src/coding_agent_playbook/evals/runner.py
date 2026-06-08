"""v2 placeholder: ``HarnessRunner`` ABC + result dataclasses (SPEC §15.3).

These ABCs reserve the v2 surface so third-party packages can declare
``coding_agent_playbook.runners`` entry points today, and so the
:mod:`coding_agent_playbook.evals` module layout doesn't change between v1
and v2 (SPEC §15.4).

Any subclass that actually invokes ``run_task`` before v2 ships will hit a
:exc:`NotImplementedError` carrying a pointer back to SPEC §15.3.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.task import EvalTask


_V2_POINTER = (
    "HarnessRunner.run_task is a v2 placeholder. See SPEC.md §15.3 for the "
    "expected concrete implementations (ClaudeCodeRunner, ContinueCLIRunner, "
    "OpenCodeRunner)."
)


@dataclass
class CheckResult:
    """One programmatic check outcome (e.g. ``files_must_contain[0]``)."""

    name: str
    passed: bool
    detail: str


@dataclass
class TaskResult:
    """Per-task outcome across all checks and (Tier 2) rubric scoring."""

    task_id: str
    harness: str
    programmatic_checks: list[CheckResult]
    rubric_scores: list[float] | None
    aggregate_score: float
    passed: bool
    duration_seconds: float
    transcript: str


@dataclass
class EvalReport:
    """The full report emitted by a v2 ``playbook eval --harness <name>`` run."""

    engine_version: str
    harness: str
    task_results: list[TaskResult]
    aggregate_pass_rate: float
    timestamp: str


class HarnessRunner(ABC):
    """Invokes an agent for a single task against a specific harness.

    Concrete v2 implementations expected:

    - ``ClaudeCodeRunner`` — Claude Code SDK with a working-dir-bound session.
    - ``ContinueCLIRunner`` — invokes ``cn -p --prompt``.
    - ``OpenCodeRunner`` — invokes ``opencode`` CLI.
    """

    name: str

    @abstractmethod
    def run_task(self, task: EvalTask, scratch_dir: Path) -> TaskResult:
        """Execute the task against this runner's agent and return a result.

        v2 will:

        1. Copy ``task.setup.files`` into ``scratch_dir``.
        2. Mock detector facts using ``task.setup`` so framework-conditional
           prompts evaluate consistently.
        3. Render the prompt referenced by ``task.prompt_id``.
        4. Invoke the agent loop with that prompt + ``task.invocation``.
        5. Run programmatic checks against ``scratch_dir`` state.
        6. (Tier 2) Score the rubric via :class:`Judge`.
        7. Return the assembled :class:`TaskResult`.
        """
        raise NotImplementedError(_V2_POINTER)
