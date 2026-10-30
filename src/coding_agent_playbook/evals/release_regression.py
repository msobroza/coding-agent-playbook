"""Check a release metrics file for regressions against the previous release's (ticket 08).

Both files are the same Eval target's, schema version 1
(``evals.release_metrics_schema``). Per sample, by ``--compare``'s own rule
(``evals.comparison.regression_reasons``): a mean score drop above
``MAX_SCORE_DROP`` (0.05), or passing most runs before and failing most now, is a
``regression``; the mirror is an ``improvement``. A sample whose ``sample_digest``
changed is ``not_comparable``, and one the baseline lacks is ``new``. A harness
version change is noted as a likely cause, and a cost rise above 25% (tokens per
run when either cost is ``null``) is a warning only.

The ``controls`` (pinned samples run on their frozen editions, #281 ticket 15)
never block: a control that regressed or improved against the baseline's control
on the same edition is noted, because its text did not change and the model or
harness must have.

A *carried entry* (``measured_in``, copied by ``eval --record --carry-from``,
#329 ticket 06) is ``carried`` when its inputs digest equals the baseline
entry's: it was not measured again. Its ``vs_previous`` holds the previous mean
and a delta of 0, it never blocks, and an ``--accept`` naming it is refused like
any sample that did not regress. One whose digest differs (carried from an
older release, e.g. after a revert, release-metric-artifacts D2) is compared
like a rerun, with ``measured in <release>`` among its reasons, so a regression
blocks; one the baseline lacks is ``new``. The annotated summary counts the
``rerun`` and ``carried`` entries by ``measured_in``, as the record run wrote
them, not by verdict.

An entry *re-judged in this file* (``evals.release_metrics_schema.rejudged_here``:
``rejudged_from`` without ``judged_in``, release-metric-artifacts D9) is read
before ``measured_in``, which it also has. With the previous entry's inputs
digest, or no previous entry, it is ``rejudged``: it never blocks, and its delta
is the new judge's mean minus the previous entry's, the judge effect alone
(D11); ``--accept`` refuses it like ``carried``. With another inputs digest (it
was re-judged from a release older than the baseline, e.g. after a revert) it
is compared like a rerun, with ``rejudged from <release>`` among its reasons,
and can block. An entry carried after a re-judge (it has ``judged_in``) is a
carried entry under the rules above. When the new file records
``judge_change``, every compared sample notes ``judge changed since <previous>:
pass agreement <x>%``. The annotated summary counts ``rejudged`` entries by
:func:`~coding_agent_playbook.evals.release_metrics_schema.rejudged_here`,
apart from the ``carried`` ones.

A regression is *accepted* with a reason; :func:`annotate_release_metrics`
stores it in the new file (``samples.<id>.vs_previous.accepted``), so a rerun
against the same baseline keeps it. The check is *blocked* while any regression
is unaccepted. ``scripts/release.py prepare --eval`` calls :func:`check_regressions`
too, so this module is pure: it reads and returns data, the caller does the I/O.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.evals.comparison import (
    SideSummary,
    improvement_reasons,
    regression_reasons,
)
from coding_agent_playbook.evals.release_metrics_schema import (
    CONTROLS_KEY,
    INPUTS_DIGEST_KEY,
    JUDGE_CHANGE_KEY,
    MEASURED_IN_KEY,
    REJUDGED_FROM_KEY,
    rejudged_here,
)
from coding_agent_playbook.exit_two import ExitTwoError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

type SampleStatus = Literal[
    "ok", "improvement", "regression", "not_comparable", "new", "carried", "rejudged"
]
type _Entry = Mapping[str, object]

#: A cost (or token) rise above this fraction of the previous release's is a warning.
MAX_COST_RISE: Final = 0.25
_DIGITS: Final = 6
#: Verdicts compared with the previous entry, which a judge change note qualifies (D11).
_COMPARED: Final = frozenset({"ok", "improvement", "regression", "not_comparable"})


class RegressionCheckError(ExitTwoError):
    """Two files that cannot be compared, or an ``accept`` that names no regression.

    Example::

        >>> str(RegressionCheckError("target 'a' is not 'b'"))
        "target 'a' is not 'b'"
    """


@dataclass(frozen=True)
class SampleVerdict:
    """One sample's verdict against the previous release.

    ``previous_mean`` and ``delta`` are ``None`` for a ``new`` sample (and a
    ``rejudged`` one without a previous entry), and ``delta`` is 0 for a
    ``carried`` one. A ``rejudged`` sample was re-judged in this file
    (``rejudged_here``) on the previous entry's inputs, so its delta is the judge
    effect. ``accepted`` is the reason a regression was accepted, else ``None``.
    """

    sample_id: str
    status: SampleStatus
    previous_mean: float | None
    mean: float
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    accepted: str | None = None

    @property
    def delta(self) -> float | None:
        """The new mean minus the previous one (``None`` without a previous one, 0 if carried)."""
        if self.status == "carried":
            return 0.0
        if self.previous_mean is None:
            return None
        return round(self.mean - self.previous_mean, _DIGITS)

    @property
    def blocks(self) -> bool:
        """Whether this sample blocks the release: a regression nobody accepted."""
        return self.status == "regression" and self.accepted is None


@dataclass(frozen=True)
class RegressionCheck:
    """The verdict of a new release metrics file against the previous release's.

    Example::

        >>> check_regressions(new_file, old_file).blocked  # doctest: +SKIP
        False
    """

    release: str
    previous: str
    target: str
    samples: tuple[SampleVerdict, ...]
    notes: tuple[str, ...] = ()

    @property
    def blocked(self) -> bool:
        """Whether any regression is unaccepted (the CLI then exits ``1``)."""
        return any(verdict.blocks for verdict in self.samples)

    def count(self, status: SampleStatus) -> int:
        """How many samples have ``status``."""
        return sum(1 for verdict in self.samples if verdict.status == status)

    @property
    def accepted_regressions(self) -> int:
        """How many regressions carry an accepted reason."""
        return sum(1 for v in self.samples if v.status == "regression" and v.accepted)


def check_regressions(
    new: Mapping[str, object],
    baseline: Mapping[str, object],
    accepted: Mapping[str, str] | None = None,
) -> RegressionCheck:
    """Compare ``new`` with ``baseline`` (both validated release metrics files).

    ``accepted`` maps a sample id to the reason its regression is accepted; it
    overrides a reason ``new`` already stores against this baseline. Raises
    :class:`RegressionCheckError` when the targets differ or an accepted sample
    did not regress.

    Example::

        >>> check = check_regressions(new_file, old_file, accepted={"s": "stricter rubric"})  # doctest: +SKIP
        >>> check.blocked  # doctest: +SKIP
        False
    """
    target = _same_target(new, baseline)
    previous = str(baseline["release"])
    reasons = {**_stored_acceptances(new, previous), **(accepted or {})}
    new_samples, old_samples = _samples(new), _samples(baseline)
    verdicts = tuple(
        _verdict(sample_id, entry, old_samples.get(sample_id), str(new["release"]))
        for sample_id, entry in sorted(new_samples.items())
    )
    verdicts = _note_judge_change(verdicts, new, previous)
    verdicts = _accept(verdicts, reasons, accepted or {})
    notes = (
        _harness_notes(new, baseline)
        + _dropped_notes(new_samples, old_samples)
        + _control_notes(new, baseline, str(new["release"]))
    )
    return RegressionCheck(str(new["release"]), previous, target, verdicts, notes)


def parse_acceptances(values: Sequence[str]) -> dict[str, str]:
    """``SAMPLE=REASON`` values (``--accept``) by sample; refuse one without a sample or a reason.

    Example::

        >>> parse_acceptances(["review/x=the rubric is stricter"])
        {'review/x': 'the rubric is stricter'}
    """
    accepted: dict[str, str] = {}
    for value in values:
        sample_id, _, reason = value.partition("=")
        if not sample_id.strip() or not reason.strip():
            raise RegressionCheckError(f"--accept expects SAMPLE=REASON, got {value!r}")
        accepted[sample_id.strip()] = reason.strip()
    return accepted


def annotate_release_metrics(
    new: Mapping[str, object], check: RegressionCheck
) -> dict[str, object]:
    """A copy of ``new`` with ``previous``, each ``vs_previous`` and the summary counts.

    Example::

        >>> annotate_release_metrics(new_file, check)["previous"]  # doctest: +SKIP
        '9.9.8'
    """
    annotated = copy.deepcopy(dict(new))
    annotated["previous"] = check.previous
    samples = annotated["samples"]
    assert isinstance(samples, dict)  # validated by the caller
    for verdict in check.samples:
        samples[verdict.sample_id]["vs_previous"] = verdict_to_dict(verdict, with_id=False)
    summary = annotated["summary"]
    assert isinstance(summary, dict)
    summary["regressions"] = check.count("regression")
    summary["accepted_regressions"] = check.accepted_regressions
    summary["improvements"] = check.count("improvement")
    summary["not_comparable"] = check.count("not_comparable")
    rejudged = sum(1 for entry in samples.values() if rejudged_here(entry))
    carried = sum(1 for e in samples.values() if MEASURED_IN_KEY in e and not rejudged_here(e))
    summary["rerun"] = len(samples) - carried - rejudged
    summary["carried"] = carried
    summary["rejudged"] = rejudged
    return annotated


def verdict_to_dict(verdict: SampleVerdict, *, with_id: bool = True) -> dict[str, object]:
    """The JSON view of one verdict (``vs_previous`` in the file, without the id)."""
    view: dict[str, object] = {"sample_id": verdict.sample_id} if with_id else {}
    view |= {"mean_score": verdict.previous_mean, "delta": verdict.delta, "status": verdict.status}
    if verdict.reasons:
        view["reasons"] = list(verdict.reasons)
    if verdict.warnings:
        view["warnings"] = list(verdict.warnings)
    if verdict.accepted is not None:
        view["accepted"] = verdict.accepted
    return view


def _same_target(new: Mapping[str, object], baseline: Mapping[str, object]) -> str:
    new_name, old_name = _target(new).get("name"), _target(baseline).get("name")
    if new_name != old_name:
        raise RegressionCheckError(
            f"the new file is for target {new_name!r} but the baseline is for "
            f"{old_name!r}; compare files of the same target"
        )
    return str(new_name)


def _verdict(sample_id: str, entry: _Entry, old: _Entry | None, release: str) -> SampleVerdict:
    if rejudged_here(entry):
        return _rejudged_verdict(sample_id, entry, old, release)
    mean = _num(entry["mean_score"])
    if old is None:
        return SampleVerdict(sample_id, "new", None, mean)
    if MEASURED_IN_KEY not in entry:
        return _compared_verdict(sample_id, entry, old, release)
    if _same_inputs(entry, old):
        return SampleVerdict(sample_id, "carried", _num(old["mean_score"]), mean)
    verdict = _compared_verdict(sample_id, entry, old, release)
    return _add_reason(verdict, f"measured in {_measured_in(entry)}")


def _same_inputs(entry: _Entry, old: _Entry) -> bool:
    return entry.get(INPUTS_DIGEST_KEY) == old.get(INPUTS_DIGEST_KEY)


def _add_reason(verdict: SampleVerdict, reason: str) -> SampleVerdict:
    return replace(verdict, reasons=(*verdict.reasons, reason))


def _compared_verdict(sample_id: str, entry: _Entry, old: _Entry, release: str) -> SampleVerdict:
    """``entry`` against the baseline's ``old`` by ``--compare``'s rule."""
    mean = _num(entry["mean_score"])
    previous_mean = _num(old["mean_score"])
    if entry["sample_digest"] != old["sample_digest"]:
        reason = ("sample digest changed: the sample itself was edited",)
        return SampleVerdict(sample_id, "not_comparable", previous_mean, mean, reason)
    before, now = _side(old), _side(entry)
    warnings = _cost_warnings(entry, old)
    regressed = regression_reasons(before, now, release)
    if regressed:
        return SampleVerdict(sample_id, "regression", previous_mean, mean, regressed, warnings)
    improved = improvement_reasons(before, now)
    status: SampleStatus = "improvement" if improved else "ok"
    return SampleVerdict(sample_id, status, previous_mean, mean, improved, warnings)


def _rejudged_verdict(
    sample_id: str, entry: _Entry, old: _Entry | None, release: str
) -> SampleVerdict:
    """``rejudged`` on the previous entry's inputs (delta = judge effect), else compared (D11)."""
    rejudged_from = entry[REJUDGED_FROM_KEY]
    source = rejudged_from.get("release") if isinstance(rejudged_from, dict) else rejudged_from
    reason = f"rejudged from {source}"
    mean = _num(entry["mean_score"])
    if old is None:
        return SampleVerdict(sample_id, "rejudged", None, mean, (reason,))
    if _same_inputs(entry, old):
        return SampleVerdict(sample_id, "rejudged", _num(old["mean_score"]), mean, (reason,))
    return _add_reason(_compared_verdict(sample_id, entry, old, release), reason)


