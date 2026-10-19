"""``playbook ci`` — the aggregate off-workstation twin, one required status check (specs/prK-hook-pack.md §F.5).

Hooks are speed bumps; this is the authoritative check. Each row of
:data:`CI_STEPS` runs as a **child process**, ``<python> -m
coding_agent_playbook.cli <argv> --repo-root <root>`` (an argv list, no shell,
a per-step timeout), so one step crashing cannot take the others down and every
step sees exactly what a developer running it would. Other sections append
rows here (K10: ``metrics``, ``coverage``, ``commit-convention``; K8: the
secrets and dependency twins) instead of adding a second CI entry point.

- ``sync-check`` runs only when the config exists **and** ``[output] commit =
  true``: since SPEC §7.1's ``commit = false`` default, generated output is
  gitignored, so a fresh CI checkout has none and ``sync --check`` would always
  fail. A config that does not load runs it anyway, so the child reports why.
- ``metrics`` (F.2/F.3, always on) runs the static metrics gate over the
  files changed since the merge base, never the suite.
- ``coverage`` (F.1) runs the suite: changed-line coverage and total coverage
  non-regression against the merge base. It runs when ``[metrics] run_tests =
  true`` (a config that does not load runs it anyway, to report why) or when
  ``--steps`` names it.
- ``gate-scan`` and ``scan-secrets`` (E.4: always on, so CI scans every
  change for secret tokens and credential files) diff ``<merge base>..HEAD``;
  the base is ``--base`` or the default branch (``_git_scope``), resolved only
  when a selected step needs it.
- ``commit-trailers`` (E.4) checks every commit of that range against
  git-commit-push-policy-guard's trailer rows, and runs only when one is
  configured (a policy that does not load runs it anyway, to report why).
- ``check-deps`` (E.4) diffs the manifests from the merge base against
  dependency-allowlist-guard's allowlist and index rules, and runs only when a
  dependency policy is configured (same fail-closed rule).
- ``scan-sinks`` (E.3, K7's tool) is opt-in: it runs only when ``--steps``
  names it.
- ``commit-convention`` (F.4) runs ``cz check`` itself, not an engine child
  (``_ci_commit_convention``): over ``<merge base>..HEAD`` filtered by the
  committer-date cut-over, plus ``PLAYBOOK_PR_TITLE`` as one argv element. It
  runs when ``[tool.commitizen]`` or ``[hooks.commit_convention]`` is set, and
  a missing ``cz`` fails it. The readers that decide which rows run live in
  ``policy``; each fails closed.

Exit codes: 0 every run step passed, 1 any failed or timed out, 2 a usage
error or an unresolvable base (nothing ran). ``--format json`` prints one
``{step, argv, exit, duration_s, status}`` record per step on stdout and the
children's output on stderr.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Protocol

from coding_agent_playbook.commands.twins._ci_commit_convention import (
    COMMIT_STEP,
    CzCommands,
    cz_commands,
    run_cz_commands,
)
from coding_agent_playbook.commands.twins._ci_report import json_report, log_step, summary_text
from coding_agent_playbook.commands.twins._git_scope import open_git, resolve_merge_base
from coding_agent_playbook.commands.twins.policy import (
    CONFIG_FILE,
    commit_convention_configured,
    dependency_policy_set,
    metrics_run_tests,
    output_committed,
    trailer_rows_configured,
)
from coding_agent_playbook.hook_runtime.git import GitError

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Mapping, Sequence
    from typing import TextIO

    from coding_agent_playbook.hook_runtime.git import GitPort

__all__ = [
    "CI_STEPS",
    "DEFAULT_STEP_TIMEOUT_S",
    "CiContext",
    "CiStep",
    "CiStepRunner",
    "StepRecord",
    "StepRun",
    "SubprocessCiStepRunner",
    "aggregate_exit",
    "run",
    "run_ci",
    "select_steps",
]

#: Per child step: generous, since a CI runner is slow and K10's coverage row runs a suite.
DEFAULT_STEP_TIMEOUT_S: Final = 600.0
_CLI: Final = ("-m", "coding_agent_playbook.cli")

type StepStatus = Literal["passed", "failed", "timeout", "skipped"]


@dataclass(frozen=True, slots=True)
class CiContext:
    """What the step table's builders and predicates read.

    ``output_committed`` is ``None`` without a config; ``merge_base`` is ``""``
    until a selected step needs it. ``requested`` are the names ``--steps``
    named explicitly (empty: none), for rows enabled only on request.
    ``trailer_rows`` says whether a commit-trailer row is configured (read
    only when the ``commit-trailers`` row is selected); ``dependency_policy``
    the same for the ``check-deps`` row, and ``run_tests`` (``[metrics]
    run_tests``) for the ``coverage`` row; ``commit_convention`` whether a
    commitizen convention is configured, and ``commit_checks`` the ``cz``
    calls of the ``commit-convention`` row once the merge base is known.
    """

    repo_root: Path
    output_committed: bool | None
    requested: frozenset[str] = frozenset()
    merge_base: str = ""
    trailer_rows: bool = False
    dependency_policy: bool = False
    run_tests: bool = False
    commit_convention: bool = False
    commit_checks: CzCommands | None = None


type StepExecutor = Callable[[CiContext, CiStepRunner, float], tuple[tuple[str, ...], StepRun]]


@dataclass(frozen=True, slots=True)
class CiStep:
    """One ``CI_STEPS`` row: ``argv`` builds the subcommand argv, ``skip_reason`` says why not.

    ``execute`` replaces the engine child for a row that runs another program
    (``commit-convention`` runs ``cz``): it returns the argv it shows and the result.

    Example: ``CiStep("validate", "existing", lambda ctx: ["validate"])``.
    """

    name: str
    owner: str
    argv: Callable[[CiContext], list[str]]
    skip_reason: Callable[[CiContext], str | None] = lambda ctx: None
    needs_base: bool = False
    timeout_s: float = DEFAULT_STEP_TIMEOUT_S
    execute: StepExecutor | None = None


@dataclass(frozen=True, slots=True)
class StepRun:
    """What one child returned: its exit code (``None``: timed out) and merged output.

    Example: ``StepRun(0, "ok\\n")``.
    """

    exit: int | None
    output: str


class CiStepRunner(Protocol):
    """Runs one step's argv; :class:`SubprocessCiStepRunner` is the real one."""

    def run(self, argv: Sequence[str], *, cwd: Path, timeout_s: float) -> StepRun: ...


