"""v2 placeholder: ``Judge`` ABC for Tier 2 rubric scoring (SPEC §15.3).

Concrete v2 implementations expected:

- ``LLMJudge`` — strong model (Sonnet or Opus) with a fixed grading prompt
  and a calibration set.
- ``ProgrammaticOnlyJudge`` — Tier 1 fallback that returns ``[]`` so
  aggregate scoring falls back to programmatic checks only.

Lives in v1's tree purely to lock the module layout (SPEC §15.4); any call
to :meth:`Judge.score` before v2 raises :exc:`NotImplementedError`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook.evals.task import Rubric


_V2_POINTER = (
    "Judge.score is a v2 placeholder. See SPEC.md §15.3 for the expected "
    "concrete implementations (LLMJudge, ProgrammaticOnlyJudge)."
)


class Judge(ABC):
    """Scores a rubric. Tier 2."""

    name: str

    @abstractmethod
    def score(
        self,
        rubric: Rubric,
        transcript: str,
        scratch_dir_state: dict[str, str],
    ) -> list[float]:
        """Return a score in ``[0, 1]`` for each criterion in
        :attr:`Rubric.criteria`, in matching order."""
        raise NotImplementedError(_V2_POINTER)
