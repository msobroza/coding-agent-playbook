"""``release.py prepare --eval``: release metrics per release target, checked for regressions.

Spec #281 ticket 15. Inside the scratch checkout (``prepare-checkout``), before
any release file is written, every target in the ``[evals] release`` list of the
checkout's committed ``.coding-agent-playbook.toml`` is recorded by the
checkout's own engine, in a subprocess::

    python -m coding_agent_playbook.cli eval --run --all --repo-root <checkout> \\
        --target <name> --record catalog/releases/<version>/metrics/<name>.json \\
        [--judge llm]      # when [evals.judge] names a model
        [--carry-from catalog/releases]

so every sample grades the release's current text, and pinned samples also run
on their edition as a control (``controls`` in the file). The run is
changed-only by default (#329 ticket 07): the releases directory is the
``--carry-from`` baseline (spec D3), so the engine reuses results from every
committed release with the target's setup, only the samples whose inputs changed
rerun and the others are carried; ``--full`` (``EvalRequest.full``) omits it and
reruns everything. Each file's
``release`` is set to the version being prepared, then it is compared with the
previous release's file for the same target (``check_regressions``), and the
comparison is stored in it. ``--accept SAMPLE=REASON`` (repeatable) accepts that
sample's regression on every target where it regressed; one that regressed on
no target is refused. An unaccepted regression refuses the release pull request,
whose body says per target "changed-only: N rerun, M carried (K compared with
<previous>)" or "full run";
the engine's carry plan (why samples rerun) is passed on to the output.

Recording is paid and slow, so on any refusal after it the recorded files are
copied to a kept directory outside the checkout, and ``--reuse-metrics DIR``
reads a target's file from there instead of recording it again (only when it
was recorded on the same base commit). A reused file's mode comes from the file,
not from this run's flags, and ``--full`` refuses one that holds carried entries.

Every recording also saves each finished sample to a checkpoint outside the
checkout (``checkpoint_path``: one per base commit and target) and resumes from
it, so a crash, a timeout or a sleep loses no finished sample: rerunning
``prepare --eval`` on the same base reruns only the rest. ``--jobs N`` runs N
samples at a time. ``tail -f`` the checkpoint to watch the run.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.evals.answers_store import answers_path
from coding_agent_playbook.evals.release_metrics_schema import (
    ReleaseMetricsError,
    validate_release_metrics,
)
from coding_agent_playbook.evals.release_regression import (
    RegressionCheck,
    annotate_release_metrics,
    check_regressions,
)
from coding_agent_playbook.evals.release_regression_format import format_regression_table
from coding_agent_playbook.evals.target_config import load_eval_settings
from coding_agent_playbook.exit_two import ExitTwoError
from coding_agent_playbook.release.manifest import RELEASES_DIRNAME, release_dir
from release_eval_mode import carried_count, changed_only_mode, recorded_changed_only
from release_tools import ReleaseError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from release_tools import Tools

#: The directory beside ``manifest.toml`` that holds one metrics file per target.
METRICS_DIRNAME: Final = "metrics"
#: Bounds one target's recording: every sample, every run, on a paid harness.
RECORD_TIMEOUT_SECONDS: Final = 6 * 60 * 60
#: The judge every recording uses when ``[evals.judge] model`` is set.
RELEASE_JUDGE: Final = "llm"
#: A target name that is safe as a file name (it becomes ``metrics/<name>.json``).
_TARGET_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_CATALOG: Final = "catalog"


def _make_kept_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="playbook-release-metrics-"))


def _default_checkpoint_root() -> Path:
    return Path(tempfile.gettempdir()) / "playbook-release-checkpoints"


def checkpoint_path(root: Path, base: str, name: str) -> Path:
    """Where target ``name``'s recording on ``base`` saves each finished sample.

    Outside the throwaway checkout, so a failed run's samples outlive it.

    Example::

        >>> checkpoint_path(Path("/tmp/c"), "8a26e1a3", "opencode-qwen").as_posix()
        '/tmp/c/8a26e1a3/opencode-qwen.partial.jsonl'
    """
    return root / base / f"{name}.partial.jsonl"


@dataclass(frozen=True)
class EvalRequest:
    """What ``prepare --eval`` was asked: accepted regressions, a directory to reuse, full runs."""

    accepted: Mapping[str, str] = field(default_factory=dict)
    reuse: Path | None = None
    #: ``--full``: record without the releases directory as ``--carry-from``.
    full: bool = False
    make_kept_dir: Callable[[], Path] = _make_kept_dir
    #: ``--jobs``: samples each recording runs at the same time.
    jobs: int = 1
    #: Where recordings save their checkpoints (``checkpoint_path``).
    checkpoint_root: Path = field(default_factory=_default_checkpoint_root)


@dataclass(frozen=True)
class ReleaseTargets:
    """The ``[evals] release`` targets of the checkout, and whether a judge model is set."""

    names: tuple[str, ...]
    judged: bool


@dataclass(frozen=True)
class TargetMetrics:
    """One target's stored metrics file, and its check (``None``: no previous file)."""

    name: str
    metrics: Mapping[str, object]
    check: RegressionCheck | None
    #: Recorded with a ``--carry-from`` baseline; a reused file: recorded so (``recorded_changed_only``).
    changed_only: bool = False
    #: The engine's reason when a changed-only recording reran every sample.
    full_rerun_reason: str | None = None


