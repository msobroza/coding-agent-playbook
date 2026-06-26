"""The ``Evaluator`` ABC + the evaluator registry (SPEC prM §A).

One abstraction unifies static metrics, execution metrics, and judged criteria:
each yields one :class:`~coding_agent_playbook.evaluators.types.Measurement` per
scope (feeding the gate) and a normalized ``to_score`` ``0-1`` (feeding the
weighted composite). Builtins self-register via the :func:`register_evaluator`
decorator; out-of-tree evaluators register through the
``coding_agent_playbook.evaluators`` entry-point group. In-tree builtins always
win over an entry point that reuses their name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import metadata
from importlib.util import find_spec
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import (
        AbsoluteThreshold,
        Measurement,
        RegressionPolicy,
        ResolvedPolicy,
    )

#: Entry-point group for out-of-tree evaluators.
ENTRY_POINT_GROUP = "coding_agent_playbook.evaluators"

#: name -> Evaluator subclass, populated by the decorator on import.
_REGISTRY: dict[str, type[Evaluator]] = {}


class Evaluator(ABC):
    """A graded measurement producer over a scope.

    Subclasses set the class-level descriptor attributes (``name``, ``scope``,
    ...) and implement :meth:`evaluate`. ``higher_is_worse`` is ``True`` for
    metrics where larger is bad (CC/WMC/CBO/DIT/LCOM4) and ``False`` where larger
    is good (MI/coverage/test-pass-rate/any SCORE).
    """

    name: str
    scope: Scope
    value_kind: ValueKind
    determinism: Determinism
    higher_is_worse: bool
    #: Optional importable dependency/capability; ``None`` means stdlib-only.
    requires: str | None = None
    default_absolute: AbsoluteThreshold
    default_regression: RegressionPolicy
    #: ``> 0`` => contributes to the weighted composite.
    default_weight: float = 0.0

    def available(self, ctx: EvalContext) -> bool:
        """True when this evaluator can run in ``ctx``.

        Default: the declared dependency (if any) is importable *and* the needed
        context is present. Static evaluators need ``ctx.module``; execution
        evaluators need ``ctx.project`` and judged ones ``ctx.judge`` (those
        families override this to check their own slot).
        """
        if self.requires is not None and find_spec(self.requires) is None:
            return False
        return ctx.module is not None

    @abstractmethod
    def evaluate(self, ctx: EvalContext) -> list[Measurement]:
        """Produce one :class:`Measurement` per in-scope unit."""

    def to_score(self, value: float, policy: ResolvedPolicy) -> float:
        """Normalize a raw value to ``0-1`` (higher = better) for the composite.

        ``SCORE``/``BOOL`` values are already normalized, so they are returned
        clamped to ``[0, 1]``. ``NUMERIC`` values ramp around the absolute
        warn/fail bounds: ``1.0`` at/under ``warn`` and ``0.0`` at/over ``fail``
        (linear between) when ``higher_is_worse``; the ramp inverts when larger
        is better. With no bounds the score is ``1.0`` (nothing to penalize).
        """
        if self.value_kind in (ValueKind.SCORE, ValueKind.BOOL):
            return _clamp01(value)

        warn = policy.absolute.warn
        fail = policy.absolute.fail
        if warn is None or fail is None or warn == fail:
            return 1.0

        if self.higher_is_worse:
            # warn is the good floor, fail the bad ceiling.
            if value <= warn:
                return 1.0
            if value >= fail:
                return 0.0
            return (fail - value) / (fail - warn)
        # higher is better: warn is the good target, fail the bad floor.
        if value >= warn:
            return 1.0
        if value <= fail:
            return 0.0
        return (value - fail) / (warn - fail)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def register_evaluator(cls: type[Evaluator]) -> type[Evaluator]:
    """Class decorator registering an :class:`Evaluator` subclass by ``name``."""
    _REGISTRY[cls.name] = cls
    return cls


def _load_builtins() -> None:
    """Import the builtins package so each module's decorator fires."""
    import coding_agent_playbook.evaluators.builtins  # noqa: F401


def _load_entry_points() -> dict[str, type[Evaluator]]:
    """Load out-of-tree evaluators from the entry-point group, deduped by name.

    In-tree builtins take precedence: an entry point reusing a registered name
    is ignored.
    """
    discovered: dict[str, type[Evaluator]] = {}
    for ep in metadata.entry_points(group=ENTRY_POINT_GROUP):
        if ep.name in _REGISTRY or ep.name in discovered:
            continue
        discovered[ep.name] = ep.load()
    return discovered


def all_evaluators() -> list[Evaluator]:
    """Every evaluator: builtins (decorator) + entry points, deduped by name."""
    _load_builtins()
    classes: dict[str, type[Evaluator]] = dict(_REGISTRY)
    for name, cls in _load_entry_points().items():
        classes.setdefault(name, cls)
    return [cls() for cls in classes.values()]


def static_evaluators() -> list[Evaluator]:
    """Deterministic, non-MODULE-scope evaluators (ast/radon static metrics)."""
    return [
        ev
        for ev in all_evaluators()
        if ev.determinism is Determinism.DETERMINISTIC and ev.scope is not Scope.MODULE
    ]


def deterministic_evaluators() -> list[Evaluator]:
    """Every deterministic evaluator (static + execution)."""
    return [ev for ev in all_evaluators() if ev.determinism is Determinism.DETERMINISTIC]


def get_evaluator(name: str) -> Evaluator:
    """Return a fresh instance of the evaluator registered under ``name``.

    Raises :exc:`KeyError` if no builtin or entry point provides it.
    """
    _load_builtins()
    if name in _REGISTRY:
        return _REGISTRY[name]()
    entry = _load_entry_points()
    if name in entry:
        return entry[name]()
    raise KeyError(f"no evaluator registered under {name!r}")


if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext
