"""The Check registry — built :class:`Check` instances by id prefix (FACTORIES).

This is to :class:`~coding_agent_playbook.grading.check.Check` what
:mod:`coding_agent_playbook.evals.compile.rubric_registry` is to ``Rubric`` and
:mod:`coding_agent_playbook.grading.metric` is to ``Metric``: a registry that
lets a task (and out-of-tree packages) build a check by a short id. It mirrors the
rubric idiom with one deliberate difference — the registry **values are
factories** (``Callable[..., Check]``), not zero-arg classes, because a check
takes ctor kwargs. A factory may be a plain function *or* a ``Check`` subclass
(both are callables): the file-check classes register directly (their
``(path=…)`` / ``(path=…, pattern=…)`` ctors are the factories), while the
metric-backed ``threshold`` / ``non_regression`` ids register helper factories
defined here that route through :func:`_resolve_metric_source`.

In-tree builtins win over an entry-point plugin of the same id
(``coding_agent_playbook.checks`` group). The metric-backed factories take exactly
one of ``metric=`` (a registered :class:`Metric` name) or ``judge=`` (a criterion
wrapped in a :class:`JudgeMetric`).

Acyclic by construction: :func:`register_check` and the registry dict are defined
*first*, before the module-level imports of the check classes; the check modules
import *back* only :func:`register_check` (no class-level dependency on the
factories), so there is no import cycle.

The task pipeline consumes this registry: the handle builder
(:mod:`coding_agent_playbook.evals.compile._handles`) routes a ``{check = "…"}`` (or
aggregate ``{metric = "…"}``) binding through :func:`get_check`.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module, metadata
from typing import TYPE_CHECKING, Final, TypeVar, cast

# ``Check`` (the ABC) is imported at runtime — its module never imports
# ``check_registry``, so this is acyclic; it lets the registry value type + the
# ``register_check`` TypeVar bound reference a real (non-string) ``Callable[...,
# Check]``. The cycle-sensitive concrete checks (``ThresholdCheck`` etc.) are
# imported *below* ``register_check`` instead.
from coding_agent_playbook.grading.check import Check

if TYPE_CHECKING:
    from coding_agent_playbook.grading.metric import Metric
    from coding_agent_playbook.grading.types import Mode

#: Entry-point group for out-of-tree custom grader checks.
ENTRY_POINT_GROUP = "coding_agent_playbook.checks"

#: id prefix -> factory, populated by the :func:`register_check` decorator on import.
_CHECK_REGISTRY: dict[str, Callable[..., Check]] = {}

#: The in-tree check modules besides this one: importing one fires its
#: ``@register_check``. A package ``__init__`` holds only a docstring (ADR 0002),
#: so the list names every module.
_BUILTIN_CHECK_MODULES: Final = ("coding_agent_playbook.grading.execution_checks",)

#: The decorated callable's own type, preserved by :func:`register_check` so a
#: decorated ``Check`` subclass stays a class (``type[FileExistsCheck]``) and a
#: factory function keeps its signature — only the registration is the side effect.
_F = TypeVar("_F", bound=Callable[..., Check])


def register_check(id_prefix: str) -> Callable[[_F], _F]:
    """Decorator factory registering a check factory under ``id_prefix``.

    The decorated callable is the factory — either a plain function returning a
    :class:`Check` or a ``Check`` subclass (both are callables)::

        @register_check("file_exists")
        class FileExistsCheck(_FileCheck): ...

        @register_check("threshold")
        def _threshold(*, metric=None, judge=None, ...) -> Check: ...

    Returns the callable unchanged (same type) so the decorated name still binds
    normally — a decorated class stays a class for ``isinstance`` and typing.
    """

    def decorate(factory: _F) -> _F:
        _CHECK_REGISTRY[id_prefix] = factory
        return factory

    return decorate


# The registry primitives above are defined *before* these imports so the check
# modules (which import ``register_check`` from this module) never observe a
# half-initialized registry — the cycle is broken by ordering, not laziness.
from coding_agent_playbook.grading.check import (  # noqa: E402
    NonRegressionCheck,
    ThresholdCheck,
)
from coding_agent_playbook.grading.judge_metric import JudgeMetric  # noqa: E402
from coding_agent_playbook.grading.metric import get_metric  # noqa: E402


def _resolve_metric_source(metric: str | None, judge: str | None) -> Metric:
    """Resolve the single metric source a metric-backed check grades over.

    Exactly one of ``metric`` (a registered :class:`Metric` name -> ``get_metric``)
    or ``judge`` (a criterion string -> :class:`JudgeMetric`) must be set. Passing
    both or neither is a :exc:`ValueError`.
    """
    if (metric is None) == (judge is None):
        raise ValueError(
            f"exactly one of metric= or judge= must be set (got metric={metric!r}, judge={judge!r})"
        )
    if metric is not None:
        return get_metric(metric)
    assert judge is not None  # narrowed by the XOR guard above
    return JudgeMetric(judge)


@register_check("threshold")
def _threshold(
    *,
    metric: str | None = None,
    judge: str | None = None,
    warn: float | None = None,
    fail: float | None = None,
    min_score: float | None = None,
    weight: float = 0.0,
    required: bool = True,
    mode: str = "absolute",
) -> Check:
    """Build a :class:`ThresholdCheck` over a metric *or* a judged criterion."""
    return ThresholdCheck(
        _resolve_metric_source(metric, judge),
        warn=warn,
        fail=fail,
        min_score=min_score,
        weight=weight,
        required=required,
        mode=cast("Mode", mode),
    )


@register_check("non_regression")
def _non_regression(
    *,
    metric: str | None = None,
    judge: str | None = None,
    max_worsening: float = 0.0,
    warn: float | None = None,
    fail: float | None = None,
    weight: float = 0.0,
    required: bool = True,
) -> Check:
    """Build a :class:`NonRegressionCheck` over a metric *or* a judged criterion."""
    return NonRegressionCheck(
        _resolve_metric_source(metric, judge),
        max_worsening=max_worsening,
        warn=warn,
        fail=fail,
        weight=weight,
        required=required,
    )


def _load_check_builtins() -> None:
    """Import the in-tree check modules so each module's ``@register_check`` fires.

    Imports every module of :data:`_BUILTIN_CHECK_MODULES` (the execution checks),
    populating the registry beside this module's own ``threshold`` /
    ``non_regression`` factories. The eval-only file, answer and aggregate checks
    register when the handle builder imports them.
    """
    for module in _BUILTIN_CHECK_MODULES:
        import_module(module)


# Importing the registry registers the execution checks right after ``threshold`` and
# ``non_regression``, as the package ``__init__`` did, so an eval family imported
# first never lists ahead of them in :func:`all_check_ids`.
_load_check_builtins()


def _load_check_entry_points() -> dict[str, Callable[..., Check]]:
    """Load out-of-tree check factories from the entry-point group, deduped by id.

    In-tree builtins take precedence: an entry point reusing a registered id is
    ignored (mirrors
    :func:`~coding_agent_playbook.grading.metric._load_metric_entry_points`).
    """
    discovered: dict[str, Callable[..., Check]] = {}
    for ep in metadata.entry_points(group=ENTRY_POINT_GROUP):
        if ep.name in _CHECK_REGISTRY or ep.name in discovered:
            continue
        discovered[ep.name] = ep.load()
    return discovered


def get_check(id_prefix: str, **kwargs: object) -> Check:
    """Build the :class:`Check` registered under ``id_prefix`` with ``kwargs``.

    Resolves the factory (in-tree builtins first, then entry points) and calls it
    with the caller's keyword arguments. Raises :exc:`KeyError` when no builtin or
    entry point provides ``id_prefix``.
    """
    _load_check_builtins()
    if id_prefix in _CHECK_REGISTRY:
        return _CHECK_REGISTRY[id_prefix](**kwargs)
    entry = _load_check_entry_points()
    if id_prefix in entry:
        return entry[id_prefix](**kwargs)
    raise KeyError(f"no check registered under {id_prefix!r}")


def all_check_ids() -> list[str]:
    """Every known check id: in-tree builtins + entry points, deduped.

    Order is builtins first (registration order), then any entry-point ids not
    already registered.
    """
    _load_check_builtins()
    ids = list(_CHECK_REGISTRY)
    for name in _load_check_entry_points():
        if name not in _CHECK_REGISTRY:
            ids.append(name)
    return ids


__all__ = [
    "ENTRY_POINT_GROUP",
    "all_check_ids",
    "get_check",
    "register_check",
]