def release_targets(checkout: Path) -> ReleaseTargets:
    """The checkout's release targets; refuses none, or a name unfit for a file name.

    Example::

        >>> release_targets(Path("."))  # doctest: +SKIP
        ReleaseTargets(names=('claude-opus',), judged=True)
    """
    try:
        settings = load_eval_settings(checkout)
    except (ExitTwoError, ValueError) as exc:  # ConfigError is a ValueError
        raise ReleaseError(f"--eval: {exc}") from exc
    if not settings.release:
        raise ReleaseError(f"--eval: the [evals] release list of {CONFIG_FILENAME} names no target")
    bad = [name for name in settings.release if not _TARGET_NAME.fullmatch(name)]
    if bad:
        raise ReleaseError(f"--eval: release target names must be file-name safe, got {bad}")
    return ReleaseTargets(settings.release, judged=settings.judge.model is not None)


def record_release_metrics(
    tools: Tools,
    *,
    version: str,
    previous: str | None,
    base: str,
    targets: ReleaseTargets,
    request: EvalRequest,
) -> tuple[TargetMetrics, ...]:
    """Record, check and store every target's metrics file; refuses an unaccepted regression.

    On a refusal the recorded files are copied to a kept directory, named in the error.
    """
    out_dir = release_dir(tools.cwd / _CATALOG, version) / METRICS_DIRNAME
    carry_from = None if request.full else tools.cwd / _CATALOG / "releases"
    with metrics_kept_on_refusal(tools.cwd, version, request):
        results: dict[str, _RecordResult] = {}
        for name in targets.names:
            answers = answers_path(tools.cwd / _CATALOG / RELEASES_DIRNAME, version, name)
            recording = _Recording(
                name, out_dir / f"{name}.json", answers, targets.judged, carry_from
            )
            results[name] = _recorded(tools, recording, request, base)
        # The recording names the installed engine's version; the file is this release's.
        recorded = {name: {**r.metrics, "release": version} for name, r in results.items()}
        checked = _with_modes(_checked(tools.cwd, recorded, previous, request.accepted), results)
        for outcome in checked:
            _write(out_dir / f"{outcome.name}.json", outcome.metrics)
        _refuse_blocked(checked)
    return checked


@contextlib.contextmanager
def metrics_kept_on_refusal(checkout: Path, version: str, request: EvalRequest) -> Iterator[None]:
    """On a ``ReleaseError`` inside, copy ``version``'s recorded metrics out and name them.

    The release branch is discarded on any refusal, so a refusal after recording
    (cz bump, commit, push, ``pr create``) would otherwise lose paid runs.

    Example::

        >>> with metrics_kept_on_refusal(checkout, "9.9.9", request):  # doctest: +SKIP
        ...     publish()
    """
    out_dir = release_dir(checkout / _CATALOG, version) / METRICS_DIRNAME
    try:
        yield
    except ReleaseError as exc:
        raise ReleaseError(f"{exc}\n{_kept_note(out_dir, request)}") from exc


def metrics_body(outcomes: Sequence[TargetMetrics]) -> str:
    """The pull request body's ``Release metrics`` section: one line per target, and notes."""
    lines = ["## Release metrics", ""]
    for outcome in outcomes:
        lines.append(f"- `{outcome.name}`: {_summary_line(outcome)}")
        if outcome.check is not None:
            lines += [f"  - note: {note}" for note in outcome.check.notes]
    return "\n".join(lines) + "\n"


def _summary_line(outcome: TargetMetrics) -> str:
    summary = outcome.metrics.get("summary")
    facts = summary if isinstance(summary, dict) else {}
    line = (
        f"{facts.get('samples')} samples ({_mode(outcome)}), "
        f"pass rate {facts.get('pass_rate')}, mean score {facts.get('mean_score')}"
    )
    check = outcome.check
    if check is None:
        return f"{line}; no previous release metrics to compare with"
    return (
        f"{line}; vs {check.previous}: {check.count('regression')} regressions "
        f"({check.accepted_regressions} accepted), {check.count('improvement')} improvements, "
        f"{check.count('not_comparable')} not comparable"
    )


