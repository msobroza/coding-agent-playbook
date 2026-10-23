"""The ``--runner``, ``--judge`` and ``--judge-samples`` checks ``playbook eval`` shares.

One home for them: ``--run`` (``eval.py``) and ``--compare`` (``_eval_compare.py``)
both reject an unknown or unusable runner or judge, and a bad judge sample count,
before spending anything. Each check prints its own ``error:`` line on stderr and
returns ``None``; the caller then exits ``2``.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals import registry

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner

# D80: the old --samples spelling stays one release as a hidden alias; it is
# removed in the release after v0.21. Printed (not warnings.warn): pytest runs
# with filterwarnings = error.
_SAMPLES_DEPRECATION: Final = (
    "warning: --samples is deprecated and will be removed in the next release; use --judge-samples"
)
_BOTH_SAMPLE_FLAGS: Final = (
    "error: pass --judge-samples or its deprecated alias --samples, not both"
)


def load_usable_runner(name: str) -> type[HarnessRunner] | None:
    """The runner class registered as ``name`` if it can run here, else ``None``.

    An unknown name lists the registered runners; a runner whose ``available()``
    guard fails (its CLI is not installed) suggests ``--runner fake``.

    Example::

        >>> load_usable_runner("fake").__name__
        'FakeRunner'
    """
    runner_cls = registry.load_runner_class(name)
    if runner_cls is None:
        known = ", ".join(registry.available_runner_names()) or "(none registered)"
        _error(f"unknown --runner {name!r}; registered runners: {known}")
        return None
    if not runner_available(runner_cls):
        _error(
            f"runner {name!r} is unavailable in this environment "
            "(its CLI/SDK is not installed). Try `--runner fake` for a hermetic "
            "no-op run, or install the agent CLI."
        )
        return None
    return runner_cls


def load_usable_judge(name: str) -> type[Judge] | None:
    """The judge class registered as ``name`` if it can run here, else ``None``.

    Example::

        >>> load_usable_judge("no-such-judge") is None  # doctest: +SKIP
        True
    """
    judge_cls = registry.load_judge_class(name)
    if judge_cls is None:
        known = ", ".join(registry.available_judge_names()) or "(none registered)"
        _error(f"unknown --judge {name!r}; registered judges: {known}")
        return None
    if not judge_cls.available():
        _error(
            f"judge {name!r} is unavailable in this environment "
            "(its CLI/SDK is not installed). Omit `--judge` for a "
            "deterministic-only run, or install the judge's CLI."
        )
        return None
    return judge_cls


def runner_available(runner_cls: type[HarnessRunner]) -> bool:
    """Whether ``runner_cls`` can run here.

    Runners may expose an ``available()`` classmethod (the real
    ``ClaudeCodeRunner`` does, guarding on its CLI being on ``PATH``). A runner
    without one, the hermetic ``FakeRunner``, is always available.

    Example::

        >>> runner_available(type("NoGuard", (), {}))  # doctest: +SKIP
        True
    """
    guard = getattr(runner_cls, "available", None)
    if guard is None:
        return True
    return bool(guard())


def judge_sample_count(args: argparse.Namespace) -> int | None:
    """The per-criterion judge sample count, or ``None`` on a usage error.

    Reads ``--judge-samples`` and its deprecated ``--samples`` alias (D80): the
    alias prints one stderr line naming ``--judge-samples``; both flags at once, or
    a count below 1, print an error and return ``None`` (the caller exits ``2``).
    A non-positive count is rejected rather than floored so a typo never silently
    changes what gets graded.

    Example::

        >>> import argparse
        >>> judge_sample_count(argparse.Namespace(judge_samples=3, deprecated_samples=None))
        3
    """
    new = getattr(args, "judge_samples", None)
    old = getattr(args, "deprecated_samples", None)
    if new is not None and old is not None:
        print(_BOTH_SAMPLE_FLAGS, file=sys.stderr)
        return None
    if old is not None:
        print(_SAMPLES_DEPRECATION, file=sys.stderr)
    count: int | None = old if old is not None else new
    if count is not None and count < 1:
        _error(f"--judge-samples must be >= 1, got {count}")
        return None
    return count or 1


def _error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
