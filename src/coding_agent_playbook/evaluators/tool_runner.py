"""How a subprocess-backed metric runs a consumer-toolchain binary (prK §F.2.1).

``ruff_violations`` never calls :mod:`subprocess` itself: it calls a
:data:`ToolRunner` ``(argv, stdin, cwd, timeout_s) -> (returncode, stdout)``
from its :class:`~coding_agent_playbook.evaluators.types.ToolSetup`. The CLI,
pre-commit and CI use :func:`subprocess_tool_runner`; a hook passes a runner
over its own ``ProcPort`` (so tests script it with ``FakeRuff``), and evaluator
tests pass a named fake.

A runner that cannot answer (timeout, missing program) raises
:class:`ToolRunError`; the metric then yields no measurement, never a zero.
:class:`MemoToolRunner` runs each distinct ``(argv, stdin, cwd)`` once per gate
run, so an unchanged file (identical candidate and baseline text) costs one
ruff call, and a Stop stage can re-ask for details without a second process.
"""

from __future__ import annotations

import hashlib
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    #: ``(argv, stdin, cwd, timeout_s) -> (returncode, stdout)``; raises :class:`ToolRunError`.
    type ToolRunner = Callable[[Sequence[str], bytes, Path | None, float], tuple[int, bytes]]

__all__ = ["MemoToolRunner", "ToolRunError", "subprocess_tool_runner"]


class ToolRunError(Exception):
    """A tool call gave no usable answer: it timed out or its program could not start.

    Example::

        >>> str(ToolRunError("ruff timed out after 10s"))
        'ruff timed out after 10s'
    """


def subprocess_tool_runner(
    argv: Sequence[str], stdin: bytes, cwd: Path | None, timeout_s: float
) -> tuple[int, bytes]:
    """Run ``argv`` with ``stdin`` in ``cwd``, bounded by ``timeout_s``; stderr is discarded.

    Example::

        >>> subprocess_tool_runner(["ruff", "--version"], b"", None, 10.0)  # doctest: +SKIP
        (0, b'ruff 0.15.10\\n')
    """
    try:
        done = subprocess.run(
            list(argv),
            input=stdin,
            cwd=cwd,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolRunError(f"{argv[0]} timed out after {timeout_s:g}s") from exc
    except OSError as exc:
        raise ToolRunError(f"{argv[0]} could not run: {exc}") from exc
    return done.returncode, done.stdout


class MemoToolRunner:
    """A :data:`ToolRunner` answering each distinct ``(argv, sha256(stdin), cwd)`` once.

    A failed call is not remembered: the next ask retries it.

    Example::

        >>> runner = MemoToolRunner(subprocess_tool_runner)
        >>> runner(["ruff", "--version"], b"", None, 10.0)  # doctest: +SKIP
        (0, b'ruff 0.15.10\\n')
    """

    def __init__(self, inner: ToolRunner) -> None:
        self._inner = inner
        self._answers: dict[tuple[tuple[str, ...], str, str], tuple[int, bytes]] = {}

    def __call__(
        self, argv: Sequence[str], stdin: bytes, cwd: Path | None, timeout_s: float
    ) -> tuple[int, bytes]:
        key = (tuple(argv), hashlib.sha256(stdin).hexdigest(), str(cwd))
        answer = self._answers.get(key)
        if answer is None:
            answer = self._inner(argv, stdin, cwd, timeout_s)
            self._answers[key] = answer
        return answer
