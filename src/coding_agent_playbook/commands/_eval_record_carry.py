"""The ``--carry-from`` baseline of ``playbook eval --record`` (``commands._eval_record``).

``--carry-from`` names either one release metrics file of the same target
(ADR 0013, ``evals.release_carry``) or the releases directory, whose committed
metrics files of this run's setup are indexed whatever their target (ADR 0014,
``evals.result_index``). This module loads the one or the other before any
paid run and dispatches the carry plan on which it is. A directory's plan then
finds the stored answers of each sample to re-judge (spec D9,
``commands._eval_record_rejudge``) before the plan is printed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.commands._eval_record_rejudge import resolve_rejudges
from coding_agent_playbook.evals.release_carry import carry_plan_lines, load_baseline, plan_carry
from coding_agent_playbook.evals.result_index import ReleaseIndex

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from pathlib import Path

    from coding_agent_playbook.evals.release_carry import CarryPlan
    from coding_agent_playbook.evals.release_metrics import RecordedTarget
    from coding_agent_playbook.evals.sample import EvalSample

#: A ``--carry-from`` baseline: one metrics file's data, or the releases directory's index.
Baseline = Mapping[str, Any] | ReleaseIndex


def load_carry_baseline(path: Path | None, *, target_name: str, out_path: Path) -> Baseline | None:
    """The baseline ``path`` names: the releases directory's index, else the metrics file.

    The index leaves out ``out_path``, the record's own output, which may sit
    inside the directory from an earlier attempt. ``None`` without ``--carry-from``.

    Example::

        >>> load_carry_baseline(Path("catalog/releases"), target_name="opus", out_path=out)  # doctest: +SKIP
        ReleaseIndex(files=(...), skipped=())
    """
    if path is None:
        return None
    if path.is_dir():
        return ReleaseIndex.load(path, exclude=out_path)
    return load_baseline(path, target_name)


def plan_from_baseline(
    baseline: Baseline, *, target_name: str, setup: Mapping[str, object], inputs: Mapping[str, str]
) -> CarryPlan:
    """Which of ``inputs`` (sample id to inputs digest) rerun against ``baseline``.

    Example::

        >>> plan_from_baseline(index, target_name="opus", setup=setup, inputs={}).rerun  # doctest: +SKIP
        {}
    """
    if isinstance(baseline, ReleaseIndex):
        return baseline.plan(target_name=target_name, setup=setup, inputs=inputs)
    return plan_carry(baseline, setup=setup, inputs=inputs)


def print_carry_plan(
    baseline: Baseline | None,
    recorded: RecordedTarget,
    inputs: Mapping[str, str],
    controls: Collection[str],
    samples: Sequence[EvalSample],
) -> CarryPlan | None:
    """The ``--carry-from`` plan, printed before the first paid run; ``None`` without a baseline.

    ``controls`` are the ids of the pinned samples whose edition controls always rerun.
    ``samples`` are the record's samples, which a re-judge re-scores (spec D9).

    Example::

        >>> print_carry_plan(None, recorded, {}, (), []) is None  # doctest: +SKIP
        True
    """
    if baseline is None:
        return None
    assert recorded.setup is not None  # a record always computes its setup parts
    setup = recorded.setup.as_dict()
    name = recorded.target.name
    carry = plan_from_baseline(baseline, target_name=name, setup=setup, inputs=inputs)
    if isinstance(baseline, ReleaseIndex):
        by_id = {sample.id: sample for sample in samples}
        carry = resolve_rejudges(carry, releases_root=baseline.root, samples=by_id)
    for line in carry_plan_lines(carry, controls=sorted(controls)):
        print(line)
    return carry