@dataclass(frozen=True, slots=True)
class StepRecord:
    """The outcome of one step, as the text and JSON reports show it.

    Example: ``StepRecord("validate", ("python", "-m", "..."), 0, 1.2, "passed")``.
    """

    step: str
    argv: tuple[str, ...]
    exit: int | None
    duration_s: float
    status: StepStatus
    note: str = ""
    output: str = ""

    def to_json(self) -> dict[str, object]:
        """``{step, argv, exit, duration_s, status}``, plus ``note`` for a skipped step."""
        document: dict[str, object] = {
            "step": self.step,
            "argv": list(self.argv),
            "exit": self.exit,
            "duration_s": self.duration_s,
            "status": self.status,
        }
        if self.note:
            document["note"] = self.note
        return document


def _sync_check_skip(ctx: CiContext) -> str | None:
    if ctx.output_committed is None:
        return f"no {CONFIG_FILE}"
    if not ctx.output_committed:
        return "[output] commit = false: generated output is not committed, so CI has none"
    return None


def _commit_trailers_skip(ctx: CiContext) -> str | None:
    if ctx.trailer_rows:
        return None
    return "no trailer row in [hooks.git-commit-push-policy-guard]"


def _check_deps_skip(ctx: CiContext) -> str | None:
    if ctx.dependency_policy:
        return None
    return "no dependency policy (allowlist, required_index or index_mode = deny)"


def _scan_sinks_skip(ctx: CiContext) -> str | None:
    return None if "scan-sinks" in ctx.requested else "opt-in: run with --steps scan-sinks"


def _metrics_argv(ctx: CiContext) -> list[str]:
    """Static non-regression of the changed files against the merge base (§F.2.3).

    The merge base, not ``origin/<base>``, keeps main's later edits out of the
    comparison; ``--no-run-tests`` leaves the suite to the ``coverage`` row.
    """
    return ["metrics", "--baseline", f"git:{ctx.merge_base}", "--changed", "--no-run-tests"]


def _coverage_argv(ctx: CiContext) -> list[str]:
    """Changed-line coverage plus total non-regression against the merge base (§F.1.3).

    Two suite runs (candidate and a baseline worktree); ``diff_coverage``
    alone would need one.
    """
    return ["metrics", "--run-tests", "--select", "testing", "--baseline", f"git:{ctx.merge_base}"]


def _coverage_skip(ctx: CiContext) -> str | None:
    if ctx.run_tests or "coverage" in ctx.requested:
        return None
    return "[metrics] run_tests is not true: run with --steps coverage"


def _commit_convention_skip(ctx: CiContext) -> str | None:
    if ctx.commit_convention:
        return None
    return "no [tool.commitizen] in pyproject.toml and no [hooks.commit_convention]"


def _commit_convention_run(
    ctx: CiContext, runner: CiStepRunner, timeout_s: float
) -> tuple[tuple[str, ...], StepRun]:
    checks = ctx.commit_checks or CzCommands(error="the commit range was not listed")
    return run_cz_commands(checks, ctx.repo_root, runner, timeout_s)


CI_STEPS: Final[tuple[CiStep, ...]] = (
    CiStep("sync-check", "prerequisites", lambda ctx: ["sync", "--check"], _sync_check_skip),
    CiStep("validate", "existing", lambda ctx: ["validate"]),
    CiStep("metrics", "F.2/F.3", _metrics_argv, needs_base=True),
    CiStep("coverage", "F.1", _coverage_argv, _coverage_skip, needs_base=True),
    CiStep(
        "gate-scan",
        "E.2",
        lambda ctx: ["gate-scan", "--range", f"{ctx.merge_base}..HEAD"],
        needs_base=True,
    ),
    CiStep(
        "scan-secrets",
        "E.4",
        lambda ctx: ["scan-secrets", "--range", f"{ctx.merge_base}..HEAD"],
        needs_base=True,
    ),
    CiStep(
        COMMIT_STEP,
        "F.4",
        lambda ctx: ["cz", "check"],
        _commit_convention_skip,
        needs_base=True,
        execute=_commit_convention_run,
    ),
    CiStep(
        "commit-trailers",
        "E.4",
        lambda ctx: ["check-commit-trailers", "--range", f"{ctx.merge_base}..HEAD"],
        _commit_trailers_skip,
        needs_base=True,
    ),
    CiStep(
        "check-deps",
        "E.4",
        lambda ctx: ["check-deps", "--base", ctx.merge_base],
        _check_deps_skip,
        needs_base=True,
    ),
    CiStep(
        "scan-sinks",
        "E.3",
        lambda ctx: ["scan-sinks", "--range", f"{ctx.merge_base}..HEAD"],
        _scan_sinks_skip,
        needs_base=True,
    ),
)


