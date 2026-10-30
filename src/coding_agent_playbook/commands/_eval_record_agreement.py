"""The ``judge_change`` of a record that re-judged stored runs (spec D10).

After every unit ran (``commands._eval_record_runs.record_units``, so a
``--resume`` sees the checkpoint's records too), each re-judged run pairs the
old stored line (``CarryPlan.rejudge[id].runs``) with this record's new line of
the same run index. Both sides are re-scored by ``evals.rejudge.rescore_run``
from their criterion scores: the rubric verdict and the weighted rubric score.
A run that either judge did not grade (fail-fast lost its gate) does not count.
``evals.judge_agreement`` folds the pairs; the record prints its line and writes
``judge_change`` only when a run counted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evals.answers_store import run_from_json
from coding_agent_playbook.evals.judge_agreement import AgreementRun, agreement_line, judge_change
from coding_agent_playbook.evals.rejudge import RejudgeError, rescore_run
from coding_agent_playbook.evals.release_metrics_schema import JUDGE_CHANGE_KEY

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.evals.answers_store import StoredRun
    from coding_agent_playbook.evals.release_carry import CarryPlan
    from coding_agent_playbook.evals.release_metrics import SampleRecord
    from coding_agent_playbook.evals.sample import EvalSample


def with_judge_change(
    metrics: dict[str, object],
    carry: CarryPlan,
    rejudged: Sequence[SampleRecord],
    samples: Sequence[EvalSample],
    parts: Mapping[str, object],
) -> dict[str, object]:
    """``metrics`` with the ``judge_change`` of the ``rejudged`` records, its line printed.

    ``parts`` are this record's judge parts. Without a re-graded run on both
    sides, ``metrics`` is returned unchanged and nothing is printed.

    Example::

        >>> with_judge_change(metrics, carry, [], samples, parts) is metrics  # doctest: +SKIP
        True
    """
    by_id = {sample.id: sample for sample in samples}
    runs = [
        run for record in rejudged for run in agreement_runs(by_id[record.sample_id], carry, record)
    ]
    olds = [carry.rejudge[record.sample_id].judge for record in rejudged]
    change = judge_change(runs, old=olds, new=parts)
    if change is None:
        return metrics
    print(agreement_line(change))
    return {**metrics, JUDGE_CHANGE_KEY: change}


def agreement_runs(
    sample: EvalSample, carry: CarryPlan, record: SampleRecord
) -> list[AgreementRun]:
    """Each run of ``record`` paired by run index with its old stored line, both re-scored.

    Example::

        >>> agreement_runs(sample, carry, record)[0].task  # doctest: +SKIP
        'refactor'
    """
    new = {line.run: line for line in map(run_from_json, record.answers)}
    pairs = [(old, new.get(old.run)) for old in carry.rejudge[sample.id].runs]
    paired = [_paired(sample, old, line) for old, line in pairs if line is not None]
    return [run for run in paired if run is not None]


def _paired(sample: EvalSample, old: StoredRun, new: StoredRun) -> AgreementRun | None:
    """The run's old and new rubric verdict and score; ``None`` unless both judges graded it."""
    before, after = _rubric(sample, old), _rubric(sample, new)
    if before is None or after is None:
        return None
    return AgreementRun(sample.prompt_id, before[0], after[0], before[1], after[1])


def _rubric(sample: EvalSample, run: StoredRun) -> tuple[bool, float] | None:
    """``run``'s rubric verdict and weighted rubric score from its criterion scores."""
    scores = {c.criterion: c.score for c in run.criteria if c.score is not None}
    if not run.criteria or len(scores) < len(run.criteria):
        return None
    try:
        score = rescore_run(sample, run.checks, scores)
    except RejudgeError:
        return None  # agreement is never gated (D10): an unscorable pair does not count
    if score.rubric_passed is None or score.rubric_score is None:
        return None
    return score.rubric_passed, score.rubric_score
