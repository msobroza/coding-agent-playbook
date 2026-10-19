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
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol, runtime_checkable

# The eval-fixture globs are defined once, for the hooks' ``eval_fixture`` path
# class; ``artifacts.path_classes`` imports only ``re``, so the evaluators stay light.
from coding_agent_playbook.artifacts.path_classes import FIXTURE_GLOBS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from coding_agent_playbook.evaluators.baseline_git import GitRunner
    from coding_agent_playbook.evaluators.parse import ModuleModel
    from coding_agent_playbook.evaluators.scope import CostTier, Determinism
    from coding_agent_playbook.evaluators.tool_runner import ToolRunner

#: Levels a finding can carry.
Level = Literal["ok", "warn", "fail"]
#: How a finding was decided.
Kind = Literal["absolute", "regression", "new"]
#: Grading modes.
Mode = Literal["regression", "absolute", "both"]

#: Default ``[metrics] git_timeout_s``: every baseline git call is a local read,
#: so one slower than this means a wedged repository (lock contention, network FS).
DEFAULT_GIT_TIMEOUT_S = 10.0

#: Default ``[metrics.ruff_violations] families`` (prK §F.2.1): the Clean Code
#: budget codes and pydocstyle's missing-docstring codes, all stable in ruff 0.15.
DEFAULT_RUFF_FAMILIES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "quality": ("C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915"),
        "docstrings": ("D100", "D101", "D102", "D103", "D104", "D105", "D106", "D107"),
    }
)


@dataclass(frozen=True)
class RuffSettings:
    """``[metrics.ruff_violations]``: which codes count per family, and how ruff runs.

    ``config`` holds the rendered per-invocation ``--config`` overrides
    (``"lint.mccabe.max-complexity=10"``); ``preview`` adds ``--preview`` to
    this call only, never to the consumer's ruff config.

    Example::

        >>> RuffSettings().codes()[:2]
        ('C901', 'D100')
    """

    families: Mapping[str, tuple[str, ...]] = DEFAULT_RUFF_FAMILIES
    config: tuple[str, ...] = ()
    preview: bool = False

    def codes(self) -> tuple[str, ...]:
        """Every family's codes, sorted and once each: what ``--select`` gets."""
        return tuple(sorted({code for codes in self.families.values() for code in codes}))


@dataclass(frozen=True)
class ToolSetup:
    """How a subprocess-backed metric runs its tool: where, through what, for how long.

    ``runner`` ``None`` means a plain subprocess; ``cwd`` is the repository root,
    so the project's own config, ``per-file-ignores`` and ``# noqa`` apply.

    A diff-based metric (``diff_coverage``) reads git through ``git``, which
    builds a reader for a project root and bound (``None``: a plain ``git``
    subprocess; a hook passes its hardened ``SafeGit``), and never scores a
    path matching ``exclude`` (``[metrics] exclude``). ``timeout_s`` bounds
    those git reads too. ``changed_lines`` replaces that git read outright:
    ``(root, base) -> {root-relative path: line numbers}``, for a caller that
    already lists the change (the coverage Stop stage, through its hardened
    ``GitPort``, prK §F.1.2).

    Example::

        >>> ToolSetup().timeout_s
        10.0
    """

    cwd: Path | None = None
    runner: ToolRunner | None = None
    timeout_s: float = DEFAULT_GIT_TIMEOUT_S
    ruff: RuffSettings = field(default_factory=RuffSettings)
    git: Callable[[Path, float], GitRunner] | None = None
    exclude: tuple[str, ...] = ()
    changed_lines: Callable[[Path, str], Mapping[str, frozenset[int]]] | None = None


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

    ``verdict_score`` (C10) is the per-trial weighted-composite verdict score
    over the gate/rubric layers when the task authored a weighted ``[verdict]``
    (``weights``/``fail``); ``None`` for a boolean-mode verdict (the legacy
    ``[verdict].trial`` form), and ``None`` for a weighted verdict whose
    referenced layers were *all* skipped (vacuously passing). ``passed`` still
    carries the trial verdict in both modes.
    """

    findings: list[ScopeDetail]
    warn_count: int
    fail_count: int
    composite: float | None
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)
    verdict_score: float | None = None


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
    ``git_timeout_s`` bounds every git call a ``git:`` baseline makes (prK
    §F.0.3 item 7).

    ``select`` / ``extend_select`` / ``ignore`` are the ruff-shaped metric
    selection (metric or family names; ``select=None`` is the default set, see
    :func:`~coding_agent_playbook.evaluators.policy.resolve_metric_selection`).
    ``exclude`` lists repo-relative globs never measured; it defaults to the
    frozen eval fixtures. ``test_timeout_s`` bounds a suite run (``None``: no
    bound). ``ruff_families`` / ``ruff_config`` / ``ruff_preview`` are
    ``[metrics.ruff_violations]`` (``ruff_config`` keeps the TOML values;
    :attr:`ruff_settings` renders them as flags).
    """

    mode: Mode = "regression"
    fail_on_breach: bool = True
    strict: bool = False
    run_tests: bool = False
    test_cmd: list[str] | None = None
    thresholds: dict[str, AbsoluteThreshold] = field(default_factory=dict)
    regression: dict[str, RegressionPolicy] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    git_timeout_s: float = DEFAULT_GIT_TIMEOUT_S
    select: tuple[str, ...] | None = None
    extend_select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    exclude: tuple[str, ...] = FIXTURE_GLOBS
    test_timeout_s: float | None = None
    ruff_families: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(DEFAULT_RUFF_FAMILIES)
    )
    ruff_config: Mapping[str, Any] = field(default_factory=dict)
    ruff_preview: bool = False

    @property
    def ruff_settings(self) -> RuffSettings:
        """The ``ruff_violations`` settings: families, rendered ``--config`` flags, preview."""
        from coding_agent_playbook.metrics_config import ruff_config_flags

        return RuffSettings(
            families=dict(self.ruff_families),
            config=tuple(ruff_config_flags(self.ruff_config)),
            preview=self.ruff_preview,
        )


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

    ``tool_paths`` maps a consumer-toolchain binary name (``"ruff"``) to the
    executable a subprocess-backed metric must run (prK §F.0.3 item 1). The
    metrics gate fills it from its request: ``machine.json`` pins inside hooks,
    ``shutil.which`` for the CLI. ``tool_setup`` says how that tool runs (the
    runner, the repository root, the timeout, the ruff settings); only
    ``ruff_violations`` reads either.
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
    tool_paths: Mapping[str, str] = field(default_factory=dict)
    tool_setup: ToolSetup = field(default_factory=ToolSetup)