def _note_judge_change(
    verdicts: tuple[SampleVerdict, ...], new: Mapping[str, object], previous: str
) -> tuple[SampleVerdict, ...]:
    """Each compared verdict with the judge change note, when ``new`` records ``judge_change``."""
    change = new.get(JUDGE_CHANGE_KEY)
    if not isinstance(change, dict):
        return verdicts
    agreement = round(_num(change["pass_agreement"]) * 100)
    note = f"judge changed since {previous}: pass agreement {agreement}%"
    return tuple(_add_reason(v, note) if v.status in _COMPARED else v for v in verdicts)


def _measured_in(entry: _Entry) -> str:
    """The release a carried entry was measured in (``measured_in.release``)."""
    measured_in = entry[MEASURED_IN_KEY]
    return str(measured_in.get("release")) if isinstance(measured_in, dict) else str(measured_in)


def _accept(
    verdicts: tuple[SampleVerdict, ...], reasons: Mapping[str, str], requested: Mapping[str, str]
) -> tuple[SampleVerdict, ...]:
    """``verdicts`` with each regression's accepted reason; refuse a request for a non-regression."""
    regressions = {v.sample_id for v in verdicts if v.status == "regression"}
    stray = sorted(set(requested) - regressions)
    if stray:
        raise RegressionCheckError(
            f"cannot accept {', '.join(repr(s) for s in stray)}: it did not regress "
            f"against this baseline (regressions: {', '.join(sorted(regressions)) or 'none'})"
        )
    return tuple(
        _with_reason(v, reasons.get(v.sample_id)) if v.sample_id in regressions else v
        for v in verdicts
    )


