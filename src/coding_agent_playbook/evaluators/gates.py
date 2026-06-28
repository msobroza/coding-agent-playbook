"""The gate registry — named, composed boolean :class:`Check` gates by name.

A *gate* is a code-defined, composed boolean
:class:`~coding_agent_playbook.evaluators.check.Check` (typically an
``AllOf``/``AnyOf``/``Not`` tree over file/threshold/judge checks) that an
out-of-tree package ships and a task references by name (a later track wires a
task's ``[gate.bind] ref = "<name>"`` to :func:`get_gate`). This module is to a
composed gate what :mod:`coding_agent_playbook.evaluators.rubrics` is to a named
rubric: a verbatim mirror of that registry idiom.

:func:`register_gate` is a decorator **factory** keyed on an explicit ``name``
(a gate carries no intrinsic registry name), and the registry value is a
**factory** (``Callable[..., Check]``) that builds the composed gate when asked.
In-tree registrations win over an entry-point plugin of the same name. The engine
ships **no** builtin gates — this group is purely the third-party extension point
(like overlays, out-of-tree checks, and named rubrics).

Additive (Track C2): nothing in the eval/task pipeline consumes this registry yet.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import metadata

from coding_agent_playbook.evaluators.check import Check

#: Entry-point group for out-of-tree composed gates.
ENTRY_POINT_GROUP = "coding_agent_playbook.gates"

#: name -> gate factory, populated by the :func:`register_gate` decorator on import.
_GATE_REGISTRY: dict[str, Callable[..., Check]] = {}

#: The decorated callable's own type, preserved by :func:`register_gate`.
_GateFactory = Callable[..., Check]
_GateDecorator = Callable[[_GateFactory], _GateFactory]


def register_gate(name: str) -> _GateDecorator:
    """Decorator factory registering a gate factory under ``name``.

    Unlike :func:`~coding_agent_playbook.evaluators.metric.register_metric` (which
    keys on the metric's intrinsic ``cls.name``), a gate has no such field, so the
    registry key is the explicit string argument::

        @register_gate("must-touch-tests")
        def must_touch_tests() -> Check:
            return AllOf(FileExistsCheck("tests/"), ...)

    Returns the callable unchanged so the decorated name still binds normally.
    """

    def decorate(factory: _GateFactory) -> _GateFactory:
        _GATE_REGISTRY[name] = factory
        return factory

    return decorate


def _load_gate_entry_points() -> dict[str, Callable[..., Check]]:
    """Load out-of-tree gates from the entry-point group, deduped by name.

    In-tree registrations take precedence: an entry point reusing a registered
    name is ignored (mirrors
    :func:`~coding_agent_playbook.evaluators.rubrics._load_rubric_entry_points`).
    """
    discovered: dict[str, Callable[..., Check]] = {}
    for ep in metadata.entry_points(group=ENTRY_POINT_GROUP):
        if ep.name in _GATE_REGISTRY or ep.name in discovered:
            continue
        discovered[ep.name] = ep.load()
    return discovered


def get_gate(name: str) -> Check:
    """Return the *built* composed :class:`Check` registered under ``name``.

    Resolves the registered factory (in-tree registrations first, then entry
    points) and calls it (a 0-arg-or-kwargs factory returning a composed boolean
    gate). Raises :exc:`KeyError` when no registration or entry point provides
    ``name``.
    """
    if name in _GATE_REGISTRY:
        return _GATE_REGISTRY[name]()
    entry = _load_gate_entry_points()
    if name in entry:
        return entry[name]()
    raise KeyError(f"no gate registered under {name!r}")


def all_gate_names() -> list[str]:
    """Every known gate name: in-tree registrations + entry points, deduped.

    Order is registrations first (insertion order), then any entry-point names not
    already registered. Used to render a friendly "known gates" list on an unknown
    ``ref``.
    """
    names = list(_GATE_REGISTRY)
    for name in _load_gate_entry_points():
        if name not in _GATE_REGISTRY:
            names.append(name)
    return names


__all__ = [
    "ENTRY_POINT_GROUP",
    "all_gate_names",
    "get_gate",
    "register_gate",
]
