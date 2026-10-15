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
- ``gate-scan`` and ``scan-secrets`` (E.4: always on, so CI scans every
  change for secret tokens and credential files) diff ``<merge base>..HEAD``;
  the base is ``--base`` or the default branch (``_git_base``), resolved only
  when a selected step needs it.

Exit codes: 0 every run step passed, 1 any failed or timed out, 2 a usage
error or an unresolvable base (nothing ran). ``--format json`` prints one
``{step, argv, exit, duration_s, status}`` record per step on stdout and the
children's output on stderr.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Protocol

from coding_agent_playbook.commands._git_base import open_git, resolve_merge_base
from coding_agent_playbook.hook_runtime.git import GitError

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Sequence
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
CONFIG_FILE: Final = ".coding-agent-playbook.toml"
_CLI: Final = ("-m", "coding_agent_playbook.cli")

type StepStatus = Literal["passed", "failed", "timeout", "skipped"]


@dataclass(frozen=True, slots=True)
class CiContext:
    """What the step table's builders and predicates read.

    ``output_committed`` is ``None`` without a config; ``merge_base`` is ``""``
    until a selected step needs it. ``requested`` are the names ``--steps``
    named explicitly (empty: none), for rows enabled only on request.
    """

    repo_root: Path
    output_committed: bool | None
    requested: frozenset[str] = frozenset()
    merge_base: str = ""


@dataclass(frozen=True, slots=True)
class CiStep:
    """One ``CI_STEPS`` row: ``argv`` builds the subcommand argv, ``skip_reason`` says why not.

    Example: ``CiStep("validate", "existing", lambda ctx: ["validate"])``.
    """

    name: str
    owner: str
    argv: Callable[[CiContext], list[str]]
    skip_reason: Callable[[CiContext], str | None] = lambda ctx: None
    needs_base: bool = False
    timeout_s: float = DEFAULT_STEP_TIMEOUT_S


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


CI_STEPS: Final[tuple[CiStep, ...]] = (
    CiStep("sync-check", "prerequisites", lambda ctx: ["sync", "--check"], _sync_check_skip),
    CiStep("validate", "existing", lambda ctx: ["validate"]),
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
) -> int:
    """Run the selected ``CI_STEPS`` rows and report them; returns 0, 1 or 2.

    Example::

        >>> run(build_parser().parse_args(["ci", "--steps", "validate"]))  # doctest: +SKIP
        0
    """
    repo_root = Path(args.repo_root or ".").resolve()
    try:
        steps = select_steps(args.steps)
        ctx = CiContext(repo_root, _output_committed(repo_root), _requested(args.steps))
        ctx = _with_base(ctx, steps, args.base, git)
    except (GitError, ValueError) as exc:  # GitBaseError is a ValueError
        print(f"error: {exc}", file=sys.stderr)
        return 2
    log = sys.stderr if args.format == "json" else sys.stdout
    records = run_ci(steps, ctx, runner or SubprocessCiStepRunner(), clock, log=log)
    code = aggregate_exit(records)
    print(_json(records, code) if args.format == "json" else _summary(records))
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
        _log(records[-1], log)
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
    argv = (sys.executable, *_CLI, *step.argv(ctx), "--repo-root", str(ctx.repo_root))
    started = clock()
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
    ctx: CiContext, steps: Sequence[CiStep], base: str | None, git: GitPort | None
) -> CiContext:
    """``ctx`` with the merge base set, when a step that will run needs one."""
    if not any(step.needs_base and step.skip_reason(ctx) is None for step in steps):
        return ctx
    port = git if git is not None else open_git(ctx.repo_root)
    return replace(ctx, merge_base=resolve_merge_base(port, base).sha)


def _output_committed(repo_root: Path) -> bool | None:
    """``[output] commit`` of the merged config; ``True`` when it does not load (fail closed)."""
    if not (repo_root / CONFIG_FILE).is_file():
        return None
    from coding_agent_playbook.sources.filesystem import FileSystemStateSource

    try:
        return FileSystemStateSource(repo_root=repo_root).load_config().commit_output
    except (ValueError, OSError, KeyError, TypeError):
        return True  # sync --check then reports the broken config itself


def _requested(text: str | None) -> frozenset[str]:
    return frozenset(name.strip() for name in (text or "").split(",") if name.strip())


def _log(record: StepRecord, stream: TextIO | None) -> None:
    if stream is None:
        return
    print(f"--- {record.step}: {shlex.join(record.argv)}", file=stream)
    if record.output.strip():
        print(record.output.rstrip("\n"), file=stream)
    stream.flush()


def _summary(records: Sequence[StepRecord]) -> str:
    lines = [_status_line(record) for record in records]
    counts = {status: sum(r.status == status for r in records) for status in ("passed", "skipped")}
    failed = len(records) - counts["passed"] - counts["skipped"]
    lines.append(
        f"playbook ci: {counts['passed']} passed, {failed} failed, {counts['skipped']} skipped"
    )
    return "\n".join(lines)


def _status_line(record: StepRecord) -> str:
    if record.status == "skipped":
        return f"SKIP {record.step}: {record.note}"
    if record.status == "timeout":
        return f"TIMEOUT {record.step} (after {record.duration_s:.2f}s)"
    word = "PASS" if record.status == "passed" else "FAIL"
    return f"{word} {record.step} (exit {record.exit}, {record.duration_s:.2f}s)"


def _json(records: Sequence[StepRecord], code: int) -> str:
    document = {"steps": [record.to_json() for record in records], "exit": code}
    return json.dumps(document, indent=2)


def _decoded(output: bytes | str | None) -> str:
    if output is None:
        return ""
    return output if isinstance(output, str) else output.decode("utf-8", errors="replace")