def _with_reason(verdict: SampleVerdict, reason: str | None) -> SampleVerdict:
    return verdict if reason is None else replace(verdict, accepted=reason)


def _stored_acceptances(new: Mapping[str, object], previous: str) -> dict[str, str]:
    """The reasons ``new`` already stores, when it was last checked against ``previous``."""
    if new.get("previous") != previous:
        return {}
    stored: dict[str, str] = {}
    for sample_id, entry in _samples(new).items():
        vs_previous = entry.get("vs_previous")
        reason = vs_previous.get("accepted") if isinstance(vs_previous, dict) else None
        if isinstance(reason, str):
            stored[sample_id] = reason
    return stored


def _cost_warnings(entry: _Entry, old: _Entry) -> tuple[str, ...]:
    """A cost rise above :data:`MAX_COST_RISE`, or a token rise when either cost is ``null``."""
    cost, old_cost = entry.get("cost_usd_mean"), old.get("cost_usd_mean")
    if isinstance(cost, int | float) and isinstance(old_cost, int | float):
        rise = _rise(cost, old_cost)
        return (f"cost per run rises {rise:.0%} ({old_cost:g} -> {cost:g} USD)",) if rise else ()
    tokens, old_tokens = entry.get("tokens_mean"), old.get("tokens_mean")
    if isinstance(tokens, int | float) and isinstance(old_tokens, int | float):
        rise = _rise(tokens, old_tokens)
        return (f"tokens per run rise {rise:.0%} ({old_tokens:g} -> {tokens:g})",) if rise else ()
    return ()


