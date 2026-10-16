"""The one suite run the ``tests`` and ``coverage`` Stop stages share (specs/prK-hook-pack.md §F.1.2).

With coverage-diff-gate on, stop-ci-parity-gate's ``tests`` stage and the
``coverage`` stage read **one** run of the project's suite per Stop, a full run
(``tests_scope`` is forced to ``all``: a targeted ``--no-cov`` run cannot
measure changed lines) that writes junit **and** coverage XML:

- the command is the ``stop_gate.stages[coverage]`` record (the pinned project
  interpreter, ``-m pytest -o addopts= ...``), never ``[metrics] test_cmd``,
  which the agent can edit. The run appends its per-worktree report paths and
  ``--cov=<import root>`` (coverage.py's source mode, so a never-imported file
  counts as uncovered instead of unmeasured);
- reports, ``COVERAGE_FILE`` and the empty coverage config live in
  ``<state>/suite/<fingerprint>/`` (older trees' dirs removed) and
  ``PYTHONDONTWRITEBYTECODE=1`` is set: a new worktree file would change the
  Stop fingerprint and loop the gate;
- the run is a :class:`PinnedSuiteHandle` (the stage runner: pin signature
  checked, ``proc.run``), memoized on the event: whichever stage asks first runs it.

No report raises :class:`SuiteUnavailable` with the stage's skip category
(``timeout``, ``toolchain_missing``, ``crash``): never green.
``RuntimeDeps.suite_handle`` replaces the handle (``FakeProjectHandle`` in tests).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evaluators.execution.project import (
    ProjectHandle,
    RunArtifacts,
    import_roots,
)
from coding_agent_playbook.hook_runtime.state import StateUnavailable
from coding_agent_playbook.hook_runtime.stop.tools import runner_of, seconds_left, stage_command

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.hook_runtime.deps import Clock
    from coding_agent_playbook.hook_runtime.event import RepoInfo
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.state import StateStore
    from coding_agent_playbook.hook_runtime.stop.runner import StageRunner
    from coding_agent_playbook.hook_runtime.stop.stages import SkipCategory, StopPlan

__all__ = [
    "PYTEST_COV_ADVICE",
    "SUITE_DIR",
    "SUITE_STAGE",
    "PinnedSuiteHandle",
    "SharedSuite",
    "SuiteOutcome",
    "SuiteSpec",
    "SuiteUnavailable",
    "pinned_suite_handle",
    "shared_suite",
    "suite_env",
]

#: The stage record whose tool and args the shared run executes.
SUITE_STAGE: Final = "coverage"
#: ``<state>/suite/<fingerprint>/`` holds one Stop's reports (specs/prK-lifecycle-hooks.md §D.6.1).
SUITE_DIR: Final = "suite"
PYTEST_COV_ADVICE: Final = (
    "pytest-cov is not installed in the project environment; ask the user to add it to "
    "the dev dependencies"
)
#: pytest's usage error (exit 4) when no plugin provides ``--cov``.
_NO_COV_OPTION: Final = b"unrecognized arguments: --cov"
#: pytest exit codes that still mean "the suite ran": all passed, no tests collected.
_RAN_CODES: Final = (0, 5)
_STALE_REPORTS: Final = ("junit.xml", "coverage.xml")


class SuiteUnavailable(RuntimeError):
    """The shared suite produced no report; ``category`` is the stage's skip category.

    ``advice`` is one line for the **user** (a missing pin or pytest-cov).

    Example::

        >>> SuiteUnavailable("timeout", "project_python did not finish").category
        'timeout'
    """

    def __init__(self, category: SkipCategory, detail: str, advice: str = "") -> None:
        super().__init__(detail)
        self.category: SkipCategory = category
        self.advice = advice


@dataclass(frozen=True, slots=True)
class SuiteSpec:
    """What the shared run executes: the record's ``tool`` and ``args`` in ``root``.

    ``env`` replaces the child environment; ``timeout_s`` bounds the run.

    Example::

        >>> spec.run_args[-1].startswith("--cov-config=")  # doctest: +SKIP
        True
    """

    root: Path
    report_dir: Path
    tool: str
    args: tuple[str, ...]
    env: Mapping[str, str]
    timeout_s: float

    @property
    def run_args(self) -> tuple[str, ...]:
        """The record's args, then the junit and coverage reports in :attr:`report_dir`."""
        sources = (f"--cov={source}" for source in import_roots(self.root))
        return (
            *self.args,
            f"--junitxml={self.report_dir / 'junit.xml'}",
            *sources,
            f"--cov-report=xml:{self.report_dir / 'coverage.xml'}",
            f"--cov-config={self.report_dir / 'coveragerc'}",
        )


