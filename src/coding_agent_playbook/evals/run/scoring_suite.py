"""The scoring suite's process: its bound, its environment, its toolchain and its rows.

Eval scoring (:mod:`~coding_agent_playbook.evals.run.scoring`) runs a sample's
test suite through a
:class:`~coding_agent_playbook.grading.execution_metrics.project.ProjectHandle`
(:func:`open_suite_handle`), and only when an execution metric is referenced
(:func:`suite_metrics_of`; ``run_tests`` is *inferred*, not authored). Each run
stops after 300 s and starts from an allowlisted environment (:func:`suite_env`:
``PATH``, ``HOME``, the locale, the temp dirs, the Python path and the Windows
system variables), so no API key, token, agent socket or ``PYTEST_*`` option of
the caller reaches agent code.

The command is ``python -P -m pytest`` with the engine's session-record plugin
(:mod:`~coding_agent_playbook.grading.execution_metrics.suite_record_plugin`, read
by :mod:`~coding_agent_playbook.grading.execution_metrics.suite_record`), writing
to a temp dir outside the suite's argv, so neither a planted ``pytest.py`` nor a
``conftest.py`` that rewrites the reports passes for pytest's own session.

A sample cannot be scored (:class:`UnscorableSuiteError`, exit 2) when this
interpreter lacks pytest or pytest-cov (:func:`require_suite_toolchain`).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.exit_two import ExitTwoError
from coding_agent_playbook.grading.execution_metrics.project import (
    NoSuiteResultError,
    ProjectHandle,
)
from coding_agent_playbook.grading.measuring import (
    SourceMeter,
    measure_suite,
    measure_tree,
    referenced_metrics,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from contextlib import ExitStack

    from coding_agent_playbook.grading.metric import Metric
    from coding_agent_playbook.grading.rubric import Rubric
    from coding_agent_playbook.grading.types import Measurement, MeasureSetup

#: Bound on one scoring suite run, in seconds. Why: an agent's test, or the code it
#: tests, can loop forever, and the run had no timeout, so one trial stalled a whole
#: ``eval --record``. The shipped samples' suites finish in seconds.
_SUITE_TIMEOUT_S: Final = 300.0

#: The caller's variables the scoring suite keeps (compared upper-cased, as Windows
#: names are case-insensitive); every other one is dropped. Why an allowlist: the
#: suite runs agent-written code, and the engine's environment holds API keys,
#: endpoint tokens, ``GITHUB_TOKEN`` and ``SSH_AUTH_SOCK``. ``PYTHONPATH`` and
#: ``PYTHONHOME`` stay because :func:`require_suite_toolchain`'s in-process
#: ``find_spec`` saw them: without them the suite could miss a toolchain the check
#: found, and every trial would give no result. ``SYSTEMROOT`` and the other
#: Windows names stay because Python there needs them for sockets and ``random``.
_SUITE_ENV_NAMES: Final = frozenset(
    {
        "PATH", "HOME", "USER", "LOGNAME", "LANG", "TZ", "TMPDIR", "TEMP", "TMP",
        "PYTHONPATH", "PYTHONHOME", "PYTHONUTF8", "PYTHONIOENCODING", "VIRTUAL_ENV",
        "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "WINDIR", "USERPROFILE",
        "APPDATA", "LOCALAPPDATA",
    }
)  # fmt: skip

#: Name prefixes the scoring suite keeps too: the ``LC_*`` locale categories.
_SUITE_ENV_PREFIXES: Final = ("LC_",)

#: The modules the suite's ``python -m pytest --cov`` imports from this interpreter.
_SUITE_TOOLCHAIN: Final = ("pytest", "pytest_cov")


class UnscorableSuiteError(ExitTwoError):
    """The scoring suite cannot judge the agent fairly, so the sample cannot be scored (exit 2)."""


class SuiteToolchainError(UnscorableSuiteError):
    """This interpreter lacks a module the scoring suite runs: the environment's fault."""


def require_suite_toolchain(rubric: Rubric) -> None:
    """Raise :class:`SuiteToolchainError` when ``rubric`` runs the suite and a module is missing.

    Why in this process: the suite runs this interpreter in the candidate tree,
    where a ``pytest.py`` can fake any output or exit code, so the run cannot tell
    a missing pytest-cov from the agent's crash. Without it every trial scored 0.
    The runner calls it before any agent runs, scoring before the suite.

    Example::

        >>> require_suite_toolchain(compile_eval_sample(sample).per_trial)  # doctest: +SKIP
    """
    if suite_metrics_of(rubric):
        check_suite_toolchain()


def check_suite_toolchain() -> None:
    """Raise :class:`SuiteToolchainError` naming each suite module this interpreter lacks.

    Example::

        >>> check_suite_toolchain()  # doctest: +SKIP
    """
    missing = [name for name in _SUITE_TOOLCHAIN if not _importable(name)]
    if missing:
        raise SuiteToolchainError(
            f"the scoring suite runs {sys.executable} -m pytest --cov, which cannot import "
            f"{', '.join(missing)}: install the playbook's dev extra into that interpreter"
        )


