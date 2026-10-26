"""``Judge`` ABC + the opt-in ``LLMJudge`` for Tier 2 rubric scoring (SPEC §15.3).

R2 activation of the former v2 placeholder. The interface is **Option A**: the
per-criterion primitive :meth:`Judge.score_criterion` is canonical (returns one
``0-1`` score for a criterion against an artifact, averaging ``n`` samples) and
the batch :meth:`Judge.score` is a thin wrapper that maps it over a sequence of
criterion strings.

:class:`~coding_agent_playbook.grading.judged.JudgeCheck` calls
``score_criterion`` directly through the structural
:class:`~coding_agent_playbook.grading.types.JudgeLike` protocol, so
``grading`` never imports ``evals`` (no cycle). A concrete ``Judge`` satisfies
``JudgeLike`` structurally.

Two concrete judges:

- :class:`LLMJudge` (``name="llm"``) — shells out to the ``claude`` CLI with a
  fixed grading prompt that embeds the criterion + artifact and asks for a single
  ``0-1`` score. Opt-in, ``available()``-gated on the binary being on ``PATH``,
  configurable command, **never exercised in CI** (its real test is env-gated).
  Registered under the ``coding_agent_playbook.judges`` entry-point group.
- :class:`StubJudge` (not registered) — deterministic, dict-backed; drives every
  judged unit test hermetically.

"Deterministic-only" is simply *no judge configured* (``ctx.judge is None`` ⇒
``JudgeCheck.available()`` is ``False``); there is no ``ProgrammaticOnlyJudge``.

A judge that is configured but cannot produce a score (the CLI failed, timed out,
or answered off-format) raises :class:`JudgeError`. It never degrades to a
number: before this, ``"API Error: 529 Overloaded"`` parsed as ``529`` and
clamped to a perfect ``1.0``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evals.run.claude_code_route import routed_argv, routed_env
from coding_agent_playbook.evals.run.cli_argv import PROMPT_TOKEN, build_cli_argv

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from coding_agent_playbook.evals.run.claude_code_route import ClaudeCodeIsolation


class JudgeError(RuntimeError):
    """A configured judge could not produce a score for a criterion.

    Raised by :class:`LLMJudge` once its bounded retries are exhausted. It
    propagates out of the scoring run on purpose: an unscored rubric is neither
    a pass nor a fail, so ``playbook eval --run`` reports it as an error (exit 2).
    """


class Judge(ABC):
    """Scores rubric criteria into ``0-1`` SCOREs. Tier 2 (SPEC §15.3).

    Subclasses set the class attribute :attr:`name` (the
    ``coding_agent_playbook.judges`` entry-point key) and implement the single
    abstract primitive :meth:`score_criterion`. :meth:`score` is concrete (the
    batch wrapper) and :meth:`available` defaults to ``True`` (real judges
    override it to guard on an external dependency).
    """

    name: str
    #: Whether the constructor takes ``model=`` (``[evals.judge] model``). A judge
    #: that does not is refused when that key is set.
    accepts_model: bool = False
    #: Whether the constructor takes ``route=`` (``[evals.judge] endpoint``).
    accepts_endpoint: bool = False

    @classmethod
    def available(cls) -> bool:
        """Whether this judge can run here. Real judges override (e.g.
        :func:`shutil.which` on a CLI); the default is always-available."""
        return True

    @abstractmethod
    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
        """Score ``criterion`` against ``artifact`` as a ``0-1`` float.

        ``n`` (``>= 1``) is the number of independent samples to draw and average
        (LLM judges are stochastic). An implementation that cannot produce a real
        score — its backend failed, timed out, or answered off-format — must
        raise :class:`JudgeError` (``playbook eval --run`` reports the sample as
        unscorable, exit 2), never clamp or default the answer into a number.
        """

    def score(
        self,
        criteria: Sequence[str],
        transcript: str,
        scratch_dir_state: dict[str, Any],
    ) -> list[float]:
        """Batch sugar: one :meth:`score_criterion` per criterion (``n=1``).

        Returns a score per criterion in ``criteria``, matching order.
        ``scratch_dir_state`` is accepted for the v2-shaped signature but the
        artifact handed to the per-criterion primitive is ``transcript``.
        """
        return [self.score_criterion(c, transcript, n=1) for c in criteria]


#: Name of the Claude executable looked up on ``PATH`` by :class:`LLMJudge`.
_CLI = "claude"

#: Default command: the ``claude`` CLI in non-interactive print mode. The bare
#: ``{prompt}`` token is interpolated with the grading prompt per invocation.
_DEFAULT_COMMAND: tuple[str, ...] = (_CLI, "-p", PROMPT_TOKEN)

#: Default wall-clock bound (seconds) for one grading invocation.
_DEFAULT_TIMEOUT = 120.0

#: Default extra attempts after a failed grading invocation (3 attempts total).
_DEFAULT_RETRIES = 2

#: How much of a failed invocation's output to quote in a :class:`JudgeError`.
_OUTPUT_EXCERPT_CHARS = 200

#: The fixed grading prompt. ``{criterion}``/``{artifact}`` are filled per call;
#: the judge is told to emit a single bare ``0-1`` float so parsing stays robust.
GRADING_PROMPT = (
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

#: A whole judge answer once markdown marks are stripped: one decimal number,
#: optionally labelled ``Score:`` and followed by a full stop. Nothing else may
#: surround it — prose such as ``"retry in 1s"`` must never parse. Each run of
#: whitespace can match only one way, so a long degenerate output cannot backtrack.
_ANSWER_RE = re.compile(
    r"(?:score\s*(?:[:=]\s*)?)?(?P<number>\d+(?:\.\d*)?|\.\d+)\.?",
    re.IGNORECASE,
)

#: Markdown emphasis/code marks a judge may wrap its answer in (``**Score:** 0.8``).
_MARKDOWN_MARKS = str.maketrans("", "", "*`_")

#: A bare answer is a handful of characters; anything longer is off-format.
_MAX_ANSWER_CHARS = 32


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def parse_score(text: str) -> float | None:
    """The judge's ``0-1`` score in ``text``, or ``None`` when it is off-format.

    The whole answer must be one number in ``[0, 1]`` — the grading prompt asks
    for exactly that — tolerating only a ``Score:`` label, markdown bold/code
    marks anywhere (``**Score:** 0.8``), a trailing full stop, and surrounding
    whitespace. Anything else (prose,
    several numbers, a number out of range) is ``None``: an error message such as
    ``"API Error: 529"`` or ``"rate limited, retry in 1s"`` must never be read as
    a grade.

    Example::

        parse_score("Score: 0.8")  # 0.8
        parse_score("API Error: 529 Overloaded")  # None
    """
    answer = text.translate(_MARKDOWN_MARKS).strip()
    if len(answer) > _MAX_ANSWER_CHARS:
        return None
    match = _ANSWER_RE.fullmatch(answer)
    if match is None:
        return None
    value = float(match.group("number"))
    return value if 0.0 <= value <= 1.0 else None


def _excerpt(text: str) -> str:
    """The last :data:`_OUTPUT_EXCERPT_CHARS` of ``text``, whitespace-collapsed."""
    return " ".join(text.split())[-_OUTPUT_EXCERPT_CHARS:]


@contextmanager
def _judge_cwd(route: ClaudeCodeIsolation | None) -> Iterator[str | None]:
    """Where one grading runs: the caller's directory unrouted, else a fresh empty one.

    Why: an isolated judge has an empty config dir, but Claude Code still reads
    project and local settings (``CLAUDE.md``, ``CLAUDE.local.md``,
    ``.claude/settings*.json``) from its working directory and the parents; an
    empty directory under the system temp dir, outside any repository, has none.

    Example::

        >>> with _judge_cwd(None) as cwd:
        ...     cwd is None
        True
    """
    if route is None:
        yield None
        return
    with tempfile.TemporaryDirectory(prefix="playbook-judge-cwd-") as empty:
        yield empty


class LLMJudge(Judge):
    """A :class:`Judge` that grades by shelling out to the ``claude`` CLI.

    ``command`` is the arg-list template used to spawn the judge; a single
    ``{prompt}`` token (anywhere in the list) is replaced by the rendered grading
    prompt. When the template contains no token, the prompt is appended as a
    trailing argument so a custom command still receives it. ``timeout`` bounds
    each invocation. A failed invocation (it cannot be launched, exits non-zero,
    times out, or answers anything but one number in ``[0, 1]``) is retried up
    to ``retries`` times — immediately, with no backoff — and then raises
    :class:`JudgeError`. ``model`` (``[evals.judge] model``) is passed as
    ``--model <model>``, exactly as written; ``None`` keeps the CLI's default.
    ``route`` (``[evals.judge] endpoint``) isolates each grading and points it at
    that endpoint; under ``--record`` without an endpoint, a ``ClaudeCodeKeyRoute``
    isolates it on an API key. ``None`` keeps the CLI's own settings and login.

    Opt-in and **never run in CI**: no top-level import needs the CLI, the
    executable is discovered at call time, and :meth:`available` is ``False`` when
    it is absent so callers skip it cleanly.
    """

    name = "llm"
    accepts_model = True
    accepts_endpoint = True

    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        retries: int = _DEFAULT_RETRIES,
        model: str | None = None,
        route: ClaudeCodeIsolation | None = None,
    ) -> None:
        if retries < 0:
            raise ValueError(f"LLMJudge retries must be >= 0, got {retries}")
        if command is not None and not command:
            raise ValueError("LLMJudge command must not be empty, got []")
        self._command: tuple[str, ...] = tuple(command) if command is not None else _DEFAULT_COMMAND
        self._timeout = timeout
        self._retries = retries
        self.model = model
        self.route = route

    @classmethod
    def available(cls) -> bool:
        """``True`` when the ``claude`` executable is on ``PATH``."""
        return shutil.which(_CLI) is not None

    def _build_command(self, prompt: str) -> list[str]:
        """The argv for one grading: the template with ``prompt`` and the model (``cli_argv``)."""
        return routed_argv(build_cli_argv(self._command, prompt, self.model), self.route)

    def _grade_once(self, criterion: str, artifact: Any) -> float:
        """One graded sample: up to ``1 + retries`` attempts, else :class:`JudgeError`."""
        prompt = GRADING_PROMPT.format(criterion=criterion, artifact=str(artifact))
        if "\x00" in prompt:
            # argv cannot carry a NUL (subprocess raises ValueError); retrying
            # cannot help, so fail now. A binary-ish diff can contain one.
            raise JudgeError("the artifact contains a NUL byte, which cannot be passed to the CLI")
        attempts = self._retries + 1
        last_failure: JudgeError | None = None
        for _ in range(attempts):
            try:
                return self._attempt(prompt)
            except JudgeError as failure:
                last_failure = failure
        raise JudgeError(
            f"judge {self._command[0]!r} gave no score after {attempts} attempt(s): {last_failure}"
        ) from last_failure

    def _attempt(self, prompt: str) -> float:
        """Run the CLI once; its score, or :class:`JudgeError` saying why not."""
        try:
            with routed_env(self.route, None) as env, _judge_cwd(self.route) as cwd:
                completed = subprocess.run(
                    self._build_command(prompt),
                    env=env,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    # Undecodable bytes become U+FFFD and then fail the parse as
                    # off-format, instead of escaping as UnicodeDecodeError.
                    encoding="utf-8",
                    errors="replace",
                    timeout=self._timeout,
                    check=False,
                )
        except subprocess.TimeoutExpired as exc:
            raise JudgeError(f"timed out after {self._timeout:g}s") from exc
        except OSError as exc:  # e.g. not executable, or E2BIG for a huge artifact
            raise JudgeError(f"could not launch {self._command[0]!r}: {exc}") from exc
        if completed.returncode != 0:
            output = _excerpt(self._redact(completed.stderr.strip() or completed.stdout))
            raise JudgeError(f"exited {completed.returncode}: {output}")
        score = parse_score(completed.stdout)
        if score is None:
            output = _excerpt(self._redact(completed.stdout))
            raise JudgeError(f"answered off-format (want one number in [0, 1]): {output!r}")
        return score

    def _redact(self, text: str) -> str:
        """``text`` without the endpoint token: a judge error must never carry it."""
        return text if self.route is None else self.route.redact(text)

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
