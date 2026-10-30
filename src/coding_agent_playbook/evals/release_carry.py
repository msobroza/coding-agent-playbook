"""Which samples a ``--carry-from`` record reruns, and the entries it carries (#329 ticket 05).

``playbook eval --run --all --record OUT --carry-from PREVIOUS.json`` compares
the run with a baseline release metrics file (ADR 0013). :func:`plan_carry`
decides, before any paid run:

- **Full rerun** when the baseline records no setup digest, an entry without an
  inputs digest, or a setup part that differs from this run's
  (``evals.setup_digest.differing_setup_parts``); the reason names the parts.
- **Otherwise** a sample reruns when it is new or its inputs digest changed; every
  other sample becomes a *carried entry* (:func:`carried_entry`). Edition
  controls always rerun, so they never reach this module.

:func:`merge_carried` then adds the carried entries to the fresh record and folds
the summary from every entry (``evals.release_metrics.entries_summary``), with
``rerun``, ``carried`` and ``rejudged`` counts; ``tokens`` and ``cost_usd`` stay
the fresh runs' own, since a re-judged entry (spec D9, :class:`RejudgeSource`)
ran no agent. Nothing here runs an agent.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.evals.answers_store import ArtifactRef
from coding_agent_playbook.evals.release_metrics import entries_summary
from coding_agent_playbook.evals.release_metrics_schema import (
    INPUTS_DIGEST_KEY,
    JUDGED_IN_KEY,
    MEASURED_IN_KEY,
    REJUDGED_FROM_KEY,
    SETUP_DIGEST_KEY,
    SETUP_KEY,
    ReleaseMetricsError,
    validate_release_metrics,
)
from coding_agent_playbook.evals.setup_digest import differing_setup_parts
from coding_agent_playbook.exit_two import ExitTwoError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.evals.answers_store import StoredRun

#: Keys of a baseline entry that compare it with its own previous release, dropped on carry.
_COMPARISON_KEYS: Final = ("vs_previous", "accepted")
_NEW_SAMPLE: Final = "new sample (not in the baseline)"
_INPUTS_CHANGED: Final = "inputs digest changed"
_CONTROL: Final = "edition controls always rerun"


class CarryFromError(ExitTwoError):
    """``--carry-from`` names a baseline this record cannot use; ``playbook`` exits 2.

    Example::

        >>> str(CarryFromError("x"))
        'x'
    """


@dataclass(frozen=True)
class RejudgeSource:
    """A sample's entry in a file whose setup differs in judge parts only (spec D9).

    ``release``, ``commit`` and ``target`` name that file, ``judge`` its judge
    parts (``evals.answers_store.judge_parts_of``). ``runs`` are the entry's
    stored answers once the record has found them, each naming in
    ``artifact_ref`` the answers file its artifact came from.

    Example::

        >>> RejudgeSource("9.9.2", None, "opus", {"runs": 3}, {}).label
        '9.9.2 (opus)'
    """

    release: str
    commit: str | None
    target: str
    entry: Mapping[str, Any]
    judge: Mapping[str, object]
    runs: tuple[StoredRun, ...] = ()

    @property
    def label(self) -> str:
        """The source as a carry plan names it: ``"<release> (<target>)"``."""
        return f"{self.release} ({self.target})"

    @property
    def measured_in(self) -> dict[str, object]:
        """Where the entry's agent runs were measured: its own ``measured_in``, else this file."""
        own = self.entry.get(MEASURED_IN_KEY)
        if isinstance(own, dict):
            return dict(own)
        return {"release": self.release, "commit": self.commit, "target": self.target}

    @property
    def answers_at(self) -> ArtifactRef:
        """The answers file holding the lines the entry's current judge graded (spec D9).

        In order: the entry's ``judged_in``; this file, when the entry was
        re-judged here (``rejudged_from``); its ``measured_in`` when carried;
        else this file. Their criterion scores are the latest judge's, and a
        re-judged line's ``artifact_ref`` leads to the artifact.
        """
        place = self.entry.get(JUDGED_IN_KEY)
        if not isinstance(place, dict):
            rejudged_here = REJUDGED_FROM_KEY in self.entry
            place = self.entry.get(MEASURED_IN_KEY) if not rejudged_here else None
        if not isinstance(place, dict):
            return ArtifactRef(self.release, self.target)
        return ArtifactRef(str(place["release"]), str(place.get("target") or self.target))

    @property
    def rejudged_from(self) -> dict[str, object]:
        """The entry's ``rejudged_from``: the re-graded file's release, commit and judge parts."""
        return {"release": self.release, "commit": self.commit, "judge": dict(self.judge)}