@dataclass
class PinnedSuiteHandle(ProjectHandle):
    """A ``ProjectHandle`` whose one run goes through the Stop stage runner (pins, ``proc.run``).

    ``output`` keeps the run's stdout and stderr for the ``tests`` stage's
    failure lines. Build it with :func:`pinned_suite_handle`.
    """

    runner: StageRunner | None = None
    spec: SuiteSpec | None = None
    output: bytes = b""

    def _run_once(self) -> RunArtifacts:
        """Run the record's command once; :class:`SuiteUnavailable` when it wrote no report."""
        if self.runner is None or self.spec is None:
            raise SuiteUnavailable("crash", "the suite handle has no runner or spec")
        spec = self.spec
        run = self.runner.run(spec.tool, spec.run_args, timeout=spec.timeout_s, env=spec.env)
        if run.skip_category:
            detail = f"{spec.tool} did not run ({run.skip_category})"
            raise SuiteUnavailable(run.skip_category, detail, run.advice)
        self.output = run.stdout + run.stderr
        returncode = -1 if run.returncode is None else run.returncode
        junit = self._read_junit()
        if junit.total == 0 and returncode not in _RAN_CODES:
            raise _no_report(returncode, self.output)
        return RunArtifacts(junit=junit, coverage=self._read_coverage(), returncode=returncode)


def _no_report(returncode: int, output: bytes) -> SuiteUnavailable:
    if _NO_COV_OPTION in output:
        return SuiteUnavailable("toolchain_missing", "pytest-cov is missing", PYTEST_COV_ADVICE)
    return SuiteUnavailable("crash", f"pytest exited {returncode} without a junit report")


def pinned_suite_handle(spec: SuiteSpec, runner: StageRunner) -> PinnedSuiteHandle:
    """The real shared-suite handle, with the empty coverage config the twins' command also uses.

    Example: ``pinned_suite_handle(spec, runner_of(ctx, repo)).run().returncode``.
    """
    spec.report_dir.mkdir(parents=True, exist_ok=True)
    (spec.report_dir / "coveragerc").write_text("[run]\n", encoding="utf-8")
    return PinnedSuiteHandle(
        root=spec.root,
        test_cmd=[spec.tool, *spec.run_args],
        report_dir=spec.report_dir,
        timeout_s=spec.timeout_s,
        runner=runner,
        spec=spec,
    )


def suite_env(base: Mapping[str, str], report_dir: Path) -> dict[str, str]:
    """``base`` with ``COVERAGE_FILE`` in ``report_dir`` and no bytecode written.

    Example::

        >>> suite_env({}, Path("/s"))["COVERAGE_FILE"]
        '/s/.coverage'
    """
    return {**base, "COVERAGE_FILE": str(report_dir / ".coverage"), "PYTHONDONTWRITEBYTECODE": "1"}


