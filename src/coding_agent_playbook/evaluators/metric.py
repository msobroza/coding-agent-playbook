"""The ``Metric`` ABC + the metric registry (T2 of the Metric/Check/Rubric split).

The ``Metric`` layer is the "measure" half of the clean-slate split that pulls
apart the fused :class:`~coding_agent_playbook.evaluators.registry.Evaluator`
into :class:`Metric` (measure) -> ``Check`` (grade) -> ``Rubric`` (aggregate). A
``Metric`` produces raw
:class:`~coding_agent_playbook.evaluators.types.Measurement` rows over a scope
and carries *only* the measurement-side descriptors (``name``, ``scope``,
``higher_is_worse``, ``requires``, ``needs_project``) - the grading-side
descriptors (thresholds, regression policy, weight) move to the ``Check`` layer.

T2 runs the ``Metric`` layer **in parallel** with the still-present
``Evaluator`` world: the old ``grade()``/scoring/CLI keep depending on the
``Evaluator`` builtins until the cutover track, so this module adds a second
registry without touching the first. Each ported builtin/execution module shares
its measurement compute through a module-level ``_measure`` function that BOTH the
``Evaluator`` and the ``Metric`` call - no duplicated logic.

Builtins self-register via the :func:`register_metric` decorator; out-of-tree
metrics register through the ``coding_agent_playbook.metrics`` entry-point group.
In-tree builtins always win over an entry point that reuses their name. (The
``pyproject.toml`` declaration of that group lands in a later track; T2 needs only
the decorator-driven builtins.)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import metadata
from importlib.util import find_spec
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.scope import Scope

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext, Measurement

#: Entry-point group for out-of-tree metrics (distinct from the Evaluator group).
ENTRY_POINT_GROUP = "coding_agent_playbook.metrics"

#: name -> Metric subclass, populated by the decorator on import.
_METRIC_REGISTRY: dict[str, type[Metric]] = {}


class Metric(ABC):
    """A raw measurement producer over a scope (the "measure" layer).

    Subclasses set the class-level measurement descriptors and implement
    :meth:`measure`. ``higher_is_worse`` keeps the exact name the ``Evaluator``
    builtins use (the measurement's intrinsic direction: ``True`` for CC/WMC/CBO/
    DIT/LCOM4 where larger is bad, ``False`` for MI/coverage/test-pass-rate where
    larger is good) so the ported pairs stay in lockstep. Grading-side concerns
    (absolute thresholds, regression tolerance, composite weight, score
    normalization) belong to the ``Check`` layer, not here.
    """

    name: str
    scope: Scope
    #: The measurement's intrinsic direction (kept name-identical to the
    #: ``Evaluator`` builtins for parity across the ported pair).
    higher_is_worse: bool
    #: Optional importable dependency/capability; ``None`` means stdlib-only.
    requires: str | None = None
    #: ``True`` for execution metrics that need a runnable project
    #: (``ctx.project``). This is the explicit "static vs execution"
    #: discriminator: :func:`static_metrics` excludes any metric with
    #: ``needs_project=True``.
    needs_project: bool = False

    def available(self, ctx: EvalContext) -> bool:
        """True when this metric can run in ``ctx``.

        Mirrors :meth:`Evaluator.available`: the declared dependency (if any) must
        be importable, and the needed context slot must be present - execution
        metrics (``needs_project``) need ``ctx.project``; static metrics need
        ``ctx.module``. Families that gate on a different slot (e.g. radon for MI)
        override this.
        """
        if self.requires is not None and find_spec(self.requires) is None:
            return False
        if self.needs_project:
            return ctx.project is not None
        return ctx.module is not None

    @abstractmethod
    def measure(self, ctx: EvalContext) -> list[Measurement]:
        """Produce one :class:`Measurement` per in-scope unit."""


def register_metric(cls: type[Metric]) -> type[Metric]:
    """Class decorator registering a :class:`Metric` subclass by ``name``."""
    _METRIC_REGISTRY[cls.name] = cls
    return cls


def _load_metric_builtins() -> None:
    """Import the builtin packages so each module's metric decorator fires.

    Imports both the static ``builtins`` package and the ``execution`` package so
    the metric registry sees the execution metrics (``test_pass_rate``,
    ``coverage``) alongside the static metrics. Importing these modules fires
    *both* the ``@register_evaluator`` and the ``@register_metric`` decorators -
    the two registries are populated from the same import.
    """
    import coding_agent_playbook.evaluators.builtins
    import coding_agent_playbook.evaluators.execution  # noqa: F401


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


def all_metrics() -> list[Metric]:
    """Every metric: builtins (decorator) + entry points, deduped by name."""
    _load_metric_builtins()
    classes: dict[str, type[Metric]] = dict(_METRIC_REGISTRY)
    for name, cls in _load_metric_entry_points().items():
        classes.setdefault(name, cls)
    return [cls() for cls in classes.values()]


def static_metrics() -> list[Metric]:
    """Metrics that need no runnable project (ast/radon over a parsed module).

    Excludes execution metrics (``needs_project=True``) - the same ``needs_project``
    discriminator the ``Evaluator`` ``static_evaluators()`` uses, since a
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