@dataclass(frozen=True)
class CarryPlan:
    """What a ``--carry-from`` record reruns (by sample id, with the reason) and carries.

    ``full_rerun_reason`` is set when every sample reruns. ``reported_model`` is
    the baseline's, kept when no fresh run reports one. ``sources`` names, by
    sample id, the file each carried entry came from as ``"<release> (<target>)"``
    (``evals.result_index``); a ``--carry-from`` plan leaves it empty, as it
    leaves ``rejudge``: the samples to re-grade with this record's judge (D9).

    Example::

        >>> CarryPlan(None, {"a": "new sample"}, {}).reruns("a")
        True
    """

    full_rerun_reason: str | None
    rerun: Mapping[str, str]
    carried: Mapping[str, Mapping[str, object]]
    reported_model: str | None = None
    sources: Mapping[str, str] = field(default_factory=dict)
    rejudge: Mapping[str, RejudgeSource] = field(default_factory=dict)

    def reruns(self, sample_id: str) -> bool:
        """Whether ``sample_id`` runs fresh in this record."""
        return sample_id in self.rerun


def load_baseline(path: Path, target_name: str) -> dict[str, Any]:
    """The validated baseline metrics file at ``path``, refused unless it is for ``target_name``.

    Example::

        >>> load_baseline(Path("catalog/releases/9.9.9/metrics/opus.json"), "opus")  # doctest: +SKIP
    """
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CarryFromError(f"--carry-from {path}: cannot read the baseline: {exc}") from exc
    try:
        validate_release_metrics(data)
    except ReleaseMetricsError as exc:
        raise CarryFromError(f"--carry-from {path}: {exc}") from exc
    baseline_target = data["target"]["name"]
    if baseline_target != target_name:
        raise CarryFromError(
            f"--carry-from {path}: the baseline is for target {baseline_target!r}, not "
            f"{target_name!r}; pass the metrics file of {target_name!r}, so nothing was run"
        )
    return dict(data)


def plan_carry(
    baseline: Mapping[str, Any], *, setup: Mapping[str, object], inputs: Mapping[str, str]
) -> CarryPlan:
    """Which of the samples in ``inputs`` (id to inputs digest) rerun against ``baseline``.

    ``setup`` is this run's setup parts (``SetupParts.as_dict``).

    Example::

        >>> plan_carry(baseline, setup=parts.as_dict(), inputs={"review/x": "ab12"}).rerun  # doctest: +SKIP
        {}
    """
    entries: Mapping[str, Mapping[str, Any]] = baseline["samples"]
    reported = baseline["target"]["reported_model"]
    reason = _full_rerun_reason(baseline, setup)
    if reason is not None:
        return CarryPlan(reason, dict.fromkeys(sorted(inputs), reason), {}, reported)
    rerun: dict[str, str] = {}
    carried: dict[str, Mapping[str, object]] = {}
    for sample_id, digest in sorted(inputs.items()):
        why = _rerun_reason(entries.get(sample_id), digest)
        if why is not None:
            rerun[sample_id] = why
            continue
        release, commit = baseline["release"], baseline["commit"]
        carried[sample_id] = carried_entry(entries[sample_id], release=release, commit=commit)
    return CarryPlan(None, rerun, carried, reported)


def _full_rerun_reason(baseline: Mapping[str, Any], setup: Mapping[str, object]) -> str | None:
    """Why every sample reruns, naming what is missing or differs; ``None`` when none must."""
    if SETUP_DIGEST_KEY not in baseline or SETUP_KEY not in baseline:
        return "the baseline records no setup digest"
    keyless = sorted(
        sample_id
        for sample_id, entry in baseline["samples"].items()
        if INPUTS_DIGEST_KEY not in entry
    )
    if keyless:
        return (
            f"the baseline records no inputs digest for {len(keyless)} sample(s), "
            f"e.g. {keyless[0]!r}"
        )
    parts = differing_setup_parts(baseline[SETUP_KEY], setup)
    if parts:
        return "the setup differs from the baseline in " + ", ".join(parts)
    return None