def _with_modes(
    outcomes: Sequence[TargetMetrics], results: Mapping[str, _RecordResult]
) -> tuple[TargetMetrics, ...]:
    """Each outcome with the mode its file was recorded in (#329 ticket 07).

    A file reused with ``--reuse-metrics`` was recorded by an earlier run, so its
    mode comes from the file (``recorded_changed_only``), not from this run's flags.
    """
    return tuple(
        dataclasses.replace(
            o,
            changed_only=results[o.name].changed_only,
            full_rerun_reason=results[o.name].full_rerun_reason,
        )
        for o in outcomes
    )


def _mode(outcome: TargetMetrics) -> str:
    """``changed-only: N rerun, M carried (K compared with <previous>)`` or ``full run``."""
    if not outcome.changed_only:
        return "full run"
    reason = outcome.full_rerun_reason
    return changed_only_mode(outcome.metrics, full_rerun_reason=reason, check=outcome.check)


@dataclass(frozen=True)
class _Recording:
    """One target's record command: where it writes, with a judge, from which baseline.

    ``answers`` is the target's answers file in the release directory (spec D8).
    """

    name: str
    path: Path
    answers: Path
    judged: bool
    carry_from: Path | None


@dataclass(frozen=True)
class _RecordResult:
    """One target's metrics file, the mode it was recorded in, and why it reran everything."""

    metrics: dict[str, object]
    changed_only: bool
    full_rerun_reason: str | None = None


def _recorded(
    tools: Tools, recording: _Recording, request: EvalRequest, base: str
) -> _RecordResult:
    """The target's metrics: reused from ``request.reuse`` when kept there, else recorded."""
    kept = None if request.reuse is None else request.reuse / f"{recording.name}.json"
    if kept is not None and kept.is_file():
        return _reused(kept, recording.name, base, full=request.full)
    checkpoint = checkpoint_path(request.checkpoint_root, base, recording.name)
    return _fresh(tools, recording, checkpoint, request.jobs)


def _reused(kept: Path, name: str, base: str, *, full: bool) -> _RecordResult:
    """The kept file of target ``name``; refuses another base, or carried entries under --full."""
    metrics = _load(kept)
    if metrics.get("commit") != base:
        raise ReleaseError(
            f"{kept} was recorded on commit {metrics.get('commit')}, not on the base {base}: "
            "drop --reuse-metrics or remove that file to record the target again"
        )
    if full and carried_count(metrics) > 0:
        raise ReleaseError(
            f"{kept} carries {carried_count(metrics)} entries from a baseline, but --full reruns "
            "every sample: drop --reuse-metrics or remove that file to record the target again"
        )
    print(f"release: reused the metrics of target {name!r} from {kept}")
    return _RecordResult(metrics, changed_only=recorded_changed_only(metrics))


def _fresh(tools: Tools, recording: _Recording, checkpoint: Path, jobs: int) -> _RecordResult:
    """Record the target in a subprocess, resuming ``checkpoint``; pass its carry plan on."""
    name, path = recording.name, recording.path
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"release: recording target {name!r}; each finished sample is saved to {checkpoint}")
    argv = [*_record_argv(tools.cwd, recording), *_resume_flags(checkpoint, jobs)]
    done = tools.runner(argv, cwd=tools.cwd, timeout=RECORD_TIMEOUT_SECONDS)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()[-5:]
        raise ReleaseError(
            f"recording target {name!r} exited {done.returncode}: " + "\n".join(detail)
        )
    mode = (
        "in full" if recording.carry_from is None else f"changed-only from {recording.carry_from}"
    )
    plan = carry_plan_lines(done.stdout)
    for line in plan:
        print(f"release: {name}: {line}")
    print(f"release: recorded the metrics of target {name!r} {mode}")
    changed_only = recording.carry_from is not None
    return _RecordResult(_load(path), changed_only, full_rerun_reason(plan))


def carry_plan_lines(stdout: str) -> list[str]:
    """The record run's carry plan: its ``carry plan:`` line and the indented reasons under it.

    Example::

        >>> carry_plan_lines("x\ncarry plan: 1 rerun, 0 carried\n  a: new sample\ndone\n")
        ['carry plan: 1 rerun, 0 carried', '  a: new sample']
    """
    lines: list[str] = []
    inside = False
    for line in stdout.splitlines():
        if line.startswith("carry plan:"):
            inside = True
        elif inside and not line.startswith("  "):
            inside = False
        if inside:
            lines.append(line)
    return lines


def full_rerun_reason(plan: Sequence[str]) -> str | None:
    """Why a changed-only recording reran every sample, from its carry plan; ``None`` if not.

    Example::

        >>> full_rerun_reason(["carry plan: every sample reruns, setup differs: 2 rerun, 0 carried"])
        'every sample reruns, setup differs'
    """
    prefix = "carry plan: every sample reruns, "
    first = next((line for line in plan if line.startswith(prefix)), None)
    return None if first is None else first.removeprefix("carry plan: ").rpartition(": ")[0]


