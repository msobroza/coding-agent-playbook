"""The ``Metric`` ABC + the metric registry (the Metric/Check/Rubric stack).

The ``Metric`` layer is the "measure" leaf of the
:class:`Metric` (measure) -> ``Check`` (grade) -> ``Rubric`` (aggregate) stack. A
``Metric`` produces raw
:class:`~coding_agent_playbook.grading.types.Measurement` rows over a scope
and carries *only* the measurement-side descriptors (``name``, ``scope``,
``normalizer``, ``requires``, ``needs_project``, ``diff_based``) - the grading-side
descriptors (thresholds, regression policy, weight) live on the ``Check`` layer.

Every metric owns a
:class:`~coding_agent_playbook.grading.normalizer.Normalizer` that maps its
raw value to a ``0-1`` **goodness** (higher = always better), exposed via
:meth:`Metric.score`. Folding the metric's native direction into the normalizer
is what let the per-metric direction flag be deleted: the ``Check`` layer grades
on the normalized score, so it never reasons about direction.

Each builtin/execution module keeps its measurement compute in a module-level
``_measure`` function the ``Metric`` calls, so the parse-once value surfaces per
scope with no duplicated logic.

Builtins self-register via the :func:`register_metric` decorator; out-of-tree
metrics register through the ``coding_agent_playbook.metrics`` entry-point group.
In-tree builtins always win over an entry point that reuses their name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import import_module, metadata
from importlib.util import find_spec
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.grading.scope import Scope

if TYPE_CHECKING:
    from coding_agent_playbook.grading.normalizer import Normalizer
    from coding_agent_playbook.grading.types import EvalContext, Measurement, MeasureSetup

#: Entry-point group for out-of-tree metrics.
ENTRY_POINT_GROUP = "coding_agent_playbook.metrics"

#: name -> Metric subclass, populated by the decorator on import.
_METRIC_REGISTRY: dict[str, type[Metric]] = {}

#: The 12 in-tree metric modules, static first, each family in the order its
#: package ``__init__`` imported it: importing one fires its ``@register_metric``.
#: A package ``__init__`` holds only a docstring (ADR 0002), so the list names
#: every module.
_BUILTIN_METRIC_MODULES: Final = (
    "coding_agent_playbook.grading.static_metrics.cbo",
    "coding_agent_playbook.grading.static_metrics.cyclomatic",
    "coding_agent_playbook.grading.static_metrics.dit",
    "coding_agent_playbook.grading.static_metrics.docstring_example",
    "coding_agent_playbook.grading.static_metrics.file_sloc",
    "coding_agent_playbook.grading.static_metrics.lcom4",
    "coding_agent_playbook.grading.static_metrics.maintainability",
    "coding_agent_playbook.grading.static_metrics.ruff_violations",
    "coding_agent_playbook.grading.static_metrics.wmc",
    "coding_agent_playbook.grading.execution_metrics.coverage",
    "coding_agent_playbook.grading.execution_metrics.diff_coverage",
    "coding_agent_playbook.grading.execution_metrics.test_pass",
)


class Metric(ABC):
    """A raw measurement producer over a scope (the "measure" layer).

    Subclasses set the class-level measurement descriptors and implement
    :meth:`measure`. Each metric owns a :attr:`normalizer` that bakes in its
    native direction and maps a raw value to a ``0-1`` **goodness** (higher =
    always better) via :meth:`score`: CC/WMC/CBO/DIT/LCOM4 ramp *down* as the raw
    value grows, MI/coverage/test-pass-rate ramp *up*. Grading-side concerns
    (absolute thresholds as ``0-1`` cutoffs, regression tolerance, composite
    weight) belong to the ``Check`` layer, not here.
    """

    name: str
    scope: Scope
    #: Maps this metric's raw value to a ``0-1`` goodness (higher = always
    #: better); see :meth:`score`. Folds the metric's native direction in, which
    #: is why no separate per-direction flag is needed.
    normalizer: Normalizer
    #: Optional importable dependency/capability; ``None`` means stdlib-only.
    requires: str | None = None
    #: ``True`` for execution metrics that need a runnable project
    #: (``ctx.project``). This is the explicit "static vs execution"
    #: discriminator: :func:`static_metrics` excludes any metric with
    #: ``needs_project=True``.
    needs_project: bool = False
    #: ``True`` for judge-backed metrics that need a configured judge
    #: (``ctx.judge``) to measure — a
    #: :class:`~coding_agent_playbook.grading.judge_metric.JudgeMetric`
    #: or a :class:`~coding_agent_playbook.grading.rubric.Rubric` carrying judged
    #: checks. A metric-backed :class:`~coding_agent_playbook.grading.check.Check`
    #: reads this to schedule the check in the JUDGED tier and to measure it lazily
    #: at grade time (so the cost-tiered scheduler can short-circuit it).
    needs_judge: bool = False
    #: ``True`` for execution metrics that measure the candidate *relative to a
    #: diff base* (``diff_coverage``, prK §F.1.1). A baseline run of one is
    #: meaningless: the metrics gate skips the baseline suite run when every
    #: selected execution metric is diff-based, and a baseline handle carries no
    #: diff base, so the candidate grades as ``kind="new"`` (absolute).
    diff_based: bool = False

    def runnable(self, setup: MeasureSetup) -> bool:
        """True when ``setup`` can run this metric: the environment half of :meth:`available`.

        The declared dependency (if any) must be importable. A family whose tool
        or dependency comes from elsewhere overrides it (``ruff_violations``
        needs ``setup.tool_paths["ruff"]``). A measuring pass promises exactly
        the metrics that are runnable
        (:func:`~coding_agent_playbook.grading.measuring.measured_metrics`).

        Example::

            >>> get_metric("cyclomatic_complexity").runnable(MeasureSetup())
            True
        """
        return self.requires is None or find_spec(self.requires) is not None

    def available(self, ctx: EvalContext) -> bool:
        """True when this metric can run in ``ctx``.

        ``ctx``'s tools must run it (:meth:`runnable`), and the needed context
        slot must be present - execution metrics (``needs_project``) need
        ``ctx.project``; static metrics need ``ctx.module``. Families that gate on
        a different slot override this. An environment condition (a tool, an
        environment variable, an import beyond ``requires``) belongs in
        :meth:`runnable`, not here: at grade time a threshold or non-regression
        check over a non-judge metric reads ``ctx.measured_metrics``, which the
        measuring pass fills from :meth:`runnable`, and never calls this method.
        """
        if not self.runnable(ctx.measure_setup):
            return False
        if self.needs_project:
            return ctx.project is not None
        return ctx.module is not None

    def score(self, raw: float) -> float:
        """Map ``raw`` to this metric's ``0-1`` goodness via its :attr:`normalizer`."""
        return self.normalizer.normalize(raw)

    @abstractmethod
    def measure(self, ctx: EvalContext) -> list[Measurement]:
        """Produce one :class:`Measurement` per in-scope unit."""


