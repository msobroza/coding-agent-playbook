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
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

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
    from collections.abc import Iterator, Sequence

    from coding_agent_playbook.evals.run.harness_runner import SampleResult
    from coding_agent_playbook.evals.setup_digest import SetupParts
    from coding_agent_playbook.evals.targets import EvalTarget
    from coding_agent_playbook.evals.token_usage import TokenPrice

#: The graded source of a sample that grades the current text (editions come with pins).
GRADED_HEAD: Final = "head"
#: Digits kept in recorded means, so files diff cleanly across machines.
_DIGITS: Final = 6


@dataclass(frozen=True)
class SampleRuns:
    """Every run of one sample, with the digests of what was graded.

    ``graded`` is :data:`GRADED_HEAD` or an edition tag. ``inputs_digest``
    (``evals.sample_digest.inputs_digest``, #329 ticket 03) covers what the agent
    received; ``None`` leaves the key out of the entry.

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
    entries = {runs.sample_id: _sample_entry(runs, price) for runs in samples}
    control_entries = {runs.sample_id: _sample_entry(runs, price) for runs in controls}
    return _setup_keys(recorded.setup) | {
        "schema_version": SCHEMA_VERSION,
        "release": release,
        "previous": None,
        "commit": commit,
        "target": _target_block(recorded, samples),
        "summary": _summary(samples, price),
        "samples": dict(sorted(entries.items())),
        CONTROLS_KEY: dict(sorted(control_entries.items())),
    }


def _setup_keys(setup: SetupParts | None) -> dict[str, object]:
    """The file's ``setup_digest`` and ``setup`` parts; none without setup parts."""
    if setup is None:
        return {}
    return {SETUP_DIGEST_KEY: setup.digest, SETUP_KEY: setup.as_dict()}


def _target_block(recorded: RecordedTarget, samples: Sequence[SampleRuns]) -> dict[str, object]:
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


def _most_reported_model(samples: Sequence[SampleRuns]) -> str | None:
    """The model the harness reported most often over every run (``None``: it reported none)."""
    reported = Counter(
        result.reported_model
        for runs in samples
        for result in runs.results
        if result.reported_model is not None
    )
    return reported.most_common(1)[0][0] if reported else None


def _sample_entry(runs: SampleRuns, price: TokenPrice | None) -> dict[str, object]:
    results = runs.results
    scores = [result.aggregate_score for result in results]
    inputs = {} if runs.inputs_digest is None else {INPUTS_DIGEST_KEY: runs.inputs_digest}
    return inputs | {
        "prompt_id": runs.prompt_id,
        "graded": runs.graded,
        "prompt_digest": runs.prompt_digest,
        "sample_digest": runs.sample_digest,
        "passes": sum(1 for result in results if result.passed),
        "runs": len(results),
        "mean_score": _round(_mean(scores)),
        "stdev": _round(statistics.pstdev(scores)) if scores else 0.0,
        "checks": _check_means(results),
        "duration_seconds_mean": _round(_mean([r.duration_seconds for r in results])),
        "tokens_mean": _round_or_none(_mean_or_none(_run_tokens(results))),
        "cost_usd_mean": _round_or_none(_mean_or_none(_run_costs(results, price))),
    }


def _summary(samples: Sequence[SampleRuns], price: TokenPrice | None) -> dict[str, object]:
    """Totals over every run; the mean score is the mean of the per-sample means."""
    results = [result for runs in samples for result in runs.results]
    sample_means = [_mean([r.aggregate_score for r in runs.results]) for runs in samples]
    tokens = _total_or_none(_run_tokens(results))
    cost = _total_or_none(_run_costs(results, price))
    return {
        "samples": len(samples),
        "runs": len(results),
        "pass_rate": _round(_mean([float(result.passed) for result in results])),
        "mean_score": _round(_mean(sample_means)) if sample_means else None,
        "tokens": int(tokens) if tokens is not None else None,
        "cost_usd": _round_or_none(cost),
    }


def _run_tokens(results: Sequence[SampleResult]) -> list[int | None]:
    return [result.usage.total if result.usage is not None else None for result in results]


def _run_costs(results: Sequence[SampleResult], price: TokenPrice | None) -> list[float | None]:
    """Each run's cost at ``price``: ``None`` without a price or without reported tokens."""
    if price is None:
        return [None] * len(results)
    return [price.cost_usd(r.usage) if r.usage is not None else None for r in results]


def _check_means(results: Sequence[SampleResult]) -> dict[str, float]:
    """The mean score of each check over the runs it ran in, by check id."""
    scores: dict[str, list[float]] = {}
    for result in results:
        for check_id, score in _run_check_scores(result).items():
            scores.setdefault(check_id, []).append(score)
    return {check_id: _round(_mean(values)) for check_id, values in sorted(scores.items())}


def _run_check_scores(result: SampleResult) -> dict[str, float]:
    """One run's score per check: its layers and their leaf checks, skipped ones left out.

    A check without a score counts as its verdict (``1.0`` passed, ``0.0`` failed).
    A composed check between a layer and its leaves repeats the layer, so it is skipped.
    """
    scores: dict[str, float] = {}
    for layer in result.report.checks:
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
