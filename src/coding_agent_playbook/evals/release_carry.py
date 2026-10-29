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
``rerun`` and ``carried`` counts; ``tokens`` and ``cost_usd`` stay the fresh
runs' own. Nothing here runs an agent.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.evals.release_metrics import entries_summary
from coding_agent_playbook.evals.release_metrics_schema import (
    INPUTS_DIGEST_KEY,
    MEASURED_IN_KEY,
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
class CarryPlan:
    """What a ``--carry-from`` record reruns (by sample id, with the reason) and carries.

    ``full_rerun_reason`` is set when every sample reruns. ``reported_model`` is
    the baseline's, kept when no fresh run reports one. ``sources`` names, by
    sample id, the file each carried entry came from as ``"<release> (<target>)"``
    (``evals.result_index``); a ``--carry-from`` plan leaves it empty.

    Example::

        >>> CarryPlan(None, {"a": "new sample"}, {}).reruns("a")
        True
    """

    full_rerun_reason: str | None
    rerun: Mapping[str, str]
    carried: Mapping[str, Mapping[str, object]]
    reported_model: str | None = None
    sources: Mapping[str, str] = field(default_factory=dict)

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
    entry: Mapping[str, object], *, release: str, commit: str | None
) -> dict[str, object]:
    """``entry`` as carried from the baseline ``release`` at ``commit``.

    Its comparison with its own previous release is dropped, and ``measured_in``
    names where it was measured: kept when the entry was already carried.

    Example::

        >>> carried_entry({"runs": 3}, release="9.9.9", commit=None)
        {'runs': 3, 'measured_in': {'release': '9.9.9', 'commit': None}}
    """
    copied = {key: value for key, value in entry.items() if key not in _COMPARISON_KEYS}
    copied.setdefault(MEASURED_IN_KEY, {"release": release, "commit": commit})
    return copied


def merge_carried(metrics: Mapping[str, Any], plan: CarryPlan) -> dict[str, Any]:
    """The fresh record ``metrics`` completed with ``plan``'s carried entries.

    The summary is folded from every entry, with ``rerun`` and ``carried``
    counts; ``tokens`` and ``cost_usd`` stay the fresh runs' own.

    Example::

        >>> merge_carried(fresh, plan)["summary"]["carried"]  # doctest: +SKIP
        97
    """
    fresh: Mapping[str, Any] = metrics["samples"]
    samples = dict(sorted({**fresh, **plan.carried}.items()))
    summary = entries_summary(samples) | {
        "tokens": metrics["summary"]["tokens"],
        "cost_usd": metrics["summary"]["cost_usd"],
        "rerun": len(fresh),
        "carried": len(plan.carried),
    }
    target = dict(metrics["target"])
    if target["reported_model"] is None and plan.carried:
        target["reported_model"] = plan.reported_model
    return {**metrics, "target": target, "summary": summary, "samples": samples}


def carry_plan_lines(plan: CarryPlan, *, controls: Sequence[str]) -> list[str]:
    """The plan printed before the first paid run: a headline, then each rerun with its reason.

    ``controls`` are the ids of the pinned samples, whose edition controls rerun.
    A plan with ``sources`` (``evals.result_index``) ends with one
    ``carried from <source>: <n>`` line per source, sorted by source.

    Example::

        >>> carry_plan_lines(CarryPlan(None, {"a": "new sample"}, {}), controls=[])
        ['carry plan: 1 rerun, 0 carried', '  a: new sample']
    """
    extra = f" (+{len(controls)} edition controls rerun)" if controls else ""
    counts = f"{len(plan.rerun)} rerun, {len(plan.carried)} carried{extra}"
    if plan.full_rerun_reason is not None:
        return [f"carry plan: every sample reruns, {plan.full_rerun_reason}: {counts}"]
    lines = [f"carry plan: {counts}"]
    lines += [f"  {sample_id}: {why}" for sample_id, why in plan.rerun.items()]
    lines += [f"  {sample_id} (edition control): {_CONTROL}" for sample_id in controls]
    counts_by_source = Counter(plan.sources.values())
    lines += [f"  carried from {src}: {n}" for src, n in sorted(counts_by_source.items())]
    return lines