class SubprocessCiStepRunner:
    """:class:`CiStepRunner` over ``subprocess.run``: stdin closed, stderr merged into stdout.

    Example::

        >>> SubprocessCiStepRunner().run([sys.executable, "-c", "print(1)"], cwd=Path("."),
        ...                              timeout_s=10).exit
        0
    """

    def run(self, argv: Sequence[str], *, cwd: Path, timeout_s: float) -> StepRun:
        """Run ``argv`` in ``cwd`` within ``timeout_s`` seconds."""
        try:
            done = subprocess.run(
                list(argv),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return StepRun(None, _decoded(exc.output))
        except OSError as exc:
            return StepRun(127, f"cannot start {argv[0]}: {exc.strerror}\n")
        return StepRun(done.returncode, _decoded(done.stdout))


def run(
    args: argparse.Namespace,
    *,
    runner: CiStepRunner | None = None,
    git: GitPort | None = None,
    clock: Callable[[], float] = time.monotonic,
    which: Callable[[str], str | None] = shutil.which,
    env: Mapping[str, str] | None = None,
) -> int:
    """Run the selected ``CI_STEPS`` rows and report them; returns 0, 1 or 2.

    ``which`` finds ``cz`` and ``env`` holds ``PLAYBOOK_PR_TITLE`` (default: this
    process's environment) for the ``commit-convention`` row.

    Example::

        >>> run(build_parser().parse_args(["ci", "--steps", "validate"]))  # doctest: +SKIP
        0
    """
    repo_root = Path(args.repo_root or ".").resolve()
    try:
        steps = select_steps(args.steps)
        names = {step.name for step in steps}
        ctx = CiContext(
            repo_root,
            output_committed(repo_root),
            _requested(args.steps),
            trailer_rows="commit-trailers" in names and trailer_rows_configured(repo_root),
            dependency_policy="check-deps" in names and dependency_policy_set(repo_root),
            run_tests="coverage" in names and metrics_run_tests(repo_root),
            commit_convention=COMMIT_STEP in names and commit_convention_configured(repo_root),
        )
        ctx = _with_base(ctx, steps, args.base, git, (which, os.environ if env is None else env))
    except (GitError, ValueError) as exc:  # GitBaseError is a ValueError
        print(f"error: {exc}", file=sys.stderr)
        return 2
    log = sys.stderr if args.format == "json" else sys.stdout
    records = run_ci(steps, ctx, runner or SubprocessCiStepRunner(), clock, log=log)
    code = aggregate_exit(records)
    print(json_report(records, code) if args.format == "json" else summary_text(records))
    return code


def select_steps(text: str | None) -> tuple[CiStep, ...]:
    """The ``CI_STEPS`` rows ``--steps`` names, in table order (all of them for ``None``).

    Raises ``ValueError`` naming the unknown or missing names.

    Example::

        >>> [step.name for step in select_steps("gate-scan,validate")]
        ['validate', 'gate-scan']
    """
    if text is None:
        return CI_STEPS
    wanted = _requested(text)
    known = [step.name for step in CI_STEPS]
    unknown = sorted(wanted - set(known))
    if unknown or not wanted:
        problem = f"unknown step(s) {', '.join(unknown)}" if unknown else "no step named"
        raise ValueError(
            f"--steps {text!r}: {problem}; expected a comma-separated subset of: {', '.join(known)}"
        )
    return tuple(step for step in CI_STEPS if step.name in wanted)


def run_ci(
    steps: Sequence[CiStep],
    ctx: CiContext,
    runner: CiStepRunner,
    clock: Callable[[], float],
    *,
    log: TextIO | None = None,
) -> tuple[StepRecord, ...]:
    """Run each step in order (no fail-fast) and record it; skipped rows are recorded too.

    Example::

        >>> run_ci(CI_STEPS[1:2], ctx, FakeCiStepRunner(), time.monotonic)[0].status  # doctest: +SKIP
        'passed'
    """
    records: list[StepRecord] = []
    for step in steps:
        reason = step.skip_reason(ctx)
        if reason is not None:
            records.append(StepRecord(step.name, (), None, 0.0, "skipped", note=reason))
            continue
        records.append(_run_step(step, ctx, runner, clock))
        log_step(records[-1], log)
    return tuple(records)


def aggregate_exit(records: Sequence[StepRecord]) -> int:
    """``1`` when any run step failed or timed out, else ``0``.

    Example::

        >>> aggregate_exit([StepRecord("validate", (), 1, 0.1, "failed")])
        1
    """
    return 1 if any(record.status in ("failed", "timeout") for record in records) else 0


def _run_step(
    step: CiStep, ctx: CiContext, runner: CiStepRunner, clock: Callable[[], float]
) -> StepRecord:
    started = clock()
    if step.execute is not None:
        argv, result = step.execute(ctx, runner, step.timeout_s)
    else:
        argv = (sys.executable, *_CLI, *step.argv(ctx), "--repo-root", str(ctx.repo_root))
        result = runner.run(argv, cwd=ctx.repo_root, timeout_s=step.timeout_s)
    duration = round(clock() - started, 3)
    return StepRecord(
        step.name, argv, result.exit, duration, _status(result.exit), output=result.output
    )


def _status(exit_code: int | None) -> StepStatus:
    if exit_code is None:
        return "timeout"
    return "passed" if exit_code == 0 else "failed"


def _with_base(
    ctx: CiContext,
    steps: Sequence[CiStep],
    base: str | None,
    git: GitPort | None,
    cz_lookup: tuple[Callable[[str], str | None], Mapping[str, str]],
) -> CiContext:
    """``ctx`` with the merge base set when a running step needs one, then the ``cz`` checks."""
    running = [step for step in steps if step.skip_reason(ctx) is None]
    if not any(step.needs_base for step in running):
        return ctx
    port = git if git is not None else open_git(ctx.repo_root)
    ctx = replace(ctx, merge_base=resolve_merge_base(port, base).sha)
    if not any(step.name == COMMIT_STEP for step in running):
        return ctx
    which, env = cz_lookup
    checks = cz_commands(port, ctx.repo_root, ctx.merge_base, which=which, env=env)
    return replace(ctx, commit_checks=checks)


def _requested(text: str | None) -> frozenset[str]:
    return frozenset(name.strip() for name in (text or "").split(",") if name.strip())


def _decoded(output: bytes | str | None) -> str:
    if output is None:
        return ""
    return output if isinstance(output, str) else output.decode("utf-8", errors="replace")
