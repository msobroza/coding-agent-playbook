"""The answers a ``--record`` keeps of each fresh run (spec D8, ``evals.answers_store``).

Each run of a sample on the current text grades through its own
:class:`~coding_agent_playbook.evals.answers_store.CapturingJudge` (one per run,
so ``--jobs`` never mixes two runs' calls), and becomes one
:class:`~coding_agent_playbook.evals.answers_store.StoredRun`: the artifact the
judge graded, the judge-free checks, each rubric criterion's weight and captured
mean score, and the judge parts of the record's setup. The record writes the
lines of its fresh sample units, never of an edition control or a carried
sample, to ``--answers`` or beside the metrics file.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.answers_store import (
    CapturingJudge,
    StoredCriterion,
    StoredRun,
    run_from_json,
    write_answers,
)
from coding_agent_playbook.evals.rejudge import rubric_criteria
from coding_agent_playbook.evals.release_metrics import run_check_scores
from coding_agent_playbook.grading.scope import Determinism
from coding_agent_playbook.grading.types import CheckResult

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterable, Iterator, Mapping, Sequence

    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.release_metrics import SampleRecord
    from coding_agent_playbook.evals.run.harness_runner import SampleResult
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.grading.types import ScopeDetail

#: Appended to the metrics file's name for the default answers path.
ANSWERS_FILE_SUFFIX: Final = ".answers.jsonl.gz"


def answers_out_path(args: argparse.Namespace, out_path: Path) -> Path:
    """``--answers``, else ``<record>.answers.jsonl.gz`` beside the metrics file.

    Example::

        >>> answers_out_path(argparse.Namespace(), Path("m/opus.json")).as_posix()  # doctest: +SKIP
        'm/opus.json.answers.jsonl.gz'
    """
    flag = getattr(args, "answers", None)
    return Path(flag) if flag is not None else Path(f"{out_path}{ANSWERS_FILE_SUFFIX}")


def capturing(judge: Judge | None) -> CapturingJudge | None:
    """A fresh capturing wrapper around ``judge`` for one run; ``None`` without a judge.

    Example::

        >>> capturing(None) is None
        True
    """
    return CapturingJudge(judge) if judge is not None else None


def stored_run(
    sample: EvalSample,
    inputs: str,
    run: int,
    result: SampleResult,
    judge: CapturingJudge | None,
    parts: Mapping[str, object],
) -> StoredRun:
    """Run ``run`` of ``sample`` as its answers line, from what ``judge`` captured.

    Every call of one run grades the same artifact, so the first call's is kept.
    Without a call (no judge, or fail-fast skipped it) the artifact and every
    criterion score are ``None``.

    Example::

        >>> stored_run(sample, "ab12", 0, result, None, judge_parts(None)).artifact  # doctest: +SKIP
    """
    calls = judge.calls if judge is not None else []
    return StoredRun(
        sample=sample.id,
        inputs_digest=inputs,
        run=run,
        artifact=calls[0][1] if calls else None,
        checks=judge_free_checks(result),
        criteria=captured_criteria(sample, judge),
        judge=dict(parts),
    )


def captured_criteria(
    sample: EvalSample, judge: CapturingJudge | None
) -> tuple[StoredCriterion, ...]:
    """Each rubric criterion of ``sample`` with the mean score ``judge`` captured for it.

    A criterion without a call (or without a judge) has score ``None`` and ``n`` 0.

    Example::

        >>> captured_criteria(sample, None)[0].score is None  # doctest: +SKIP
        True
    """
    calls = judge.calls if judge is not None else []
    return tuple(_criterion(text, weight, calls) for text, weight in rubric_criteria(sample))


def judge_free_checks(result: SampleResult) -> dict[str, float]:
    """The run's check scores (``run_check_scores``) without the judged ones (spec D8).

    Example::

        >>> judge_free_checks(result)  # doctest: +SKIP
        {'gate': 1.0}
    """
    judged = set(_judged_ids(result.report.checks))
    return {key: score for key, score in run_check_scores(result).items() if key not in judged}


def write_record_answers(path: Path, records: Iterable[SampleRecord]) -> None:
    """Write the answers lines of the fresh sample ``records`` to ``path``.

    Example::

        >>> write_record_answers(Path("m/opus.json.answers.jsonl.gz"), records)  # doctest: +SKIP
    """
    write_answers(path, [run_from_json(answer) for record in records for answer in record.answers])


def _criterion(
    text: str, weight: float, calls: Sequence[tuple[str, str, float, int]]
) -> StoredCriterion:
    """``text``'s mean captured score over its calls; ``None`` (and ``n`` 0) without one."""
    mine = [(score, n) for criterion, _artifact, score, n in calls if criterion == text]
    if not mine:
        return StoredCriterion(text, weight, None, 0)
    return StoredCriterion(text, weight, statistics.fmean(s for s, _ in mine), mine[0][1])


def _judged_ids(checks: Iterable[CheckResult | ScopeDetail]) -> Iterator[str]:
    """The ids of every judged check result under ``checks``, layers and leaves."""
    for check in checks:
        if not isinstance(check, CheckResult):
            continue
        if check.determinism is Determinism.JUDGED:
            yield check.check_id
        yield from _judged_ids(check.subresults)
