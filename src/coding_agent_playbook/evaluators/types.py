"""Evaluator dataclasses + policy types (SPEC prM §E).

These parallel the eval-side ``ExpectedOutcome``/``CheckResult`` dataclasses:
small, mostly-frozen records that describe a *threshold* (``AbsoluteThreshold``),
a *non-regression tolerance* (``RegressionPolicy``), a raw *measurement*, a
graded *finding*, and the aggregate *report*. ``MetricConfig`` is the parsed
``[metrics]`` config for the standalone gate; it satisfies the ``GradePolicy``
``Protocol`` that ``grade()`` reads (the eval block-compiler will expose the same
shape in a later track).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.parse import ModuleModel

#: Levels a finding can carry.
Level = Literal["ok", "warn", "fail"]
#: How a finding was decided.
Kind = Literal["absolute", "regression", "new"]
#: Grading modes.
Mode = Literal["regression", "absolute", "both"]


@dataclass(frozen=True)
class AbsoluteThreshold:
    """A two-stage absolute bound. ``None`` means "no bound at this stage"."""

    warn: float | None = None
    fail: float | None = None


@dataclass(frozen=True)
class RegressionPolicy:
    """How much a scope may worsen vs baseline before it counts as a regression.

    ``0.0`` (the deterministic default) means *any* worsening fails; judged
    evaluators use a small tolerance band (e.g. ``0.1``).
    """

    max_worsening: float = 0.0


@dataclass(frozen=True)
class Measurement:
    """One raw value an evaluator produced for one scope."""

    evaluator: str
    scope_key: str
    value: float


@dataclass(frozen=True)
class Finding:
    """A graded measurement: raw value + how it compared + the verdict.

    ``baseline`` is the matched prior value (``None`` for a new scope), ``bound``
    is the absolute bound that decided the level (``None`` when a regression
    decided it), ``score`` is the normalized ``0-1`` value for the composite,
    ``level`` is ``ok|warn|fail`` and ``kind`` is ``absolute|regression|new``.
    """

    evaluator: str
    scope_key: str
    value: float
    baseline: float | None
    bound: float | None
    score: float
    level: Level
    kind: Kind


@dataclass
class EvaluationReport:
    """The aggregate output of :func:`grade`: every finding + the two verdicts.

    Mutable (unlike the records above) so callers can attach context as they
    merge reports from several evaluator families.
    """

    findings: list[Finding]
    warn_count: int
    fail_count: int
    composite: float | None
    passed: bool


@dataclass(frozen=True)
class ResolvedPolicy:
    """The *effective* policy for one evaluator after config overrides defaults.

    Carries the absolute threshold, the regression tolerance, and the composite
    weight that apply to a single evaluator at grade time.
    """

    absolute: AbsoluteThreshold
    regression: RegressionPolicy
    weight: float


@runtime_checkable
class GradePolicy(Protocol):
    """The slice of config :func:`grade` reads.

    Both the standalone :class:`MetricConfig` and (in a later track) the eval
    block-compiler expose this shape, so ``grade()`` never depends on either
    concretely. ``mode`` picks the comparison strategy; ``strict`` promotes
    warnings to gate failures; the three dicts are per-evaluator overrides.
    """

    mode: Mode
    strict: bool

    @property
    def thresholds(self) -> dict[str, AbsoluteThreshold]: ...

    @property
    def regression(self) -> dict[str, RegressionPolicy]: ...

    @property
    def weights(self) -> dict[str, float]: ...


@dataclass
class MetricConfig:
    """Parsed ``[metrics]`` config for the standalone gate; a ``GradePolicy``.

    ``mode`` selects the comparison strategy; ``fail_on_breach`` controls the
    process exit code; ``strict`` promotes warnings to gate failures. The three
    dicts are per-evaluator overrides keyed by evaluator ``name``.
    """

    mode: Mode = "regression"
    fail_on_breach: bool = True
    strict: bool = False
    run_tests: bool = False
    test_cmd: list[str] | None = None
    thresholds: dict[str, AbsoluteThreshold] = field(default_factory=dict)
    regression: dict[str, RegressionPolicy] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)


@dataclass
class EvalContext:
    """Everything an evaluator might need, decoupled per family (SPEC prM §A).

    Static evaluators read ``module``/``source``/``label``. The execution and
    judged fields (``project``/``judge``/``artifact``/``samples``) are reserved
    for later tracks and default to ``None``/``1`` so v1 static evaluators never
    touch them.
    """

    module: ModuleModel | None
    source: str
    label: str
    project: Any | None = None
    judge: Any | None = None
    artifact: Any | None = None
    samples: int = 1
