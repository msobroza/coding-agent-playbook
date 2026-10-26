"""The ``--runner``, ``--target``, ``--judge`` and ``--judge-samples`` checks ``playbook eval`` shares.

One home for them: ``--run`` (``eval.py``) and ``--compare`` (``_eval_compare.py``)
both reject an unknown or unusable runner or judge, and a bad judge sample count,
before spending anything. Each check prints its own ``error:`` line on stderr and
returns ``None``; the caller then exits ``2``. :func:`select_target` instead
raises :class:`~coding_agent_playbook.evals.targets.TargetError` (exit 2 too).
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals import registry
from coding_agent_playbook.evals.run.claude_code_route import claude_code_route
from coding_agent_playbook.evals.run.opencode_route import opencode_route
from coding_agent_playbook.evals.run.opencode_runner import OpenCodeRunner
from coding_agent_playbook.evals.targets import TargetError, resolve_target, runner_alias_target

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.evals.endpoints import Endpoint
    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.run.claude_code_route import ClaudeCodeRoute
    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner
    from coding_agent_playbook.evals.run.opencode_route import OpenCodeRoute
    from coding_agent_playbook.evals.targets import EvalSettings, EvalTarget, JudgeSettings

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


def select_target(args: argparse.Namespace, settings: EvalSettings) -> EvalTarget:
    """The Eval target this run drives (``evals.targets.resolve_target``'s order).

    ``settings`` is the repo's ``[evals]`` (``evals.target_config.load_eval_settings``).

    ``--runner <name>`` stays an alias for a target with that harness and no
    model; passing it with ``--target`` raises :class:`TargetError`, as does a
    ``--target`` (or a default) that names no target.

    Example::

        >>> select_target(argparse.Namespace(runner="fake", target=None), settings).harness  # doctest: +SKIP
        'fake'
    """
    runner = getattr(args, "runner", None)
    target = getattr(args, "target", None)
    if runner is not None and target is not None:
        raise TargetError(
            f"pass --target {target!r} or --runner {runner!r}, not both "
            "(--runner is the target with that harness and no model)"
        )
    if runner is not None:
        return runner_alias_target(runner)
    return resolve_target(settings, cli_value=target, env=os.environ)


def build_target_runner(target: EvalTarget) -> HarnessRunner | None:
    """A runner for ``target``'s harness, sent its model; ``None`` after an error line.

    Unknown or unavailable harnesses fail like ``--runner`` does
    (:func:`load_usable_runner`); a model for a runner that takes none is refused
    rather than dropped. A target without a model builds the runner as before.
    A target on an endpoint gets its route (token read from the environment now,
    so a missing variable fails before any run: ``EndpointError``, exit 2).

    Example::

        >>> build_target_runner(EvalTarget("t", "fake", "m")).model  # doctest: +SKIP
        'm'
    """
    runner_cls = load_usable_runner(target.harness)
    if runner_cls is None:
        return None
    if target.model is None:
        return runner_cls()
    if not runner_cls.accepts_model:
        _error(
            f"target {target.name!r}: runner {target.harness!r} takes no model, "
            f"got model {target.model!r}; drop the model or pick another harness"
        )
        return None
    if target.endpoint is None:
        return runner_cls(model=target.model)  # type: ignore[call-arg]
    if not runner_cls.accepts_endpoint:
        _error(
            f"target {target.name!r}: runner {target.harness!r} cannot reach endpoint "
            f"{target.endpoint.name!r}; use a claude_code or opencode target"
        )
        return None
    route = _endpoint_route(runner_cls, target.endpoint, target.model, target.small_model)
    return runner_cls(model=target.model, route=route)  # type: ignore[call-arg]


def _endpoint_route(
    runner_cls: type[HarnessRunner], endpoint: Endpoint, model: str, small_model: str | None
) -> ClaudeCodeRoute | OpenCodeRoute:
    """The wiring ``runner_cls``'s harness reaches ``endpoint`` with (token read now)."""
    if issubclass(runner_cls, OpenCodeRunner):
        return opencode_route(endpoint, model, small_model=small_model)
    return claude_code_route(endpoint, model, small_model=small_model)


def build_judge(name: str, settings: JudgeSettings) -> Judge | None:
    """The judge ``name`` names, sent ``[evals.judge] model``; ``None`` after an error line.

    Example::

        >>> build_judge("llm", JudgeSettings(model="claude-opus-5-5"))  # doctest: +SKIP
    """
    judge_cls = load_usable_judge(name)
    if judge_cls is None:
        return None
    if settings.model is None:
        return judge_cls()
    if not judge_cls.accepts_model:
        _error(
            f"judge {name!r} takes no model, but [evals.judge] model = {settings.model!r}; "
            "remove that key or use --judge llm"
        )
        return None
    if settings.endpoint is None:
        return judge_cls(model=settings.model)  # type: ignore[call-arg]
    if not judge_cls.accepts_endpoint:
        _error(
            f"judge {name!r} cannot reach endpoint {settings.endpoint.name!r}; "
            "remove [evals.judge] endpoint or use --judge llm"
        )
        return None
    route = claude_code_route(settings.endpoint, settings.model)
    return judge_cls(model=settings.model, route=route)  # type: ignore[call-arg]


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


def judge_sample_count(args: argparse.Namespace, default: int = 1) -> int | None:
    """The per-criterion judge sample count, or ``None`` on a usage error.

    Reads ``--judge-samples`` and its deprecated ``--samples`` alias (D80): the
    alias prints one stderr line naming ``--judge-samples``; both flags at once, or
    a count below 1, print an error and return ``None`` (the caller exits ``2``).
    A non-positive count is rejected rather than floored so a typo never silently
    changes what gets graded. Without either flag the count is ``default``
    (``[evals.judge] samples`` for ``--run``).

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
    return count if count is not None else default


def _error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
