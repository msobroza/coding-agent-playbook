"""The named-rubric registry — code-defined :class:`Rubric` subclasses by name.

This module is to :class:`~coding_agent_playbook.evaluators.rubric.Rubric` what
:mod:`coding_agent_playbook.evaluators.metric` is to ``Metric``: a registry that
lets an out-of-tree package ship a code-defined rubric (a :class:`Rubric`
subclass declaring its :attr:`~coding_agent_playbook.evaluators.rubric.Rubric.CRITERIA`)
and reference it from an eval ``task.toml`` via ``[rubric] ref = "<name>"``. It is
the bridge between a Python-defined rubric and the TOML authoring surface.

The registry mirrors the metric idiom with one deliberate difference:
:func:`register_rubric` is a decorator **factory** keyed on an explicit ``name``
argument (rubrics carry no intrinsic registry name the way a ``Metric`` carries
``cls.name``). In-tree registrations win over an entry-point plugin of the same
name. The engine ships **no** builtin rubrics - this group is purely the
third-party extension point (like overlays and out-of-tree checks).
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import metadata

from coding_agent_playbook.evaluators.rubric import Rubric

#: Entry-point group for out-of-tree named rubrics.
ENTRY_POINT_GROUP = "coding_agent_playbook.rubrics"

#: name -> Rubric subclass, populated by the :func:`register_rubric` decorator.
_RUBRIC_REGISTRY: dict[str, type[Rubric]] = {}

#: The class decorator :func:`register_rubric` returns (a rubric subclass in, the
#: same subclass out).
_RubricDecorator = Callable[[type[Rubric]], type[Rubric]]


def register_rubric(name: str) -> _RubricDecorator:
    """Decorator factory registering a :class:`Rubric` subclass under ``name``.

    Unlike :func:`~coding_agent_playbook.evaluators.metric.register_metric` (which
    keys on the metric's intrinsic ``cls.name``), a rubric has no such field, so
    the registry key is the explicit string argument::

        @register_rubric("code-review")
        class CodeReviewRubric(Rubric):
            CRITERIA = (("Findings prioritized", 1.0), ...)

    Returns the class unchanged so the decorated name still binds to the subclass.
    """

    def decorate(cls: type[Rubric]) -> type[Rubric]:
        _RUBRIC_REGISTRY[name] = cls
        return cls

    return decorate


def _load_rubric_entry_points() -> dict[str, type[Rubric]]:
    """Load out-of-tree rubrics from the entry-point group, deduped by name.

    In-tree registrations take precedence: an entry point reusing a registered
    name is ignored (mirrors
    :func:`~coding_agent_playbook.evaluators.metric._load_metric_entry_points`).
    """
    discovered: dict[str, type[Rubric]] = {}
    for ep in metadata.entry_points(group=ENTRY_POINT_GROUP):
        if ep.name in _RUBRIC_REGISTRY or ep.name in discovered:
            continue
        discovered[ep.name] = ep.load()
    return discovered


def get_rubric(name: str) -> Rubric:
    """Return the *built* :class:`Rubric` registered under ``name``.

    Resolves the registered class (in-tree registrations first, then entry
    points) and returns ``cls.define()`` - a built
    :class:`~coding_agent_playbook.evaluators.rubric.Rubric` instance whose checks
    are the subclass's :attr:`~coding_agent_playbook.evaluators.rubric.Rubric.CRITERIA`
    as :class:`~coding_agent_playbook.evaluators.checks.judged.JudgeCheck`\\ s.

    Raises :exc:`KeyError` when no registration or entry point provides ``name``.
    """
    if name in _RUBRIC_REGISTRY:
        return _RUBRIC_REGISTRY[name].define()
    entry = _load_rubric_entry_points()
    if name in entry:
        return entry[name].define()
    raise KeyError(f"no rubric registered under {name!r}")


def all_rubric_names() -> list[str]:
    """Every known rubric name: in-tree registrations + entry points, deduped.

    Order is registrations first (insertion order), then any entry-point names
    not already registered. Used by the validator to render a friendly "known
    rubrics" list on an unknown ``ref``.
    """
    names = list(_RUBRIC_REGISTRY)
    for name in _load_rubric_entry_points():
        if name not in _RUBRIC_REGISTRY:
            names.append(name)
    return names


__all__ = [
    "ENTRY_POINT_GROUP",
    "all_rubric_names",
    "get_rubric",
    "register_rubric",
]