def _rise(now: float, before: float) -> float | None:
    """The fractional rise from ``before`` to ``now`` when above the threshold, else ``None``."""
    if before <= 0:
        return None
    rise = round((now - before) / before, _DIGITS)
    return rise if rise > MAX_COST_RISE else None


def _harness_notes(new: Mapping[str, object], baseline: Mapping[str, object]) -> tuple[str, ...]:
    now, before = _target(new).get("harness_version"), _target(baseline).get("harness_version")
    if now == before:
        return ()
    return (f"harness version changed {before} -> {now}: a likely cause of score changes",)


def _dropped_notes(new: Mapping[str, _Entry], old: Mapping[str, _Entry]) -> tuple[str, ...]:
    return tuple(
        f"sample {sample_id!r} is in the baseline but not in the new file"
        for sample_id in sorted(set(old) - set(new))
    )


def _control_notes(
    new: Mapping[str, object], baseline: Mapping[str, object], release: str
) -> tuple[str, ...]:
    """A note per control whose score moved on an unchanged edition and sample."""
    old_controls = _samples(baseline, CONTROLS_KEY)
    notes = []
    for sample_id, entry in sorted(_samples(new, CONTROLS_KEY).items()):
        old = old_controls.get(sample_id)
        same = old is not None and all(entry[k] == old[k] for k in ("graded", "sample_digest"))
        if old is None or not same:
            continue
        before, now = _side(old), _side(entry)
        moved = regression_reasons(before, now, release) or improvement_reasons(before, now)
        if moved:
            notes.append(
                f"control {sample_id!r} on frozen edition {entry['graded']} moved "
                f"({'; '.join(moved)}): its text is unchanged, so the model or harness drifted"
            )
    return tuple(notes)


def _side(entry: _Entry) -> SideSummary:
    """A file entry as ``--compare``'s per-side summary: passes of runs, mean and spread."""
    return SideSummary(
        count=int(_num(entry["runs"])),
        passes=int(_num(entry["passes"])),
        mean=_num(entry["mean_score"]),
        spread=_num(entry["stdev"]),
    )


def _target(data: Mapping[str, object]) -> Mapping[str, object]:
    target = data.get("target")
    return target if isinstance(target, dict) else {}


def _samples(data: Mapping[str, object], key: str = "samples") -> dict[str, _Entry]:
    samples = data.get(key)
    return dict(samples) if isinstance(samples, dict) else {}


def _num(value: object) -> float:
    if not isinstance(value, int | float):
        raise RegressionCheckError(f"expected a number, got {value!r}")
    return float(value)