def _resume_flags(checkpoint: Path, jobs: int) -> list[str]:
    """Save and resume each finished sample at ``checkpoint``; run ``jobs`` samples at a time."""
    return ["--checkpoint", str(checkpoint), "--resume", "--jobs", str(jobs)]


def _record_argv(checkout: Path, recording: _Recording) -> list[str]:
    judge = ["--judge", RELEASE_JUDGE] if recording.judged else []
    carry = [] if recording.carry_from is None else ["--carry-from", str(recording.carry_from)]
    cli = [sys.executable, "-m", "coding_agent_playbook.cli", "eval", "--run", "--all"]
    where = ["--repo-root", str(checkout), "--target", recording.name]
    out = ["--record", str(recording.path), "--answers", str(recording.answers)]
    return [*cli, *where, *out, *judge, *carry]


def _checked(
    checkout: Path,
    recorded: Mapping[str, dict[str, object]],
    previous: str | None,
    accepted: Mapping[str, str],
) -> tuple[TargetMetrics, ...]:
    """Each target's file checked against the previous release's; refuses a stray acceptance."""
    baselines = {name: _baseline(checkout, previous, name) for name in recorded}
    regressed: dict[str, set[str]] = {}
    for name, metrics in recorded.items():
        baseline = baselines[name]
        if baseline is not None:
            plain = _check(metrics, baseline, {})
            regressed[name] = {v.sample_id for v in plain.samples if v.status == "regression"}
    stray = sorted(set(accepted) - set().union(*regressed.values()))
    if stray:
        raise ReleaseError(
            f"--accept names {', '.join(repr(s) for s in stray)}, which regressed on no "
            "release target"
        )
    outcomes = []
    for name, metrics in recorded.items():
        baseline = baselines[name]
        if baseline is None:
            outcomes.append(TargetMetrics(name, metrics, None))
            continue
        mine = {s: accepted[s] for s in regressed[name] if s in accepted}
        check = _check(metrics, baseline, mine)
        outcomes.append(TargetMetrics(name, annotate_release_metrics(metrics, check), check))
    return tuple(outcomes)


def _check(
    metrics: Mapping[str, object], baseline: Mapping[str, object], accepted: Mapping[str, str]
) -> RegressionCheck:
    try:
        return check_regressions(metrics, baseline, accepted=accepted)
    except ExitTwoError as exc:
        raise ReleaseError(str(exc)) from exc


def _baseline(checkout: Path, previous: str | None, name: str) -> dict[str, object] | None:
    """The previous release's file for target ``name``, loaded, or ``None`` when it has none."""
    path = _previous_file(checkout, previous, name)
    return None if path is None else _load(path)


def _previous_file(checkout: Path, previous: str | None, name: str) -> Path | None:
    """The path of the previous release's file for target ``name``, or ``None`` without one."""
    if previous is None:
        return None
    path = release_dir(checkout / _CATALOG, previous) / METRICS_DIRNAME / f"{name}.json"
    return path if path.is_file() else None


def _refuse_blocked(outcomes: Sequence[TargetMetrics]) -> None:
    for outcome in outcomes:
        if outcome.check is not None:
            print(format_regression_table(outcome.check))
    blocked = [o.name for o in outcomes if o.check is not None and o.check.blocked]
    if blocked:
        raise ReleaseError(
            f"unaccepted regressions on target(s) {', '.join(blocked)}: fix them, or re-run "
            "with --accept SAMPLE=REASON for each, so no release pull request was opened"
        )


def _kept_note(out_dir: Path, request: EvalRequest) -> str:
    """Copy the recorded files out of the checkout; the sentence that names where."""
    if not out_dir.is_dir() or not any(out_dir.glob("*.json")):
        return "no metrics file was recorded"
    kept = request.make_kept_dir()
    for path in sorted(out_dir.glob("*.json")):
        shutil.copy2(path, kept / path.name)
    full = " --full" if request.full else ""
    return (
        f"the recorded metrics are kept in {kept}: pass --reuse-metrics {kept}{full} to reuse them"
    )


def _load(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        validate_release_metrics(data)
    except (OSError, ValueError, ReleaseMetricsError) as exc:
        raise ReleaseError(f"cannot read the release metrics file {path}: {exc}") from exc
    assert isinstance(data, dict)  # validate_release_metrics refuses anything else
    return data


def _write(path: Path, metrics: Mapping[str, object]) -> None:
    try:
        validate_release_metrics(metrics)
    except ReleaseMetricsError as exc:
        raise ReleaseError(f"the checked metrics for {path} are invalid: {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
