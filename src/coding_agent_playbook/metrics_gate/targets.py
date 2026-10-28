"""What a metrics finding needs in order to pass, and how to get there: the fix note.

A check grades a ``0-1`` score, never the raw value, so a finding alone says
"1 -> 9 (regression)" but not where it would pass. The raw value it needed is
recoverable from the metric's normalizer. :func:`passing_target` inverts it at
the score the check required: the deciding ``bound`` for a new or absolute
finding, and the baseline's score less ``max_worsening`` for a regression.
:data:`FIX_HINTS` names one refactoring per metric. ``playbook metrics`` and the
metrics Stop stages both print :func:`fix_note`, so the agent reads the same
target wherever a finding shows up.
"""

from __future__ import annotations

import math
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.grading.normalizer import PercentNormalizer, RampNormalizer
from coding_agent_playbook.metrics_gate.policy import metric_policy

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.grading.types import ScopeDetail
    from coding_agent_playbook.metrics_gate.config import MetricConfig

__all__ = ["FIX_HINTS", "fix_note", "passing_target"]

#: One short refactoring per metric (kept short: a Stop reason line is clipped at 160 chars).
#: ``ruff_violations`` has none: the ruff code the line names already says what to fix.
FIX_HINTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "cyclomatic_complexity": "split branches into helpers",
        "cognitive_complexity": "flatten nesting, extract nested blocks",
        "wmc": "move methods to a collaborator class",
        "lcom4": "split the class by the state its methods share",
        "dit": "compose instead of adding a base class",
        "cbo": "depend on fewer classes",
        "maintainability_index": "shorten and simplify its functions",
        "file_sloc": "split the module by responsibility",
        "docstring_example": "add a usage example to the docstring",
        "coverage": "test the uncovered lines",
        "diff_coverage": "test the changed lines",
        "test_pass_rate": "fix the failing tests",
    }
)
#: Float error in an inverted ramp stays far below one raw unit.
_EPS: Final = 1e-9


def fix_note(finding: ScopeDetail, config: MetricConfig) -> str:
    """``"passes at <= 5: split branches into helpers"``: the target and the hint that apply.

    Either part may be missing; ``""`` when neither is known.

    Example::

        >>> fix_note(cc_regression_1_to_9, MetricConfig())  # doctest: +SKIP
        'passes at <= 5: split branches into helpers'
    """
    target = passing_target(finding, config)
    hint = FIX_HINTS.get(finding.evaluator, "")
    if target and hint:
        return f"passes at {target}: {hint}"
    return f"passes at {target}" if target else hint


def passing_target(finding: ScopeDetail, config: MetricConfig) -> str:
    """The raw value ``finding`` would pass at, as ``"<= 5"`` or ``">= 80"``; ``""`` when unknown.

    A ramp metric (counts: complexity, coupling, lines) gets a whole number; a
    percentage gets its percent; any other normalizer, or an unknown metric,
    gets ``""``.

    Example::

        >>> passing_target(cognitive_new_at_20, MetricConfig())  # doctest: +SKIP
        '<= 15'
    """
    from coding_agent_playbook.grading.metric import get_metric

    try:
        metric = get_metric(finding.evaluator)
    except KeyError:
        return ""
    rule = _pass_rule(finding, metric.score, config)
    if rule is None or rule[0] <= 0.0:
        return ""  # nothing would be required, so there is no target to state
    needed, passes = rule
    normalizer = metric.normalizer
    if isinstance(normalizer, RampNormalizer):
        return _ramp_target(normalizer, needed, passes)
    if isinstance(normalizer, PercentNormalizer):
        return f">= {needed * 100:g}"
    return ""


def _pass_rule(
    finding: ScopeDetail, score: Callable[[float], float], config: MetricConfig
) -> tuple[float, Callable[[float], bool]] | None:
    """``(lowest passing 0-1 score, whether a raw value passes)`` for ``finding``'s check.

    The test repeats ``grading.check``'s own float comparisons (``score <
    bound`` fails; ``base - score > max_worsening`` regresses), so a target on a
    float edge is the one the check really accepts.
    """
    if finding.kind != "regression":
        bound = finding.bound
        return None if bound is None else (bound, lambda raw: score(raw) >= bound)
    if finding.baseline is None:
        return None
    base = score(finding.baseline)
    tolerance = metric_policy(finding.evaluator, config).max_worsening
    return base - tolerance, lambda raw: base - score(raw) <= tolerance


def _ramp_target(ramp: RampNormalizer, needed: float, passes: Callable[[float], bool]) -> str:
    """The last whole raw value that ``passes`` on ``ramp``, near ``needed``, with its direction."""
    limit = ramp.bad + needed * (ramp.good - ramp.bad)
    step = -1 if ramp.good < ramp.bad else 1  # higher is worse: every value below passes
    best = math.floor(limit + _EPS) if step < 0 else math.ceil(limit - _EPS)
    if not passes(best):  # the float limit landed one past the boundary
        best += step
    elif passes(best - step):  # or one short of it
        best -= step
    return f"{'<=' if step < 0 else '>='} {best}"
