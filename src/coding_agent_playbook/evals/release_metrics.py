"""Build one release metrics file from the runs of every sample on one Eval target (ticket 07).

``playbook eval --run --all --runs N --record <path>`` runs each sample ``N``
times and hands the results here; :func:`build_release_metrics` folds them into
the shape :mod:`~coding_agent_playbook.evals.release_metrics_schema` documents
(schema version 1). Nothing here runs an agent, so tests build a file from
fake results.

Per sample it records passes out of runs, the mean and the population standard
deviation of the sample score, the mean score of each check that ran, the mean
duration, the mean tokens and the mean cost. Cost comes only from the target's
``price``; without one, or when a run reported no tokens, it is ``null``.

A pinned sample also runs on its edition as a **control** (#281 ticket 15): those
runs go under ``controls`` in the same per-sample shape, with ``graded`` the
edition tag, and stay out of the summary, which scores the current text only.

Fresh and ``--carry-from`` records (#329 ticket 05, ``evals.release_carry``)
both fold the summary's sample, run, pass-rate and mean-score keys from the
recorded entries (:func:`entries_summary`), so a carried entry counts exactly as
it did when it was measured; ``tokens`` and ``cost_usd`` count fresh runs only.
A re-judged sample (spec D9) folds its re-scored runs through the same
:func:`fold_outcomes` as a fresh one (:func:`rejudged_record`).
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.evals.answers_store import run_to_json
from coding_agent_playbook.evals.release_metrics_schema import (
    CONTROLS_KEY,
    INPUTS_DIGEST_KEY,
    ISOLATED_KEY,
    SCHEMA_VERSION,
    SETUP_DIGEST_KEY,
    SETUP_KEY,
)
from coding_agent_playbook.grading.types import CheckResult

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence

    from coding_agent_playbook.evals.answers_store import StoredRun
    from coding_agent_playbook.evals.run.harness_runner import SampleResult
    from coding_agent_playbook.evals.setup_digest import SetupParts
    from coding_agent_playbook.evals.targets import EvalTarget
    from coding_agent_playbook.evals.token_usage import TokenPrice

#: The graded source of a sample that grades the current text (editions come with pins).
GRADED_HEAD: Final = "head"
#: Digits kept in recorded means, so files diff cleanly across machines.
_DIGITS: Final = 6
#: Entry keys that describe the agent's runs, which a re-judged entry keeps from its source.
_AGENT_RUN_KEYS: Final = ("duration_seconds_mean", "tokens_mean", "cost_usd_mean")


@dataclass(frozen=True)
class SampleRuns:
    """Every run of one sample, with the digests of what was graded.

    ``graded`` is :data:`GRADED_HEAD` or an edition tag. ``inputs_digest``
    (``evals.sample_digest.inputs_digest``, #329 ticket 03) covers what the agent
    received; ``None`` leaves the key out of the entry. ``answers`` holds each
    run's answers line (spec D8), empty for an edition control.

    Example::

        >>> SampleRuns("review/x", "review", GRADED_HEAD, None, "ab12", results=[]).runs
        0
    """

    sample_id: str
    prompt_id: str
    graded: str
    prompt_digest: str | None
    sample_digest: str
    results: Sequence[SampleResult]
    inputs_digest: str | None = None
    answers: tuple[StoredRun, ...] = ()

    @property
    def runs(self) -> int:
        """How many times the sample ran."""
        return len(self.results)


@dataclass(frozen=True)
class RecordedTarget:
    """The target block's facts that do not come from the runs themselves.

    ``isolated`` says the harness and the judge ran without the user's personal
    settings (#329 ticket 02); ``None`` leaves the key out of the block.
    ``setup`` is the record's setup parts (#329 ticket 04), written as the
    file's ``setup_digest`` and ``setup``; ``None`` leaves both keys out.

    Example::

        >>> RecordedTarget(EvalTarget("t", "fake", "m"), None, None, runs=3).runs
        3
    """

    target: EvalTarget
    harness_version: str | None
    judge_model: str | None
    runs: int
    isolated: bool | None = None
    setup: SetupParts | None = None


def build_release_metrics(
    *,
    release: str,
    commit: str | None,
    recorded: RecordedTarget,
    samples: Sequence[SampleRuns],
    controls: Sequence[SampleRuns] = (),
) -> dict[str, object]:
    """The release metrics file of ``samples`` on ``recorded``'s target, as JSON-ready data.

    ``controls`` are the pinned samples' runs on their editions: ``controls`` in
    the file, left out of the summary.

    Example::

        >>> build_release_metrics(release="9.9.9", commit=None, recorded=r, samples=[])["summary"]  # doctest: +SKIP
        {'samples': 0, 'runs': 0, 'pass_rate': 0.0, 'mean_score': None, 'tokens': 0, 'cost_usd': ...}
    """
    price = recorded.target.price
    return build_release_metrics_from_records(
        release=release,
        commit=commit,
        recorded=recorded,
        samples=[sample_record(runs, price) for runs in samples],
        controls=[sample_record(runs, price) for runs in controls],
    )


def build_release_metrics_from_records(
    *,
    release: str,
    commit: str | None,
    recorded: RecordedTarget,
    samples: Sequence[SampleRecord],
    controls: Sequence[SampleRecord] = (),
) -> dict[str, object]:
    """The release metrics file of already-folded sample records (see :func:`sample_record`).

    A record read back from a checkpoint (``evals.record_checkpoint``) folds
    exactly as the runs it came from, so a resumed record writes the same file.

    Example::

        >>> build_release_metrics_from_records(release="9.9.9", commit=None, recorded=r, samples=[])  # doctest: +SKIP
    """
    ordered = sorted(samples, key=_record_id)
    entries = {record.sample_id: dict(record.entry) for record in ordered}
    control_entries = {record.sample_id: dict(record.entry) for record in controls}
    return _setup_keys(recorded.setup) | {
        "schema_version": SCHEMA_VERSION,
        "release": release,
        "previous": None,
        "commit": commit,
        "target": _target_block(recorded, ordered),
        # One fold for fresh and carried records, so carrying an entry never moves the summary.
        "summary": entries_summary(entries) | _fresh_totals(ordered, recorded.target.price),
        "samples": entries,
        CONTROLS_KEY: dict(sorted(control_entries.items())),
    }


@dataclass(frozen=True)
class SampleRecord:
    """One sample's file entry and the per-run facts the file's totals fold over.

    JSON-ready, so a checkpoint can store it and fold it later as if it had just
    run: ``run_tokens`` and ``run_costs`` (``None``: unknown) feed the summary's
    ``tokens`` and ``cost_usd``, ``reported_models`` the target's ``reported_model``.
    ``answers`` are the runs' answers lines in their JSON form
    (``evals.answers_store.run_to_json``), so a resumed record still writes them.

    Example::

        >>> SampleRecord("review/x", {"runs": 0}, (), (), ()).sample_id
        'review/x'
    """

    sample_id: str
    entry: Mapping[str, object]
    run_tokens: tuple[int | None, ...]
    run_costs: tuple[float | None, ...]
    reported_models: tuple[str, ...]
    answers: tuple[Mapping[str, object], ...] = ()


def sample_record(runs: SampleRuns, price: TokenPrice | None) -> SampleRecord:
    """``runs`` folded into its file entry and the per-run facts the totals need.

    Example::

        >>> sample_record(SampleRuns("review/x", "review", "head", None, "ab12", []), None).run_tokens
        ()
    """
    results = runs.results
    return SampleRecord(
        sample_id=runs.sample_id,
        entry=_sample_entry(runs, price),
        run_tokens=tuple(_run_tokens(results)),
        run_costs=tuple(_run_costs(results, price)),
        reported_models=tuple(r.reported_model for r in results if r.reported_model is not None),
        answers=tuple(run_to_json(stored) for stored in runs.answers),
    )


@dataclass(frozen=True)
class RunOutcome:
    """One run's verdict, sample score and check scores: what an entry folds per run.

    Example::

        >>> RunOutcome(True, 1.0, {"gate": 1.0}).passed
        True
    """

    passed: bool
    score: float
    checks: Mapping[str, float]


def rejudged_record(
    runs: SampleRuns,
    outcomes: Sequence[RunOutcome],
    source_entry: Mapping[str, Any],
    provenance: Mapping[str, object],
) -> SampleRecord:
    """A re-judged sample's record (spec D9), folded like a fresh one from its ``outcomes``.

    ``runs`` gives the entry's identity and the new answers lines (its
    ``results`` are empty). No agent ran, so the duration, tokens and cost means
    are ``source_entry``'s and the record adds no tokens or cost to the summary.
    ``provenance`` adds ``rejudged_from`` and ``measured_in``.

    Example::

        >>> rejudged_record(runs, outcomes, entry, {"measured_in": {}}).run_tokens  # doctest: +SKIP
        ()
    """
    kept = {key: source_entry[key] for key in _AGENT_RUN_KEYS}
    entry = _entry_identity(runs) | fold_outcomes(outcomes) | kept | dict(provenance)
    answers = tuple(run_to_json(stored) for stored in runs.answers)
    return SampleRecord(runs.sample_id, entry, (), (), (), answers)


def fold_outcomes(outcomes: Sequence[RunOutcome]) -> dict[str, object]:
    """An entry's passes, runs, mean score, score stdev and check means over ``outcomes``.

    Example::

        >>> fold_outcomes([RunOutcome(True, 1.0, {"gate": 1.0})])["passes"]
        1
    """
    scores = [outcome.score for outcome in outcomes]
    return {
        "passes": sum(1 for outcome in outcomes if outcome.passed),
        "runs": len(outcomes),
        "mean_score": _round(_mean(scores)),
        "stdev": _round(statistics.pstdev(scores)) if scores else 0.0,
        "checks": _check_means([outcome.checks for outcome in outcomes]),
    }


def _record_id(record: SampleRecord) -> str:
    return record.sample_id


def _setup_keys(setup: SetupParts | None) -> dict[str, object]:
    """The file's ``setup_digest`` and ``setup`` parts; none without setup parts."""
    if setup is None:
        return {}
    return {SETUP_DIGEST_KEY: setup.digest, SETUP_KEY: setup.as_dict()}


def _target_block(recorded: RecordedTarget, samples: Sequence[SampleRecord]) -> dict[str, object]:
    target = recorded.target
    price = target.price
    isolation = {} if recorded.isolated is None else {ISOLATED_KEY: recorded.isolated}
    return isolation | {
        "name": target.name,
        "harness": target.harness,
        "harness_version": recorded.harness_version,
        "model": target.model,
        "reported_model": _most_reported_model(samples),
        "label": target.label,
        # The endpoint's name and URL fingerprint, never the URL or the token.
        "endpoint": (
            {"name": target.endpoint.name, "fingerprint": target.endpoint.fingerprint}
            if target.endpoint is not None
            else None
        ),
        "price": (
            {"input": price.input_per_million, "output": price.output_per_million}
            if price is not None
            else None
        ),
        "judge_model": recorded.judge_model,
        "runs": recorded.runs,
    }


def _most_reported_model(samples: Sequence[SampleRecord]) -> str | None:
    """The model the harness reported most often over every run (``None``: it reported none)."""
    reported = Counter(model for record in samples for model in record.reported_models)
    return reported.most_common(1)[0][0] if reported else None


def _sample_entry(runs: SampleRuns, price: TokenPrice | None) -> dict[str, object]:
    results = runs.results
    outcomes = [
        RunOutcome(result.passed, result.aggregate_score, run_check_scores(result))
        for result in results
    ]
    return (
        _entry_identity(runs)
        | fold_outcomes(outcomes)
        | {
            "duration_seconds_mean": _round(_mean([r.duration_seconds for r in results])),
            "tokens_mean": _round_or_none(_mean_or_none(_run_tokens(results))),
            "cost_usd_mean": _round_or_none(_mean_or_none(_run_costs(results, price))),
        }
    )


def _entry_identity(runs: SampleRuns) -> dict[str, object]:
    """The entry's prompt, graded source and digests."""
    inputs = {} if runs.inputs_digest is None else {INPUTS_DIGEST_KEY: runs.inputs_digest}
    return inputs | {
        "prompt_id": runs.prompt_id,
        "graded": runs.graded,
        "prompt_digest": runs.prompt_digest,
        "sample_digest": runs.sample_digest,
    }


def _fresh_totals(samples: Sequence[SampleRecord], price: TokenPrice | None) -> dict[str, object]:
    """The summary's ``tokens`` and ``cost_usd`` over every fresh run.

    ``cost_usd`` stays ``null`` without a price even when nothing ran: an
    unpriced target's cost is unknown, not zero.
    """
    tokens = _total_or_none([value for record in samples for value in record.run_tokens])
    costs = [value for record in samples for value in record.run_costs]
    cost = _total_or_none(costs) if price is not None else None
    return {
        "tokens": int(tokens) if tokens is not None else None,
        "cost_usd": _round_or_none(cost),
    }


def entries_summary(entries: Mapping[str, Mapping[str, Any]]) -> dict[str, object]:
    """The summary's sample, run, pass-rate and mean-score keys, folded from recorded entries.

    The same semantics as a fresh record's summary: ``pass_rate`` pools the
    passes of every run, ``mean_score`` is the mean of the per-sample means. A
    ``--carry-from`` record (#329 ticket 05) folds fresh and carried entries
    alike, so its headline numbers stay comparable across releases.

    Example::

        >>> entries_summary({"a": {"passes": 1, "runs": 2, "mean_score": 0.5}})
        {'samples': 1, 'runs': 2, 'pass_rate': 0.5, 'mean_score': 0.5}
    """
    runs = sum(int(entry["runs"]) for entry in entries.values())
    passes = sum(int(entry["passes"]) for entry in entries.values())
    means = [float(entry["mean_score"]) for entry in entries.values()]
    return {
        "samples": len(entries),
        "runs": runs,
        "pass_rate": _round(passes / runs) if runs else 0.0,
        "mean_score": _round(_mean(means)) if means else None,
    }


def _run_tokens(results: Sequence[SampleResult]) -> list[int | None]:
    return [result.usage.total if result.usage is not None else None for result in results]


def _run_costs(results: Sequence[SampleResult], price: TokenPrice | None) -> list[float | None]:
    """Each run's cost at ``price``: ``None`` without a price or without reported tokens."""
    if price is None:
        return [None] * len(results)
    return [price.cost_usd(r.usage) if r.usage is not None else None for r in results]


def _check_means(runs: Sequence[Mapping[str, float]]) -> dict[str, float]:
    """The mean score of each check over the runs it ran in, by check id."""
    scores: dict[str, list[float]] = {}
    for checks in runs:
        for check_id, score in checks.items():
            scores.setdefault(check_id, []).append(score)
    return {check_id: _round(_mean(values)) for check_id, values in sorted(scores.items())}


def run_check_scores(result: SampleResult) -> dict[str, float]:
    """One run's score per check: its layers and their leaf checks, skipped ones left out.

    A check without a score counts as its verdict (``1.0`` passed, ``0.0`` failed).
    A composed check between a layer and its leaves repeats the layer, so it is skipped.

    Example::

        >>> run_check_scores(result)  # doctest: +SKIP
        {'file-exists': 1.0, 'tests': 0.5}
    """
    return report_check_scores(result.report.checks)


def report_check_scores(layers: Iterable[CheckResult]) -> dict[str, float]:
    """:func:`run_check_scores` over a report's layer results, for a report with no run.

    Example::

        >>> report_check_scores(report.checks)  # doctest: +SKIP
        {'gate': 1.0, 'file-exists': 1.0}
    """
    scores: dict[str, float] = {}
    for layer in layers:
        for check in (layer, *_leaves(layer)):
            if check.status == "run" and check.check_id not in scores:
                scores[check.check_id] = (
                    check.score if check.score is not None else float(check.passed)
                )
    return scores


def _leaves(check: CheckResult) -> Iterator[CheckResult]:
    children = [sub for sub in check.subresults if isinstance(sub, CheckResult)]
    for child in children:
        nested = [sub for sub in child.subresults if isinstance(sub, CheckResult)]
        if nested:
            yield from _leaves(child)
        else:
            yield child


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _mean_or_none(values: Sequence[float | None]) -> float | None:
    """The mean, or ``None`` when there are no values or any is unknown."""
    known = [value for value in values if value is not None]
    if not values or len(known) != len(values):
        return None
    return statistics.fmean(known)


def _total_or_none(values: Sequence[float | None]) -> float | None:
    """The sum, or ``None`` when any value is unknown (a partial sum would undercount)."""
    known = [value for value in values if value is not None]
    return sum(known) if len(known) == len(values) else None


def _round(value: float) -> float:
    return round(value, _DIGITS)


def _round_or_none(value: float | None) -> float | None:
    return _round(value) if value is not None else None
