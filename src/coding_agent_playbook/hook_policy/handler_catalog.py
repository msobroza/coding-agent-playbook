"""The registry half of the hook contract, at sync: which handlers exist and what they declare (§B.5, §D.3.1).

A builtin handler name resolves to the in-tree registry first (the runtime's
static module map), then to the ``coding_agent_playbook.hook_handlers``
entry-point group; in-tree wins, as in ``evaluators/checks/registry.py``. Sync
records an entry-point handler in ``guard_config.json`` as ``{"kind":
"entry_point", "target", "dist"}``, so the runtime never scans entry points.

From the declarations, validate closes the two halves K1 deferred:

- H6: the name is registered; the hook's ``decisions`` and bound events are
  ones the handler declares; ``MUTATES_INPUT`` is ``False``;
  ``mutates_edited_file`` only on an in-tree builtin of the engine's
  allowlist bound to ``post_tool_use`` (specs/prK-hook-pack.md §E.3); the
  authored ``handler.config`` keys are in its ``CONFIG_SCHEMA`` with the right kinds,
  and every pattern of a ``regex`` key passes ``screen_regex`` (specs/prK-hook-pack.md §E.4);
- H21: each consumer ``[hooks.<hook-id>]`` key is in that schema too.

:class:`RegistryCatalog` also implements ``ConfigSchemaLookup``, so the layer
merge uses the handlers' real key policies.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol

from coding_agent_playbook.hook_policy._contract_handlers import handler_slots
from coding_agent_playbook.hook_policy._findings import error
from coding_agent_playbook.hook_policy.merge import ConfigKeySpec
from coding_agent_playbook.hook_policy.tables import HOOK_EVENTS
from coding_agent_playbook.hook_runtime._config_keys import regex_of
from coding_agent_playbook.hook_runtime.registry import (
    HandlerResolutionError,
    builtin_handler_modules,
    declaration_of,
    edited_file_mutation_problem,
    load_builtin,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping

    from coding_agent_playbook.artifacts.hook_schema import HookHandler
    from coding_agent_playbook.hook_policy._findings import Finding
    from coding_agent_playbook.hook_runtime.registry import HandlerDeclaration
    from coding_agent_playbook.types import Hook

__all__ = [
    "ENTRY_POINT_GROUP",
    "CatalogEntry",
    "HandlerCatalog",
    "RegistryCatalog",
    "config_findings",
    "registry_findings",
]

ENTRY_POINT_GROUP: Final = "coding_agent_playbook.hook_handlers"
_DECISIONS: Final = frozenset({"deny", "ask", "context", "none"})


class EntryPointLike(Protocol):
    """The part of ``importlib.metadata.EntryPoint`` the catalog reads."""

    @property
    def name(self) -> str: ...

    @property
    def value(self) -> str: ...

    @property
    def dist(self) -> Any: ...

    def load(self) -> Any: ...


@dataclass(frozen=True)
class CatalogEntry:
    """One resolvable handler: its declaration and where it comes from.

    ``target`` / ``dist`` are set for an entry point (``pkg.mod:attr``,
    ``pkg==1.2.0``); ``problem`` instead of a declaration when it failed to load.

    Example: ``CatalogEntry("in_tree", declaration)``.
    """

    source: Literal["in_tree", "entry_point"]
    declaration: HandlerDeclaration | None
    target: str | None = None
    dist: str | None = None
    problem: str | None = None


class HandlerCatalog(Protocol):
    """Where sync looks handler names up; also a ``ConfigSchemaLookup`` for the merge."""

    def lookup(self, name: str) -> CatalogEntry | None: ...

    def known(self) -> tuple[str, ...]: ...

    def key_specs(self, builtin: str) -> Mapping[str, ConfigKeySpec]: ...

    def config_domain(self, builtin: str) -> str | None: ...


def _installed_entry_points() -> Iterable[EntryPointLike]:
    from importlib import metadata  # sync-time only; the runtime never scans (D-12)

    return metadata.entry_points(group=ENTRY_POINT_GROUP)


class RegistryCatalog:
    """The real catalog: the in-tree static map, then the entry-point group (in-tree wins).

    Example::

        >>> RegistryCatalog().lookup("no_such_handler") is None
        True
    """

    def __init__(
        self,
        *,
        modules: Mapping[str, str] | None = None,
        entry_points: Callable[[], Iterable[EntryPointLike]] = _installed_entry_points,
    ) -> None:
        self._modules = builtin_handler_modules() if modules is None else modules
        self._entry_points = entry_points
        self._by_name: dict[str, EntryPointLike] | None = None
        self._cache: dict[str, CatalogEntry | None] = {}

    def lookup(self, name: str) -> CatalogEntry | None:
        """The handler registered as ``name``, or ``None`` when nothing provides it."""
        if name not in self._cache:
            self._cache[name] = self._find(name)
        return self._cache[name]

    def known(self) -> tuple[str, ...]:
        """Every handler name the catalog can resolve, sorted."""
        return tuple(sorted({*self._modules, *self._group()}))

    def key_specs(self, builtin: str) -> Mapping[str, ConfigKeySpec]:
        """The merge policy of each config key ``builtin`` declares (``{}``: none)."""
        declaration = _declaration(self.lookup(builtin))
        if declaration is None:
            return MappingProxyType({})
        return MappingProxyType(
            {k: ConfigKeySpec(v.policy, v.order) for k, v in declaration.config_schema.items()}
        )

    def config_domain(self, builtin: str) -> str | None:
        """The ``[guardrails]`` domain ``builtin`` reads, or ``None``."""
        declaration = _declaration(self.lookup(builtin))
        return None if declaration is None else declaration.config_domain

    def _find(self, name: str) -> CatalogEntry | None:
        if name in self._modules:
            try:
                return CatalogEntry("in_tree", load_builtin(name, modules=self._modules))
            except HandlerResolutionError as exc:
                return CatalogEntry("in_tree", None, problem=str(exc))
        entry_point = self._group().get(name)
        return None if entry_point is None else _from_entry_point(entry_point)

    def _group(self) -> dict[str, EntryPointLike]:
        if self._by_name is None:
            self._by_name = {}
            for entry_point in self._entry_points():
                self._by_name.setdefault(entry_point.name, entry_point)
        return self._by_name


def _from_entry_point(entry_point: EntryPointLike) -> CatalogEntry:
    dist = entry_point.dist
    pinned = None if dist is None else f"{dist.name}=={dist.version}"
    try:
        declaration = declaration_of(entry_point.load())
    except Exception as exc:  # an overlay's import error is its own validate finding
        problem = f"entry point {entry_point.value!r} failed to load: {type(exc).__name__}"
        return CatalogEntry("entry_point", None, entry_point.value, pinned, problem)
    if declaration is None:
        problem = f"entry point {entry_point.value!r} is not a @register_hook_handler function"
        return CatalogEntry("entry_point", None, entry_point.value, pinned, problem)
    return CatalogEntry("entry_point", declaration, entry_point.value, pinned)


def _declaration(entry: CatalogEntry | None) -> HandlerDeclaration | None:
    return None if entry is None else entry.declaration


# --- H6: the hook against its handlers' declarations ------------------------------------------


def registry_findings(hook: Hook, catalog: HandlerCatalog) -> list[Finding]:
    """Every H6 registry finding of ``hook``'s builtin handlers.

    Example::

        >>> registry_findings(sample_hook(), RegistryCatalog())  # doctest: +SKIP
        [('error', "handler.builtin 'guard_x' is not a registered handler; known handlers: none")]
    """
    findings: list[Finding] = []
    for label, handler, events in _bound_slots(hook):
        if handler.builtin is None:
            continue
        entry = catalog.lookup(handler.builtin)
        findings.extend(_slot_findings(hook, label, handler, events, entry, catalog))
    return findings


def _bound_slots(hook: Hook) -> Iterator[tuple[str, HookHandler, tuple[str, ...]]]:
    """Each authored handler, its label and the events it is bound to."""
    fm = hook.frontmatter
    for label, handler in handler_slots(fm):
        events = tuple(fm.events) if label == "handler" else (label.removeprefix("handlers."),)
        yield label, handler, events


def _slot_findings(
    hook: Hook,
    label: str,
    handler: HookHandler,
    events: tuple[str, ...],
    entry: CatalogEntry | None,
    catalog: HandlerCatalog,
) -> Iterator[Finding]:
    name = handler.builtin
    if entry is None:
        known = ", ".join(catalog.known()) or "none"
        yield error(
            f"{label}.builtin {name!r} is not a registered handler; known handlers: {known}"
        )
        return
    declaration = entry.declaration
    if declaration is None:
        yield error(f"{label}.builtin {name!r}: {entry.problem}")
        return
    declared = {d.value for d in declaration.decisions} | {"none"}
    # A value outside the canonical four is H5's finding, an unknown event H3's.
    canonical = [d for d in dict.fromkeys(hook.frontmatter.decisions) if d in _DECISIONS]
    extra = [d for d in canonical if d not in declared]
    if extra:
        yield error(
            f"decisions {extra!r} are not declared by handler {name!r} "
            f"(it declares {', '.join(sorted(declared))})"
        )
    served = {e.value for e in declaration.events}
    unserved = [e for e in events if e in HOOK_EVENTS and e not in served]
    if unserved:
        yield error(
            f"{label}: handler {name!r} does not serve {unserved!r} (it serves {sorted(served)!r})"
        )
    if declaration.mutates_input:
        yield error(
            f"handler {name!r} declares MUTATES_INPUT = True; hooks never rewrite tool input (L6)"
        )
    in_tree = entry.source == "in_tree"
    mutation = edited_file_mutation_problem(declaration, in_tree=in_tree, events=events)
    if mutation is not None:
        yield error(mutation)
    yield from _config_problems(f"{label}.config", handler.config, declaration)


def _config_problems(
    where: str, config: Mapping[str, Any], declaration: HandlerDeclaration
) -> Iterator[Finding]:
    schema = declaration.config_schema
    for key, value in config.items():
        spec = schema.get(key)
        if spec is None:
            allowed = ", ".join(sorted(schema)) or "none"
            yield error(
                f"{where}.{key}: not a config key of handler {declaration.name!r}; allowed: {allowed}"
            )
        elif not spec.accepts(value):
            choices = f" one of {list(spec.order)}" if spec.kind == "string" and spec.order else ""
            shape = " list of patterns or {regex = ...} rows" if spec.kind == "regex" else ""
            yield error(f"{where}.{key}: expected a {spec.kind}{choices}{shape}, got {value!r}")
        elif spec.kind == "regex":
            yield from _regex_problems(f"{where}.{key}", value)


def _regex_problems(where: str, patterns: Iterable[object]) -> Iterator[Finding]:
    """H6/H21 for a ``regex`` key: every pattern must pass ``screen_regex`` (§E.4).

    The hooks run these patterns on agent-controlled text, so a pattern that
    backtracks catastrophically, or does not compile, is refused at validate.
    """
    from coding_agent_playbook.security.secrets import screen_regex

    for item in patterns:
        problem = screen_regex(regex_of(item) or "")
        if problem is not None:
            yield error(f"{where}: {problem}")


# --- H21: the consumer's [hooks.<hook-id>] against the schema --------------------------------


def config_findings(
    hooks: Iterable[Hook], per_hook: Mapping[str, Mapping[str, Any]], catalog: HandlerCatalog
) -> list[Finding]:
    """Every H21 finding of the consumer ``[hooks.<hook-id>]`` tables against the handlers' schemas.

    A key must belong to the schema of some builtin handler of the hook. Hooks
    whose handlers are all external pass their config to the script as JSON.

    Example::

        >>> config_findings([hook], {"guard-x": {"nope": 1}}, catalog)  # doctest: +SKIP
        [('error', "[hooks.guard-x] nope: not a config key of handler 'guard_x'; allowed: mode")]
    """
    by_id = {hook.frontmatter.id: hook for hook in hooks}
    findings: list[Finding] = []
    for hook_id, table in per_hook.items():
        hook = by_id.get(hook_id)
        declarations = [] if hook is None else _declarations(hook, catalog)
        if not declarations:
            continue  # an unknown id is contract_set's; an unregistered handler is H6's
        findings.extend(_table_problems(f"[hooks.{hook_id}]", table, declarations))
    return findings


def _declarations(hook: Hook, catalog: HandlerCatalog) -> list[HandlerDeclaration]:
    names = dict.fromkeys(h.builtin for _, h in handler_slots(hook.frontmatter) if h.builtin)
    found = (_declaration(catalog.lookup(name)) for name in names)
    return [declaration for declaration in found if declaration is not None]


def _table_problems(
    where: str, table: Mapping[str, Any], declarations: list[HandlerDeclaration]
) -> Iterator[Finding]:
    for key, value in table.items():
        owner = next((d for d in declarations if key in d.config_schema), None)
        if owner is None:
            allowed = (
                ", ".join(sorted({k for d in declarations for k in d.config_schema})) or "none"
            )
            names = ", ".join(repr(d.name) for d in declarations)
            yield error(f"{where} {key}: not a config key of handler {names}; allowed: {allowed}")
        else:
            for _, message in _config_problems(where, {key: value}, owner):
                yield error(message.replace(f"{where}.", f"{where} ", 1))
