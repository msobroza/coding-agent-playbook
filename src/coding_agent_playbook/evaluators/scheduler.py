"""The cost-tiered short-circuit scheduler (T4b).

:func:`schedule` is the Strategy a
:class:`~coding_agent_playbook.evaluators.rubric.Rubric` (and the boolean
composers in :mod:`coding_agent_playbook.evaluators.checks.compose`) use to run a
list of :class:`~coding_agent_playbook.evaluators.check.Check`\\ es. It pulls the
"run all checks" loop out of ``Rubric`` into one reusable function so a costlier
tier need never run once the verdict is already decided.

Three properties, all guaranteed regardless of ``max_workers``:

* **Cheapest-first tiers.** Checks run in ascending
  :class:`~coding_agent_playbook.evaluators.scope.CostTier`
  (``DETERMINISTIC`` -> ``EXECUTION`` -> ``JUDGED``), so the cheap deterministic
  checks decide the verdict before any opt-in execution or judged check is
  touched.
* **Authored-order results.** The returned list is always in the **original**
  authored order - completion order under concurrency never leaks out.
* **Short-circuit.** With ``short_circuit=True`` the scheduler stops descending
  into costlier tiers once the verdict is settled: for ``op="and"`` as soon as a
  **required** check fails, for ``op="or"`` as soon as any check passes. The
  headline guarantee: an ``op="and"`` schedule whose DETERMINISTIC tier already
  has a failing required check **never grades** the JUDGED tier - the
  :class:`~coding_agent_playbook.evals.judge.Judge` is never invoked.

A check whose :meth:`~coding_agent_playbook.evaluators.check.Check.available` is
``False`` (e.g. a judged check with no judge), and a check short-circuited away by
a settled verdict, both yield a ``status="skipped"``
:class:`~coding_agent_playbook.evaluators.types.CheckResult` that carries the
check's descriptors but never ran.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from itertools import groupby
from typing import TYPE_CHECKING, Literal

from coding_agent_playbook.evaluators.types import CheckResult

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.evaluators.check import Check, MeasurementSet
    from coding_agent_playbook.evaluators.types import EvalContext

#: The boolean fold a schedule applies. ``"and"`` short-circuits on a required
#: failure; ``"or"`` short-circuits on any pass.
Op = Literal["and", "or"]


def schedule(
    checks: list[Check],
    ctx: EvalContext,
    measurements: MeasurementSet,
    *,
    op: Op = "and",
    short_circuit: bool = True,
    max_workers: int = 1,
) -> list[CheckResult]:
    """Run ``checks`` cheapest-tier-first, short-circuiting once ``op`` is decided.

    Each check is graded only when it is :meth:`~coding_agent_playbook.evaluators.check.Check.available`
    in ``ctx`` and its tier has not been short-circuited away; otherwise it gets a
    :func:`skipped_result`. Within one cost tier the available checks run
    concurrently when ``max_workers > 1`` (a
    :class:`concurrent.futures.ThreadPoolExecutor`) and sequentially when
    ``max_workers == 1`` (the deterministic default CI uses). The returned list is
    in the **original authored order** either way.

    ``short_circuit`` (default ``True``) controls only how much work is done, never
    the verdict: after each tier, if ``op == "and"`` and a *required* check has
    ``passed is False``, or ``op == "or"`` and any check ``passed is True``, the
    remaining costlier tiers are skipped (their checks recorded ``status="skipped"``).
    With ``short_circuit=False`` every available check runs.
    """
    # Remember the authored position so the returned list can be re-sorted back
    # into authored order regardless of tier / completion order.
    indexed = list(enumerate(checks))
    results: dict[int, CheckResult] = {}

    decided = False
    # Group by ascending cost tier so the cheapest checks run (and can settle the
    # verdict) first. ``groupby`` needs a sorted key; ``CostTier`` is an IntEnum.
    indexed.sort(key=lambda pair: pair[1].cost)
    for _tier, group in groupby(indexed, key=lambda pair: pair[1].cost):
        tier_checks = list(group)
        if decided:
            # A prior tier settled the verdict: skip this costlier tier wholesale.
            for index, check in tier_checks:
                results[index] = skipped_result(check)
            continue

        tier_results = _run_tier(tier_checks, ctx, measurements, max_workers=max_workers)
        results.update(tier_results)

        if short_circuit and _settles(tier_results.values(), op):
            decided = True

    # Re-sort into the original authored order; completion order never leaks.
    return [results[index] for index in range(len(checks))]


def _run_tier(
    tier_checks: list[tuple[int, Check]],
    ctx: EvalContext,
    measurements: MeasurementSet,
    *,
    max_workers: int,
) -> dict[int, CheckResult]:
    """Grade one cost tier; unavailable checks skip. Returns ``{authored_index: result}``.

    Concurrency is bounded to the available checks of this single tier: an
    unavailable check is recorded skipped without spawning a worker, and the
    remaining checks run on a :class:`~concurrent.futures.ThreadPoolExecutor` when
    ``max_workers > 1`` (else sequentially).
    """
    results: dict[int, CheckResult] = {}
    runnable: list[tuple[int, Check]] = []
    for index, check in tier_checks:
        if check.available(ctx):
            runnable.append((index, check))
        else:
            results[index] = skipped_result(check)

    if not runnable:
        return results

    if max_workers > 1 and len(runnable) > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                index: pool.submit(check.grade, ctx, measurements) for index, check in runnable
            }
            for index, future in futures.items():
                results[index] = future.result()
    else:
        for index, check in runnable:
            results[index] = check.grade(ctx, measurements)

    return results


def _settles(tier_results: Iterable[CheckResult], op: Op) -> bool:
    """Whether this tier's results already settle the ``op`` verdict.

    ``op="and"`` is settled the moment a **required** check fails (the gate is
    already lost). ``op="or"`` is settled the moment any check passes. Skipped
    results within the tier (unavailable checks) are neutral and never settle.
    """
    rows = [r for r in tier_results if r.status == "run"]
    if op == "and":
        return any(r.required and not r.passed for r in rows)
    return any(r.passed for r in rows)


def skipped_result(check: Check) -> CheckResult:
    """A ``status="skipped"`` result carrying ``check``'s descriptors (never ran).

    Used both for a check that is unavailable in ``ctx`` and for a check
    short-circuited away by a settled verdict: either way it did not run, so
    ``passed`` is ``False`` and ``score`` is ``None`` (a skipped check is neutral
    to the gate and contributes nothing to the composite).
    """
    return CheckResult(
        check_id=check.id,
        passed=False,
        score=None,
        weight=check.weight,
        required=check.required,
        determinism=check.determinism,
        cost=check.cost,
        status="skipped",
        subresults=(),
    )


__all__ = ["Op", "schedule", "skipped_result"]
