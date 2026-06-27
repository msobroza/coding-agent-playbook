"""``coverage`` — line-coverage percentage per file + a suite total (M4).

A FILE-scope NUMERIC metric (percentage ``0-100``): one measurement per source
file coverage.py reported, plus one MODULE-scope measurement for the overall
total. Higher is better (``higher_is_worse=False``); the absolute default
``warn=80`` flags files under 80% coverage, and ``max_worsening=0`` means coverage
must not drop versus baseline.

Reads the **same** :meth:`ProjectHandle.run` cache the ``test_pass_rate``
evaluator uses, so enabling both under ``--run-tests`` still runs the suite only
once. ``needs_project=True`` ⇒ execution evaluator, excluded from
``static_evaluators()``; :meth:`available` requires ``ctx.project``.

Scope keys: per-file measurements key on the coverage.py ``filename`` (a path
relative to the project root, e.g. ``pkg/a.py``) so they match across baseline
and candidate runs; the MODULE total keys on the bare ``ctx.label``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.parse import scope_key
from coding_agent_playbook.evaluators.registry import Evaluator, register_evaluator
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    Measurement,
    RegressionPolicy,
)

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext


@register_evaluator
class Coverage(Evaluator):
    """Line coverage per file (+ a MODULE total) from one cached suite run."""

    name = "coverage"
    scope = Scope.FILE
    value_kind = ValueKind.NUMERIC
    determinism = Determinism.DETERMINISTIC
    higher_is_worse = False
    requires = None
    needs_project = True
    default_absolute = AbsoluteThreshold(warn=80.0)
    default_regression = RegressionPolicy(max_worsening=0.0)
    default_weight = 0.0

    def available(self, ctx: EvalContext) -> bool:
        """True only when a runnable project handle is present."""
        return ctx.project is not None

    def evaluate(self, ctx: EvalContext) -> list[Measurement]:
        """Emit one FILE measurement per covered file + one MODULE total.

        Reads :meth:`ProjectHandle.run` (cached), so this never re-runs the suite
        even when ``test_pass_rate`` already triggered it.
        """
        if ctx.project is None:
            return []
        report = ctx.project.run().coverage
        measurements = [
            Measurement(
                evaluator=self.name,
                scope_key=scope_key(filename, None),
                value=float(pct),
            )
            for filename, pct in sorted(report.per_file.items())
        ]
        measurements.append(
            Measurement(
                evaluator=self.name,
                scope_key=scope_key(ctx.label, None),
                value=float(report.total),
            )
        )
        return measurements