@dataclass(frozen=True, slots=True)
class SuiteOutcome:
    """The shared run's result: its handle and artifacts, or why there are none.

    Example: ``outcome.red`` when any test failed or pytest exited non-zero.
    """

    handle: ProjectHandle | None = None
    artifacts: RunArtifacts | None = None
    problem: SuiteUnavailable | None = None

    @property
    def output(self) -> bytes:
        """The run's stdout and stderr (empty for a handle that keeps none)."""
        output = getattr(self.handle, "output", b"")
        return output if isinstance(output, bytes) else b""

    @property
    def red(self) -> bool:
        """Whether the suite ran and failed (a test failed or errored, or pytest exited non-zero)."""
        found = self.artifacts
        if found is None:
            return False
        return found.returncode != 0 or found.junit.failed + found.junit.errors > 0


@dataclass
class SharedSuite:
    """The event's one suite run: :meth:`outcome` runs it on the first call, then replays it.

    ``build(timeout_s)`` makes the handle (raising :class:`SuiteUnavailable`).
    """

    build: Callable[[float], ProjectHandle]
    clock: Clock
    _outcome: SuiteOutcome | None = field(default=None, repr=False)

    def outcome(self, deadline: float) -> SuiteOutcome:
        """The run's outcome, bounded by ``deadline`` on the first call."""
        if self._outcome is None:
            self._outcome = self._run(deadline)
        return self._outcome

    def _run(self, deadline: float) -> SuiteOutcome:
        left = seconds_left(self.clock, deadline)
        if left <= 0:
            return SuiteOutcome(problem=SuiteUnavailable("timeout", "no time left for the suite"))
        try:
            handle = self.build(left)
            return SuiteOutcome(handle=handle, artifacts=handle.run())
        except SuiteUnavailable as exc:
            return SuiteOutcome(problem=exc)
        except Exception as exc:  # a broken report or handle: never green (§E.0.5)
            detail = f"the suite run failed ({type(exc).__name__})"
            return SuiteOutcome(problem=SuiteUnavailable("crash", detail))


def shared_suite(plan: StopPlan, ctx: HandlerContext, repo: RepoInfo) -> SharedSuite:
    """This Stop's shared suite of ``repo``, made once per event (whichever stage asks first).

    Example: ``shared_suite(plan, ctx, ev.repo).outcome(deadline).artifacts``.
    """

    def make() -> SharedSuite:
        return SharedSuite(
            build=lambda timeout_s: _handle(plan, ctx, repo, timeout_s), clock=ctx.clock
        )

    suite: SharedSuite = ctx.memo.get_or_compute(("stop-suite", repo.worktree_root), make)
    return suite


def _handle(plan: StopPlan, ctx: HandlerContext, repo: RepoInfo, timeout_s: float) -> ProjectHandle:
    command = stage_command(ctx.cfg, SUITE_STAGE)
    if command is None:
        raise SuiteUnavailable("crash", "no coverage stage record in guard_config")
    report_dir = _report_dir(ctx.session.store, plan)
    spec = SuiteSpec(
        root=Path(repo.worktree_root),
        report_dir=report_dir,
        tool=command[0],
        args=command[1],
        env=suite_env(ctx.env, report_dir),
        timeout_s=timeout_s,
    )
    factory = None if ctx.deps is None else ctx.deps.suite_handle
    if factory is not None:
        return factory(spec)
    return pinned_suite_handle(spec, runner_of(ctx, repo))


def _report_dir(store: StateStore, plan: StopPlan) -> Path:
    """``<state>/suite/<fingerprint>/``, emptied of stale reports; other trees' dirs removed."""
    fingerprint = plan.fingerprint
    key = "unknown" if fingerprint is None else fingerprint.key.replace(":", "-")
    try:
        root = store.private_dir(SUITE_DIR)
        for child in root.iterdir():
            if child.name != key and child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
        target = store.private_dir(f"{SUITE_DIR}/{key}")
        for stale in (*_STALE_REPORTS, *(p.name for p in target.glob(".coverage*"))):
            (target / stale).unlink(missing_ok=True)
    except (StateUnavailable, ValueError, OSError) as exc:
        raise SuiteUnavailable(
            "crash", f"no usable state dir for the suite reports: {exc}"
        ) from exc
    return target
