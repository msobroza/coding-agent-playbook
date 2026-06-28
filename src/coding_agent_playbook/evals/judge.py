"""``Judge`` ABC + the opt-in ``LLMJudge`` for Tier 2 rubric scoring (SPEC §15.3).

R2 activation of the former v2 placeholder. The interface is **Option A**: the
per-criterion primitive :meth:`Judge.score_criterion` is canonical (returns one
``0-1`` score for a criterion against an artifact, averaging ``n`` samples) and
the batch :meth:`Judge.score` is a thin wrapper that maps it over a
:class:`~coding_agent_playbook.evals.task.Rubric`'s criteria.

:class:`JudgedCriterion` (``evaluators/judged.py``) calls ``score_criterion``
directly through the structural :class:`~coding_agent_playbook.evaluators.types.JudgeLike`
protocol, so ``evaluators`` never imports ``evals`` (no cycle). A concrete
``Judge`` satisfies ``JudgeLike`` structurally.

Two concrete judges:

- :class:`LLMJudge` (``name="llm"``) — shells out to the ``claude`` CLI with a
  fixed grading prompt that embeds the criterion + artifact and asks for a single
  ``0-1`` score. Opt-in, ``available()``-gated on the binary being on ``PATH``,
  configurable command, **never exercised in CI** (its real test is env-gated).
  Registered under the ``coding_agent_playbook.judges`` entry-point group.
- :class:`StubJudge` (not registered) — deterministic, dict-backed; drives every
  judged unit test hermetically.

"Deterministic-only" is simply *no judge configured* (``ctx.judge is None`` ⇒
``JudgedCriterion.available()`` is ``False``); there is no ``ProgrammaticOnlyJudge``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.evals.task import Rubric


class Judge(ABC):
    """Scores rubric criteria into ``0-1`` SCOREs. Tier 2 (SPEC §15.3).

    Subclasses set the class attribute :attr:`name` (the
    ``coding_agent_playbook.judges`` entry-point key) and implement the single
    abstract primitive :meth:`score_criterion`. :meth:`score` is concrete (the
    batch wrapper) and :meth:`available` defaults to ``True`` (real judges
    override it to guard on an external dependency).
    """

    name: str

    @classmethod
    def available(cls) -> bool:
        """Whether this judge can run here. Real judges override (e.g.
        :func:`shutil.which` on a CLI); the default is always-available."""
        return True

    @abstractmethod
    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
        """Score ``criterion`` against ``artifact`` as a ``0-1`` float.

        ``n`` (``>= 1``) is the number of independent samples to draw and average
        (LLM judges are stochastic). Implementations clamp the result to
        ``[0, 1]``.
        """

    def score(
        self,
        rubric: Rubric,
        transcript: str,
        scratch_dir_state: dict[str, Any],
    ) -> list[float]:
        """Batch sugar: one :meth:`score_criterion` per criterion (``n=1``).

        Returns a score per criterion in :attr:`Rubric.criteria`, matching order.
        ``scratch_dir_state`` is accepted for the v2-shaped signature but the
        artifact handed to the per-criterion primitive is ``transcript``.
        """
        return [self.score_criterion(c, transcript, n=1) for c in rubric.criteria]


#: Name of the Claude executable looked up on ``PATH`` by :class:`LLMJudge`.
_CLI = "claude"

#: Placeholder token in a command template, replaced by the grading prompt.
_PROMPT_TOKEN = "{prompt}"

#: Default command: the ``claude`` CLI in non-interactive print mode. The bare
#: ``{prompt}`` token is interpolated with the grading prompt per invocation.
_DEFAULT_COMMAND: tuple[str, ...] = (_CLI, "-p", _PROMPT_TOKEN)

#: Default wall-clock bound (seconds) for one grading invocation.
_DEFAULT_TIMEOUT = 120.0

#: The fixed grading prompt. ``{criterion}``/``{artifact}`` are filled per call;
#: the judge is told to emit a single bare ``0-1`` float so parsing stays robust.
_GRADING_PROMPT = (
    "You are grading whether an artifact satisfies a single rubric criterion.\n"
    "Criterion: {criterion}\n"
    "Artifact:\n"
    "<<<ARTIFACT\n"
    "{artifact}\n"
    "ARTIFACT\n\n"
    "Respond with ONLY a single number between 0 and 1 (inclusive) representing "
    "how well the artifact satisfies the criterion (1 = fully satisfied, 0 = not "
    "at all). Output just the number, no words."
)

#: Matches the first float (incl. leading sign / decimals) anywhere in stdout.
_SCORE_RE = re.compile(r"[-+]?\d*\.?\d+")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def parse_score(text: str) -> float:
    """Pull the first numeric token out of ``text`` and clamp it to ``[0, 1]``.

    Robust to an LLM that prefixes/suffixes prose around the number (e.g.
    ``"Score: 0.8"``). Returns ``0.0`` when no number is present so a degenerate
    judge response grades as a hard miss rather than crashing.
    """
    match = _SCORE_RE.search(text)
    if match is None:
        return 0.0
    try:
        return _clamp01(float(match.group()))
    except ValueError:  # pragma: no cover - the regex only matches valid floats
        return 0.0


class LLMJudge(Judge):
    """A :class:`Judge` that grades by shelling out to the ``claude`` CLI.

    ``command`` is the arg-list template used to spawn the judge; a single
    ``{prompt}`` token (anywhere in the list) is replaced by the rendered grading
    prompt. When the template contains no token, the prompt is appended as a
    trailing argument so a custom command still receives it. ``timeout`` bounds
    each invocation.

    Opt-in and **never run in CI**: no top-level import needs the CLI, the
    executable is discovered at call time, and :meth:`available` is ``False`` when
    it is absent so callers skip it cleanly.
    """

    name = "llm"

    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._command: tuple[str, ...] = tuple(command) if command is not None else _DEFAULT_COMMAND
        self._timeout = timeout

    @classmethod
    def available(cls) -> bool:
        """``True`` when the ``claude`` executable is on ``PATH``."""
        return shutil.which(_CLI) is not None

    def _build_command(self, prompt: str) -> list[str]:
        """Interpolate ``prompt`` into the configured command template.

        Each ``{prompt}`` token is replaced by the prompt; if the template has no
        token, the prompt is appended as a final argument.
        """
        if any(_PROMPT_TOKEN in part for part in self._command):
            return [part.replace(_PROMPT_TOKEN, prompt) for part in self._command]
        return [*self._command, prompt]

    def _grade_once(self, criterion: str, artifact: Any) -> float:
        """Run one grading invocation and parse its ``0-1`` score from stdout."""
        prompt = _GRADING_PROMPT.format(criterion=criterion, artifact=str(artifact))
        completed = subprocess.run(
            self._build_command(prompt),
            capture_output=True,
            text=True,
            timeout=self._timeout,
            check=False,
        )
        return parse_score(completed.stdout)

    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
        """Average ``n`` independent CLI gradings of ``criterion`` over ``artifact``."""
        samples = max(1, n)
        total = sum(self._grade_once(criterion, artifact) for _ in range(samples))
        return total / samples


class StubJudge(Judge):
    """A deterministic, dict-backed :class:`Judge` for hermetic tests (unregistered).

    ``scores`` maps a criterion string to its fixed ``0-1`` score; any criterion
    not in the map gets ``default`` (``1.0``). ``score_criterion`` ignores the
    artifact and returns the mapped score regardless of ``n`` (it is already
    deterministic), but records every call so tests can assert what was asked.
    """

    name = "stub"

    def __init__(self, scores: dict[str, float] | None = None, *, default: float = 1.0) -> None:
        self._scores = dict(scores or {})
        self._default = default
        self.calls: list[tuple[str, Any, int]] = []

    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
        self.calls.append((criterion, artifact, n))
        return _clamp01(self._scores.get(criterion, self._default))
