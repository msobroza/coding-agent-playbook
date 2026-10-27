"""``release.py prepare --eval``: release metrics per release target, checked for regressions.

Spec #281 ticket 15. Inside the scratch checkout (``prepare-checkout``), before
any release file is written, every target in the ``[evals] release`` list of the
checkout's committed ``.coding-agent-playbook.toml`` is recorded by the
checkout's own engine, in a subprocess::

    python -m coding_agent_playbook.cli eval --run --all --repo-root <checkout> \\
        --target <name> --record catalog/releases/<version>/metrics/<name>.json \\
        [--judge llm]      # when [evals.judge] names a model

so every sample grades the release's current text, and pinned samples also run
on their edition as a control (``controls`` in the file). Each file's
``release`` is set to the version being prepared, then it is compared with the
previous release's file for the same target (``check_regressions``), and the
comparison is stored in it. ``--accept SAMPLE=REASON`` (repeatable) accepts that
sample's regression on every target where it regressed; one that regressed on
no target is refused. An unaccepted regression refuses the release pull request,
whose body says per target how many samples were rerun and how many carried.

Recording is paid and slow, so on any refusal after it the recorded files are
copied to a kept directory outside the checkout, and ``--reuse-metrics DIR``
reads a target's file from there instead of recording it again (only when it
was recorded on the same base commit).
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.config.files import CONFIG_FILENAME
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
from coding_agent_playbook.release.manifest import release_dir
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


@dataclass(frozen=True)
class EvalRequest:
    """What ``prepare --eval`` was asked: accepted regressions, and a directory to reuse."""

    accepted: Mapping[str, str] = field(default_factory=dict)
    reuse: Path | None = None
    make_kept_dir: Callable[[], Path] = _make_kept_dir


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
    with metrics_kept_on_refusal(tools.cwd, version, request):
        recorded: dict[str, dict[str, object]] = {}
        for name in targets.names:
            metrics = _recorded(tools, name, out_dir, targets.judged, request.reuse, base)
            # The recording names the installed engine's version; the file is this release's.
            recorded[name] = {**metrics, "release": version}
        checked = _checked(tools.cwd, recorded, previous, request.accepted)
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
        raise ReleaseError(f"{exc}\n{_kept_note(out_dir, request.make_kept_dir)}") from exc


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
        f"{facts.get('samples')} samples ({_rerun_and_carried(facts)}), "
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


def _rerun_and_carried(summary: Mapping[str, object]) -> str:
    """``N rerun, M carried`` (#329 ticket 06); a file without the counts reran every sample."""
    carried = summary.get("carried", 0)
    return f"{summary.get('rerun', summary.get('samples'))} rerun, {carried} carried"


def _recorded(
    tools: Tools, name: str, out_dir: Path, judged: bool, reuse: Path | None, base: str
) -> dict[str, object]:
    """``name``'s metrics: reused from ``reuse`` when recorded there on ``base``, else recorded."""
    path = out_dir / f"{name}.json"
    kept = None if reuse is None else reuse / f"{name}.json"
    if kept is not None and kept.is_file():
        metrics = _load(kept)
        if metrics.get("commit") != base:
            raise ReleaseError(
                f"{kept} was recorded on commit {metrics.get('commit')}, not on the base {base}: "
                "drop --reuse-metrics or remove that file to record the target again"
            )
        print(f"release: reused the metrics of target {name!r} from {kept}")
        return metrics
    path.parent.mkdir(parents=True, exist_ok=True)
    argv = _record_argv(tools.cwd, name, path, judged)
    done = tools.runner(argv, cwd=tools.cwd, timeout=RECORD_TIMEOUT_SECONDS)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()[-5:]
        raise ReleaseError(
            f"recording target {name!r} exited {done.returncode}: " + "\n".join(detail)
        )
    print(f"release: recorded the metrics of target {name!r}")
    return _load(path)


def _record_argv(checkout: Path, name: str, path: Path, judged: bool) -> list[str]:
    judge = ["--judge", RELEASE_JUDGE] if judged else []
    cli = [sys.executable, "-m", "coding_agent_playbook.cli", "eval", "--run", "--all"]
    return [*cli, "--repo-root", str(checkout), "--target", name, "--record", str(path), *judge]


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
    """The previous release's file for target ``name``, or ``None`` when it has none."""
    if previous is None:
        return None
    path = release_dir(checkout / _CATALOG, previous) / METRICS_DIRNAME / f"{name}.json"
    return _load(path) if path.is_file() else None


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


def _kept_note(out_dir: Path, make_kept_dir: Callable[[], Path]) -> str:
    """Copy the recorded files out of the checkout; the sentence that names where."""
    if not out_dir.is_dir() or not any(out_dir.glob("*.json")):
        return "no metrics file was recorded"
    kept = make_kept_dir()
    for path in sorted(out_dir.glob("*.json")):
        shutil.copy2(path, kept / path.name)
    return f"the recorded metrics are kept in {kept}: pass --reuse-metrics {kept} to reuse them"


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
