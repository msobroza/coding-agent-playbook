"""``HookFrontmatter``: the static YAML frontmatter of ``HOOK.md`` (§A.2).

Split out of ``types.py`` for the file-size budget (specs/prS-skills-context.md
§6.4.1), which leaves ``types`` room to grow. ``types`` re-exports the class, so
every importer keeps ``from coding_agent_playbook.types import HookFrontmatter``.

A leaf module: it depends only on ``_hook_schema``, ``dataclasses`` and ``typing``,
never on ``types``, so ``types`` can import it without a cycle.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from coding_agent_playbook import _hook_schema as schema

# The four Literal aliases are imported at run time, not under TYPE_CHECKING, so the
# field annotations resolve in this module's namespace: typing.get_type_hints(
# HookFrontmatter) worked while the class lived in types.py, and the move keeps it so.
from coding_agent_playbook._hook_schema import HookDecision as HookDecision
from coding_agent_playbook._hook_schema import HookEvent as HookEvent
from coding_agent_playbook._hook_schema import HookHandler, HookMatcher, HookSchemaError
from coding_agent_playbook._hook_schema import HookOnError as HookOnError
from coding_agent_playbook._hook_schema import HookTier as HookTier

if TYPE_CHECKING:
    from collections.abc import Mapping


# The Literal-typed fields hold whatever string the author wrote: from_mapping
# checks structure (H1) and classify_hook checks value domains (H2-H13), so
# validate can aggregate every problem of a hook (§B.5).
@dataclass
class HookFrontmatter:
    """The static YAML frontmatter of ``HOOK.md`` (§A.2), parsed before any Jinja."""

    id: str
    name: str
    description: str
    tier: HookTier
    events: list[HookEvent]
    decisions: list[HookDecision]
    timeout: float
    on_error: HookOnError
    supports: list[str]
    handler: HookHandler | None = None  # exactly one of handler / handlers (H6)
    handlers: dict[str, HookHandler] = field(default_factory=dict)
    version: int = 1
    enabled: bool = True
    mandatory: bool = False
    priority: int = 50
    matcher: dict[str, HookMatcher] = field(default_factory=dict)
    applies_if: dict[str, Any] = field(default_factory=dict)
    linked_rule: str | None = None
    tags: list[str] = field(default_factory=list)
    #: The one-line guardrail (D6); ``""`` means "fall back to the body's first sentence".
    summary: str = ""

    def __post_init__(self) -> None:
        schema.restore_defaults(self)
        # timeout is float in TOML/JSON outputs; an authored `timeout: 2` is int.
        if isinstance(self.timeout, int) and not isinstance(self.timeout, bool):
            self.timeout = float(self.timeout)

    def handler_for(self, event: str) -> HookHandler:
        """The handler bound to ``event``: ``handlers[event]``, else the shared ``handler``.

        Example: ``fm.handler_for("pre_tool_use").builtin``.
        """
        if event in self.handlers:
            return self.handlers[event]
        if self.handler is not None:
            return self.handler
        raise HookSchemaError(
            f"hook {self.id!r}",
            "handlers",
            event,
            "a handler or a handlers entry",
            problem=f"no handler bound to event {event!r}",
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, where: str) -> HookFrontmatter:
        """Build the frontmatter, nested HookHandler/HookMatcher included, from parsed YAML.

        Raises HookSchemaError on an unknown key (H1; contract keys H8), a
        missing required key or a wrong type, naming the dotted field and value.
        Example: ``HookFrontmatter.from_mapping(yaml.safe_load(text), where="playbook/hooks/x/HOOK.md")``.
        """
        fields = schema.FieldReader.root(data, where=where)
        fields.check_keys(schema.TOP_KEYS)
        fields.check_required(schema.TOP_REQUIRED)
        handler = fields.child("handler")
        return cls(
            id=fields.text("id"),
            name=fields.text("name"),
            description=fields.text("description"),
            tier=cast("HookTier", fields.text("tier")),
            events=cast("list[HookEvent]", fields.strings("events", required=True)),
            decisions=cast("list[HookDecision]", fields.strings("decisions", required=True)),
            timeout=fields.seconds("timeout"),
            on_error=cast("HookOnError", fields.text("on_error")),
            supports=fields.strings("supports", required=True),
            handler=None if handler is None else HookHandler.from_fields(handler),
            handlers={
                e: HookHandler.from_fields(f) for e, f in fields.per_event("handlers").items()
            },
            version=fields.integer("version", 1),
            enabled=fields.flag("enabled", True),
            mandatory=fields.flag("mandatory", False),
            priority=fields.integer("priority", 50),
            matcher={e: HookMatcher.from_fields(f) for e, f in fields.per_event("matcher").items()},
            applies_if=fields.table("applies_if"),
            linked_rule=fields.optional_text("linked_rule"),
            tags=fields.strings("tags"),
            summary=fields.guardrail_summary("summary"),
        )

    def to_mapping(self) -> dict[str, Any]:
        """Inverse of from_mapping: ``asdict`` with empty values dropped at every schema level.

        An empty ``summary`` is dropped too (``drop_empty`` keeps ``""``), so a hook
        without one serializes byte-identically to the days before the field existed.
        """
        mapping = schema.compact_frontmatter(dataclasses.asdict(self))
        if not mapping.get("summary"):
            mapping.pop("summary", None)
        return mapping