def _importable(name: str) -> bool:
    """Whether this interpreter can import ``name``; the seam a test replaces."""
    return importlib.util.find_spec(name) is not None


def suite_metrics_of(rubric: Rubric) -> list[Metric]:
    """The metrics ``rubric`` references that run the test suite.

    Example::

        >>> [m.name for m in suite_metrics_of(rubric)]  # doctest: +SKIP
        ['test_pass_rate']
    """
    return [m for m in referenced_metrics(rubric.checks) if not m.needs_judge and m.needs_project]


def static_metrics_of(rubric: Rubric) -> list[Metric]:
    """The metrics ``rubric`` references that read each source file, with no suite or judge.

    Example::

        >>> [m.name for m in static_metrics_of(rubric)]  # doctest: +SKIP
        ['cyclomatic']
    """
    referenced = referenced_metrics(rubric.checks)
    return [m for m in referenced if not m.needs_judge and not m.needs_project]


def tree_static_rows(tree: Path, metrics: list[Metric], setup: MeasureSetup) -> list[Measurement]:
    """``metrics`` over every ``*.py`` file of ``tree``; no walk when there is nothing to run.

    The label is the tree-relative POSIX path, so a candidate file matches its
    ``setup/`` baseline counterpart in the
    :class:`~coding_agent_playbook.grading.check.MeasurementSet` (same scope keys).
    A file that cannot be read, parsed or measured, or is over 1 MB, is skipped.

    Example::

        >>> tree_static_rows(candidate.tree, static_metrics_of(rubric), MeasureSetup())  # doctest: +SKIP
        [Measurement(evaluator='cyclomatic', scope_key='mod.py::f', value=3.0)]
    """
    if not metrics:
        return []
    return list(measure_tree(tree, SourceMeter(metrics, setup)).measurements)


def suite_rows(
    project: ProjectHandle, metrics: list[Metric], setup: MeasureSetup
) -> list[Measurement]:
    """The suite's measurements; none when it gave no result, and ``project.no_result`` says why.

    The candidate's reason reaches grading as ``ctx.suite_failure``, which fails
    every execution check: over no rows they graded zero scopes and passed. A
    command that cannot start raises, as :func:`require_suite_toolchain` does,
    since the environment, not the agent, has to change.

    Example::

        >>> suite_rows(handle, suite_metrics_of(rubric), MeasureSetup())  # doctest: +SKIP
        [Measurement(evaluator='test_pass_rate', scope_key='suite', value=1.0)]
    """
    try:
        return measure_suite(project, metrics, setup)
    except NoSuiteResultError:
        return []


def open_suite_handle(tree: Path, stack: ExitStack) -> ProjectHandle:
    """A bounded, recorded handle over ``tree`` in :func:`suite_env`; ``stack`` removes its dirs.

    The session record lives in a temp dir of its own: the report dir is in the
    suite's argv, where agent code can read it.

    Example::

        >>> open_suite_handle(candidate.tree, stack).run().returncode  # doctest: +SKIP
        0
    """
    reports = Path(
        stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-eval-reports-"))
    )
    session = Path(
        stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-eval-session-"))
    )
    return ProjectHandle.create(
        tree,
        reports,
        timeout_s=_SUITE_TIMEOUT_S,
        env_overrides=suite_env(reports),
        inherit_env=False,
        suite_record=session / "session.json",
    )


def suite_env(reports: Path, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The whole scoring-suite environment: the allowlisted part of ``base``, and its coverage file.

    ``base`` defaults to this process's environment. Only :data:`_SUITE_ENV_NAMES`
    and the :data:`_SUITE_ENV_PREFIXES` names survive, so no secret reaches agent
    code. That also drops every ``PYTEST_*`` name: ``-o addopts=`` does not clear
    ``PYTEST_ADDOPTS``, so a caller's ``-k`` deselected the failing tests, and an
    inherited plugin list or autoload switch broke the run. ``COVERAGE_FILE``
    keeps coverage's data file out of the candidate tree and apart between trials.

    Example::

        >>> sorted(suite_env(Path("/r"), {"PATH": "/bin", "ANTHROPIC_API_KEY": "k"}))
        ['COVERAGE_FILE', 'PATH']
    """
    source = os.environ if base is None else base
    kept = {name: value for name, value in source.items() if _suite_keeps(name)}
    return {**kept, "COVERAGE_FILE": str(reports / ".coverage")}


def _suite_keeps(name: str) -> bool:
    """Whether the scoring suite keeps the caller's variable ``name``, in any case."""
    upper = name.upper()
    return upper in _SUITE_ENV_NAMES or upper.startswith(_SUITE_ENV_PREFIXES)
