"""Metric/Check dataclasses + policy types (SPEC prM §E).

Small, mostly-frozen records that describe a *threshold* (``AbsoluteThreshold``),
a *non-regression tolerance* (``RegressionPolicy``), a raw *measurement*, a graded
per-scope detail (``ScopeDetail``), a check outcome (``CheckResult``), and the
aggregate *report* (``EvaluationReport``). ``MetricConfig`` is the parsed
``[metrics]`` config for the standalone gate; it satisfies the ``GradePolicy``
``Protocol`` the ``Check`` policy resolution reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evaluators.parse import ModuleModel
    from coding_agent_playbook.evaluators.scope import CostTier, Determinism

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
class ScopeDetail:
    """A graded measurement for one scope: raw value + how it compared + verdict.

    ``baseline`` is the matched prior value (``None`` for a new scope), ``bound``
    is the absolute bound that decided the level (``None`` when a regression
    decided it), ``score`` is the normalized ``0-1`` value for the composite,
    ``level`` is ``ok|warn|fail`` and ``kind`` is ``absolute|regression|new``.

    In the ``Metric``/``Check``/``Rubric`` model this is the leaf per-scope detail
    a :class:`CheckResult` carries, and the row type the flat
    :attr:`EvaluationReport.findings` list holds.
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
class CheckResult:
    """The graded outcome of one ``Check`` (T1).

    A ``Check`` is the unit a ``Rubric`` schedules. ``score`` is the normalized
    ``0-1`` contribution (``None`` when the check was skipped or yields no
    score), ``weight`` is its composite weight, ``required`` marks a gate check,
    and ``determinism``/``cost`` drive routing + cheapest-first scheduling.
    ``status`` is ``"run"`` for a check that executed and ``"skipped"`` for one
    that could not (e.g. a judged check with no ``Judge``). ``subresults`` is
    recursive — a composing check (a nested ``Rubric``) carries child
    :class:`CheckResult` objects, while a leaf check carries :class:`ScopeDetail`
    rows. Mutable, like :class:`EvaluationReport`, so callers can attach context.
    """

    check_id: str
    passed: bool
    score: float | None
    weight: float
    required: bool
    determinism: Determinism
    cost: CostTier
    status: Literal["run", "skipped"] = "run"
    subresults: tuple[ScopeDetail | CheckResult, ...] = ()
    detail: str = ""


@dataclass
class EvaluationReport:
    """The aggregate output of :meth:`Rubric.evaluate`: findings + the two verdicts.

    Mutable (unlike the records above) so callers can attach context as they
    merge reports from several check families. ``findings`` carries the flat
    per-scope :class:`ScopeDetail` rows (the deterministic leaf details renderers
    read); ``checks`` carries the structured :class:`CheckResult` rows.
    """

    findings: list[ScopeDetail]
    warn_count: int
    fail_count: int
    composite: float | None
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)


@dataclass(frozen=True)
class TrialResult:
    """One runner trial's per-trial report + its derived pass/fail verdict.

    The across-trial aggregate layer (``[aggregate]``: ``pass@k`` / ``pass^k``)
    reduces a list of these. ``report`` is the per-trial
    :class:`EvaluationReport` (its ``checks`` expose the ``gate`` / ``rubric``
    layers); ``verdict`` is the per-trial verdict already derived from those
    layers (skipped-neutral). An :class:`~coding_agent_playbook.evaluators.checks.aggregate.AggregateCheck`
    reads the per-trial boolean off each via
    :func:`~coding_agent_playbook.evals._compile.over_boolean`.
    """

    report: EvaluationReport
    verdict: bool


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
class JudgeLike(Protocol):
    """The slice of a judge an :class:`EvalContext` needs (SPEC prR2 Track J).

    Defined in ``evaluators`` (not ``evals``) so the evaluator package never
    imports ``evals`` — that would create a cycle, since ``evals`` imports
    ``evaluators``. The concrete
    :class:`~coding_agent_playbook.evals.judge.Judge` satisfies this structurally
    via its canonical per-criterion primitive.
    """

    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
        """Score ``criterion`` against ``artifact`` as a ``0-1`` float (``n``-sample avg)."""
        ...


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

    Static evaluators read ``module``/``source``/``label``. The execution field
    (``project``), the judged fields (``judge``/``artifact``/``samples``), and the
    expected-outcome fields (``tree``/``baseline_tree``) are consumed by the
    execution, judged, and ``[expected]`` families respectively and default to
    ``None``/``1`` so static evaluators never touch them. ``judge`` is typed as
    the structural :class:`JudgeLike` so this package never imports ``evals``.

    The ``[expected]`` file checks
    (:mod:`coding_agent_playbook.evaluators.checks.files`) read ``tree`` (the
    candidate repo root after the agent ran) and ``baseline_tree`` (the pristine
    ``setup/`` snapshot, for the ``file_unchanged`` check). The runner sets both;
    every other family ignores them.

    The two ``*_measurements`` fields (T4a) let a
    :class:`~coding_agent_playbook.evaluators.rubric.Rubric` act as a
    :class:`~coding_agent_playbook.evaluators.metric.Metric`: when a Rubric is
    nested inside a parent Rubric, its :meth:`measure` self-builds a
    :class:`~coding_agent_playbook.evaluators.check.MeasurementSet` from
    ``candidate_measurements`` (and the optional ``baseline_measurements``) so the
    nested rubric grades its own checks without the parent threading a separate
    measurement set through. Both default to ``None``; every non-Rubric family
    ignores them.

    ``trials`` carries the across-trial run results the
    :class:`~coding_agent_playbook.evaluators.checks.aggregate.AggregateCheck`
    family reduces (``pass@k`` / ``pass^k``). The runner runs ``N = max(k)``
    trials, collects one :class:`TrialResult` per trial, and grades the compiled
    aggregate layer over a context carrying them; every other family ignores it
    and it defaults to ``None`` (a single-trial run sets no aggregate context).
    """

    module: ModuleModel | None
    source: str
    label: str
    project: Any | None = None
    judge: JudgeLike | None = None
    artifact: Any | None = None
    samples: int = 1
    tree: Path | None = None
    baseline_tree: Path | None = None
    candidate_measurements: list[Measurement] | None = None
    baseline_measurements: list[Measurement] | None = None
    trials: list[TrialResult] | None = None
