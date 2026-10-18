"""Structural schema of ``HOOK.md`` frontmatter: key sets, H8 contract keys, typed reads.

Also the vocabulary Literals and the two nested levels (``HookMatcher``,
``HookHandler``), whose public home is ``coding_agent_playbook.types``.

``HookFrontmatter.from_mapping`` (defined in ``_hook_frontmatter``, public home
``types``) uses this module to enforce H1 (unknown keys at every level, required
keys, types) and to give the H8 contract keys their own message. It checks
structure only. Value domains (canonical event names, per-event decisions, the id
pattern, timeout bounds: H2-H13) are left to ``hook_policy.classify_hook``, so
``playbook validate`` can report every problem of a hook at once instead of
stopping at the first (specs/prK-lifecycle-hooks.md §A.2, §B.5).

Split out of ``types.py`` for the file-size budget. It imports nothing from the
package, so ``types.py``, ``_hook_frontmatter.py`` and the stdlib-only
``hook_policy`` can all import it without a cycle.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, cast

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

HookEvent = Literal[
    "session_start",
    "user_prompt_submit",
    "pre_tool_use",
    "post_tool_use",
    "post_tool_use_failure",
    "stop",
    "subagent_stop",
    "pre_compact",
    "session_end",
]
HookDecision = Literal["deny", "ask", "context", "none"]
HookTier = Literal["default", "opt-in", "overlay"]
HookOnError = Literal["ask", "deny", "open"]
#: Authorable tool classes; the dispatcher adds the runtime-only ``other`` (H4).
ToolClass = Literal[
    "shell", "edit", "write", "notebook_edit", "read", "search", "web", "subagent", "mcp"
]
HookLauncher = Literal["python", "bash", "sh", "node"]

#: Top-level keys in §A.2 table order (the order error messages list them in).
TOP_KEYS: Final = (
    "id",
    "name",
    "description",
    "version",
    "tier",
    "enabled",
    "mandatory",
    "events",
    "matcher",
    "priority",
    "handler",
    "handlers",
    "decisions",
    "timeout",
    "on_error",
    "applies_if",
    "linked_rule",
    "supports",
    "tags",
)
#: ``handler``/``handlers`` presence is H6 (exactly one of them), not H1.
TOP_REQUIRED: Final = (
    "id",
    "name",
    "description",
    "tier",
    "events",
    "decisions",
    "timeout",
    "on_error",
    "supports",
)
HANDLER_KEYS: Final = ("builtin", "command", "script", "args", "config")
MATCHER_KEYS: Final = (
    "tools",
    "tool_names",
    "paths",
    "command",
    "sources",
    "triggers",
    "agent_types",
)
#: Claude Code handler keys for HTTP, async, prompt/agent and input-rewriting
#: handlers. They are unknown keys too, but get the contract message (H8) so an
#: author copying a Claude settings.json entry learns why, not just that.
CONTRACT_KEYS: Final = frozenset(
    {"type", "url", "headers", "async", "updated_input", "prompt", "model"}
)
CONTRACT_MESSAGE: Final = (
    "HTTP/async/rewrite handlers are not part of the hook contract (SPEC §17.1)"
)

#: The advisory-rule envelope (§A.8). Defined here, not in hook_policy.tables,
#: because types.py needs them and hook_policy will import types.py (cycle).
ADVISORY_RULE_PREFIX: Final = "guardrail-"
ADVISORY_RULE_PRIORITY: Final = 30


class HookSchemaError(ValueError):
    """Field-precise ``HOOK.md`` error carrying ``where``/``field``/``value``/``expected``.

    ``field`` is the dotted path of the offending key (``handler.args``,
    ``matcher.pre_tool_use.tools``). ``problem`` overrides the default
    ``expected …, got …`` detail for unknown, missing and contract keys.
    Re-exported as ``coding_agent_playbook.types.HookSchemaError``.

    Example::

        >>> str(HookSchemaError("hooks/x/HOOK.md", "timeout", "2s", "a number of seconds"))
        "hooks/x/HOOK.md: timeout: expected a number of seconds, got '2s'"
    """

    def __init__(
        self,
        where: str,
        field: str,
        value: object,
        expected: str,
        *,
        problem: str | None = None,
    ) -> None:
        self.where = where
        self.field = field
        self.value = value
        self.expected = expected
        detail = problem if problem is not None else f"expected {expected}, got {value!r}"
        super().__init__(f"{where}: {field}: {detail}")


@dataclass(frozen=True)
class FieldReader:
    """Typed reads of one frontmatter level; every error names ``where`` and the dotted field.

    A missing or blank (YAML ``key:``) optional value yields its default; a
    present value of the wrong type raises :class:`HookSchemaError`.

    Example::

        >>> FieldReader({"timeout": 2}, where="HOOK.md").seconds("timeout")
        2.0
    """

    data: Mapping[str, Any]
    where: str
    prefix: str = ""

    @classmethod
    def root(cls, data: object, *, where: str) -> FieldReader:
        """Reader over the whole frontmatter; rejects anything but a mapping."""
        if not isinstance(data, Mapping):
            raise HookSchemaError(where, "frontmatter", data, "a mapping")
        return cls(data, where)

    def path(self, key: object) -> str:
        """Dotted path of ``key`` at this level (``handler.args``)."""
        return f"{self.prefix}.{key}" if self.prefix else str(key)

    def _fail(self, key: str, expected: str) -> HookSchemaError:
        return HookSchemaError(self.where, self.path(key), self.data.get(key), expected)

    def check_keys(self, allowed: tuple[str, ...]) -> None:
        """Raise on the first key outside ``allowed`` (H1), contract keys first-class (H8)."""
        for key in self.data:
            if key in allowed:
                continue
            problem = (
                f"{key!r}: {CONTRACT_MESSAGE}"
                if key in CONTRACT_KEYS
                else f"unknown key {key!r}; allowed: {', '.join(allowed)}"
            )
            raise HookSchemaError(
                self.where, self.path(key), key, f"one of: {', '.join(allowed)}", problem=problem
            )

    def check_required(self, required: tuple[str, ...]) -> None:
        """Raise on the first key of ``required`` that is absent."""
        for key in required:
            if key not in self.data:
                raise HookSchemaError(
                    self.where, self.path(key), None, "a value", problem="missing required key"
                )

    def text(self, key: str) -> str:
        """A required string."""
        value = self.data.get(key)
        if not isinstance(value, str):
            raise self._fail(key, "a string")
        return value

    def optional_text(self, key: str) -> str | None:
        """A string, or ``None`` when missing or blank."""
        return None if self.data.get(key) is None else self.text(key)

    def integer(self, key: str, default: int) -> int:
        """An int (``bool`` is rejected: YAML ``true`` is not a priority)."""
        value = self.data.get(key)
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int):
            raise self._fail(key, "an integer")
        return value

    def flag(self, key: str, default: bool) -> bool:
        """A bool."""
        value = self.data.get(key)
        if value is None:
            return default
        if not isinstance(value, bool):
            raise self._fail(key, "a boolean")
        return value

    def seconds(self, key: str) -> float:
        """A required int or float, returned as float (``'2s'`` and ``true`` are rejected)."""
        value = self.data.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise self._fail(key, "a number of seconds")
        return float(value)

    def strings(self, key: str, *, required: bool = False) -> list[str]:
        """A list of strings; a missing or blank optional value is ``[]``."""
        value = self.data.get(key)
        if value is None and not required:
            return []
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise self._fail(key, "a list of strings")
        return list(value)

    def table(self, key: str) -> dict[str, Any]:
        """An opaque mapping (``config``, ``applies_if``); missing or blank is ``{}``."""
        value = self.data.get(key)
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise self._fail(key, "a mapping")
        return dict(value)

    def child(self, key: str) -> FieldReader | None:
        """Reader for a nested schema mapping (``handler``), ``None`` when missing or blank."""
        if self.data.get(key) is None:
            return None
        return FieldReader(self.table(key), self.where, self.path(key))

    def per_event(self, key: str) -> dict[str, FieldReader]:
        """Readers for an event-keyed mapping (``matcher``, ``handlers``).

        Event names are only checked to be strings here; whether they are
        canonical is H3/H4 (``classify_hook``). A blank entry reads as empty.
        """
        readers: dict[str, FieldReader] = {}
        for event, entry in self.table(key).items():
            if not isinstance(event, str):
                raise HookSchemaError(self.where, self.path(key), event, "an event name")
            entry_path = f"{self.path(key)}.{event}"
            if entry is not None and not isinstance(entry, Mapping):
                raise HookSchemaError(self.where, entry_path, entry, "a mapping")
            readers[event] = FieldReader(entry or {}, self.where, entry_path)
        return readers


def restore_defaults(instance: DataclassInstance) -> None:
    """Replace each explicit ``None`` with the field's own default, in place.

    YAML parses ``key:`` as None and a dataclass default does not fire for an
    explicit None; restoring it keeps the declared types and the markdown
    round trip lossless (SPEC §6.6.3). Fields defaulting to None and required
    fields are left alone, so their type check still reports the None.

    Example: ``HookHandler(args=None).args == []``.
    """
    for spec in dataclasses.fields(instance):
        if getattr(instance, spec.name) is not None:
            continue
        if spec.default_factory is not dataclasses.MISSING:
            setattr(instance, spec.name, spec.default_factory())
        elif spec.default is not dataclasses.MISSING:
            setattr(instance, spec.name, spec.default)


@dataclass
class HookMatcher:
    """Per-event filter; present dimensions are ANDed (§A.2).

    Example: ``HookMatcher(tools=["edit", "write"], paths=["src/**"])``.
    """

    tools: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    agent_types: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        restore_defaults(self)

    @classmethod
    def from_fields(cls, fields: FieldReader) -> HookMatcher:
        """Build from one ``matcher.<event>`` level, enforcing its key set (H1)."""
        fields.check_keys(MATCHER_KEYS)
        return cls(**{name: fields.strings(name) for name in MATCHER_KEYS})


@dataclass
class HookHandler:
    """Builtin (``builtin``) or external (``command`` + ``script`` + ``args``) handler.

    Example: ``HookHandler(builtin="guard_generated_outputs")``.
    """

    builtin: str | None = None
    command: HookLauncher | None = None
    script: str | None = None
    args: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        restore_defaults(self)

    @property
    def is_external(self) -> bool:
        """True for the external-command form (no registered builtin name)."""
        return self.builtin is None

    @classmethod
    def from_fields(cls, fields: FieldReader) -> HookHandler:
        """Build from one ``handler`` / ``handlers.<event>`` level, enforcing its key set (H1)."""
        fields.check_keys(HANDLER_KEYS)
        return cls(
            builtin=fields.optional_text("builtin"),
            command=cast("HookLauncher | None", fields.optional_text("command")),
            script=fields.optional_text("script"),
            args=fields.strings("args"),
            config=fields.table("config"),
        )


def drop_empty(data: Mapping[str, Any]) -> dict[str, Any]:
    """Shallow copy of ``data`` without ``None``, ``[]`` or ``{}`` values (``False``/``0`` stay)."""
    return {key: value for key, value in data.items() if value not in (None, [], {})}


def compact_frontmatter(data: Mapping[str, Any]) -> dict[str, Any]:
    """Drop empty values at every schema level: top, ``handler``, ``handlers.*``, ``matcher.*``.

    Opaque payloads (``config``, ``applies_if``) are kept verbatim: an empty
    list inside a handler's config is data (an ``extend`` key with no rows), not
    an omitted field. Event entries are kept even when they compact to ``{}``,
    so ``matcher: {stop: {}}`` round-trips equal (§A.4).

    Example::

        >>> compact_frontmatter({"handler": {"builtin": "x", "args": [], "script": None}})
        {'handler': {'builtin': 'x'}}
    """
    compact = drop_empty(data)
    if isinstance(compact.get("handler"), Mapping):
        compact["handler"] = drop_empty(compact["handler"])
    for key in ("handlers", "matcher"):
        if key in compact:
            compact[key] = {event: drop_empty(entry) for event, entry in compact[key].items()}
    return compact