def register_metric(cls: type[Metric]) -> type[Metric]:
    """Class decorator registering a :class:`Metric` subclass by ``name``."""
    _METRIC_REGISTRY[cls.name] = cls
    return cls


def _load_metric_builtins() -> None:
    """Import the in-tree metric modules so each module's metric decorator fires.

    Imports every module of :data:`_BUILTIN_METRIC_MODULES`, the static metrics
    and then the execution metrics (``test_pass_rate``, ``coverage``,
    ``diff_coverage``), so the metric registry sees both. Importing these modules
    fires each module's ``@register_metric`` decorator.
    """
    for module in _BUILTIN_METRIC_MODULES:
        import_module(module)


def _load_metric_entry_points() -> dict[str, type[Metric]]:
    """Load out-of-tree metrics from the entry-point group, deduped by name.

    In-tree builtins take precedence: an entry point reusing a registered name is
    ignored.
    """
    discovered: dict[str, type[Metric]] = {}
    for ep in metadata.entry_points(group=ENTRY_POINT_GROUP):
        if ep.name in _METRIC_REGISTRY or ep.name in discovered:
            continue
        discovered[ep.name] = ep.load()
    return discovered


def _builtin_family(cls: type[Metric]) -> str | None:
    """The builtin package ``cls`` is defined in, or ``None`` for a metric registered elsewhere.

    Example: ``_builtin_family(type(get_metric("dit")))`` is
    ``"coding_agent_playbook.grading.static_metrics"``.
    """
    module = cls.__module__
    if module not in _BUILTIN_METRIC_MODULES:
        return None
    return module.rpartition(".")[0]


def _family_block(family: str) -> dict[str, type[Metric]]:
    """The registered metrics of the builtin ``family``, in :data:`_BUILTIN_METRIC_MODULES` order."""
    members = [item for item in _METRIC_REGISTRY.items() if _builtin_family(item[1]) == family]
    members.sort(key=lambda item: _BUILTIN_METRIC_MODULES.index(item[1].__module__))
    return dict(members)


def _registry_in_family_blocks() -> dict[str, type[Metric]]:
    """The metric registry in the order the families' package ``__init__`` files gave it.

    Importing any module of a family used to register the whole family as one block,
    in package order. So a family lists, in :data:`_BUILTIN_METRIC_MODULES` order, where
    its first-registered module stands, and any other metric keeps its own place.
    Example: when ``diff_coverage`` registered first, ``coverage``, ``diff_coverage``
    and ``test_pass_rate`` lead, then the static metrics.
    """
    ordered: dict[str, type[Metric]] = {}
    for name, cls in _METRIC_REGISTRY.items():
        family = _builtin_family(cls)
        if family is None:
            ordered[name] = cls
        elif name not in ordered:
            ordered.update(_family_block(family))
    return ordered


def all_metrics() -> list[Metric]:
    """Every metric: builtins (decorator) + entry points, deduped by name."""
    _load_metric_builtins()
    classes: dict[str, type[Metric]] = _registry_in_family_blocks()
    for name, cls in _load_metric_entry_points().items():
        classes.setdefault(name, cls)
    return [cls() for cls in classes.values()]


def static_metrics() -> list[Metric]:
    """Metrics that need no runnable project (ast/radon over a parsed module).

    Excludes execution metrics (``needs_project=True``): the ``needs_project``
    flag - not the scope axis - is the static-vs-execution discriminator, since a
    FILE-scope metric like ``coverage`` is *execution*, not static.
    """
    return [m for m in all_metrics() if not m.needs_project]


def execution_metrics() -> list[Metric]:
    """Metrics that need a runnable project (``coverage``, ``test_pass_rate``)."""
    return [m for m in all_metrics() if m.needs_project]


def get_metric(name: str) -> Metric:
    """Return a fresh instance of the metric registered under ``name``.

    Raises :exc:`KeyError` if no builtin or entry point provides it.
    """
    _load_metric_builtins()
    if name in _METRIC_REGISTRY:
        return _METRIC_REGISTRY[name]()
    entry = _load_metric_entry_points()
    if name in entry:
        return entry[name]()
    raise KeyError(f"no metric registered under {name!r}")


# ``Scope`` is re-exported for the rare caller that wants the metric module as a
# one-stop import; the builtins import it from ``scope`` directly.
__all__ = [
    "ENTRY_POINT_GROUP",
    "Metric",
    "Scope",
    "all_metrics",
    "execution_metrics",
    "get_metric",
    "register_metric",
    "static_metrics",
]