def _rerun_reason(entry: Mapping[str, Any] | None, digest: str) -> str | None:
    if entry is None:
        return _NEW_SAMPLE
    if entry[INPUTS_DIGEST_KEY] != digest:
        return _INPUTS_CHANGED
    return None


def carried_entry(
    entry: Mapping[str, object], *, release: str, commit: str | None, target: str | None = None
) -> dict[str, object]:
    """``entry`` as carried from the baseline ``release`` at ``commit``.

    Its comparison with its own previous release is dropped, and ``measured_in``
    names where it was measured: kept when the entry was already carried. The
    result index passes the source file's ``target`` (later tasks find the
    entry's answers file by it); a ``--carry-from FILE`` record leaves it out.
    An entry re-judged in the baseline (``rejudged_from``) also gets
    ``judged_in``, the same place, unless it already names one: that release's
    answers file holds its current judge's lines (spec D9).

    Example::

        >>> carried_entry({"runs": 3}, release="9.9.9", commit=None)
        {'runs': 3, 'measured_in': {'release': '9.9.9', 'commit': None}}
    """
    copied = {key: value for key, value in entry.items() if key not in _COMPARISON_KEYS}
    measured: dict[str, object] = {"release": release, "commit": commit}
    if target is not None:
        measured["target"] = target
    if REJUDGED_FROM_KEY in copied:
        copied.setdefault(JUDGED_IN_KEY, dict(measured))
    copied.setdefault(MEASURED_IN_KEY, measured)
    return copied


def merge_carried(
    metrics: Mapping[str, Any],
    plan: CarryPlan,
    rejudged: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    """The fresh record ``metrics`` completed with ``plan``'s carried and the ``rejudged`` entries.

    The summary is folded from every entry, with ``rerun``, ``carried`` and
    ``rejudged`` counts; ``tokens`` and ``cost_usd`` stay the fresh runs' own
    (a re-judged entry ran no agent, spec D9).

    Example::

        >>> merge_carried(fresh, plan)["summary"]["carried"]  # doctest: +SKIP
        97
    """
    fresh: Mapping[str, Any] = metrics["samples"]
    regraded = rejudged or {}
    samples = dict(sorted({**fresh, **regraded, **plan.carried}.items()))
    summary = entries_summary(samples) | {
        "tokens": metrics["summary"]["tokens"],
        "cost_usd": metrics["summary"]["cost_usd"],
        "rerun": len(fresh),
        "carried": len(plan.carried),
        "rejudged": len(regraded),
    }
    target = dict(metrics["target"])
    if target["reported_model"] is None and (plan.carried or regraded):
        target["reported_model"] = plan.reported_model
    return {**metrics, "target": target, "summary": summary, "samples": samples}


def carry_plan_lines(plan: CarryPlan, *, controls: Sequence[str]) -> list[str]:
    """The plan printed before the first paid run: a headline, then each rerun with its reason.

    ``controls`` are the ids of the pinned samples, whose edition controls rerun.
    A plan with ``sources`` (``evals.result_index``) ends with one
    ``carried from <source>: <n>`` line per source, then one
    ``rejudged from <source>: <n>`` line per source of ``rejudge``, each sorted.

    Example::

        >>> carry_plan_lines(CarryPlan(None, {"a": "new sample"}, {}), controls=[])
        ['carry plan: 1 rerun, 0 carried', '  a: new sample']
    """
    extra = f" (+{len(controls)} edition controls rerun)" if controls else ""
    rejudged = f", {len(plan.rejudge)} rejudged" if plan.rejudge else ""
    counts = f"{len(plan.rerun)} rerun, {len(plan.carried)} carried{rejudged}{extra}"
    if plan.full_rerun_reason is not None:
        return [f"carry plan: every sample reruns, {plan.full_rerun_reason}: {counts}"]
    lines = [f"carry plan: {counts}"]
    lines += [f"  {sample_id}: {why}" for sample_id, why in plan.rerun.items()]
    lines += [f"  {sample_id} (edition control): {_CONTROL}" for sample_id in controls]
    counts_by_source = Counter(plan.sources.values())
    lines += [f"  carried from {src}: {n}" for src, n in sorted(counts_by_source.items())]
    rejudged_by_source = Counter(source.label for source in plan.rejudge.values())
    lines += [f"  rejudged from {src}: {n}" for src, n in sorted(rejudged_by_source.items())]
    return lines
