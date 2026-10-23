"""The ``guard_config.json`` contract names sync's writer shares with the runtime (specs/prT-package-layout.md 9 AC.2.5).

The runtime owns the contract: the file's repo-relative path and the lockfile's,
the ``schema_version`` it writes and the range the runtime reads, the hook output
directory, the pre-commit config and the regex that finds its playbook hook ids,
the format of a resource-root id, the engine's ``control_plane`` rows with the
policy key paths of its TOML verdicts, and the typed shape of one ``hooks.<id>``
record (:class:`HookRecordJson`, whose keys are :data:`HOOK_RECORD_KEYS`). Each
value has this one definition; sync's writer imports each name from here,
never from a handler module, and ``hook_runtime`` never imports the writer (ADR
0002's dependency order). The dispatcher loads this module on every event, so it
imports only the standard library.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, TypedDict

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "CONTROL_PLANE",
    "DEFAULT_POLICY_KEYS",
    "GUARD_CONFIG_REL",
    "GUARD_CONFIG_SCHEMA_VERSION",
    "HOOKS_OUTPUT_DIR",
    "HOOK_RECORD_KEYS",
    "LOCKFILE_REL",
    "PRECOMMIT_CONFIG",
    "PRECOMMIT_ID_RE",
    "RESOURCE_ROOT_ID_FORMAT",
    "SUPPORTED_SCHEMA_VERSIONS",
    "HandlerRecordJson",
    "HookRecordJson",
    "PolicyKeys",
    "playbook_precommit_ids",
]

GUARD_CONFIG_REL: Final = ".coding-agent-playbook/hooks/guard_config.json"
LOCKFILE_REL: Final = ".coding-agent-playbook.lock"
#: The ``schema_version`` sync writes; additive keys need no bump.
GUARD_CONFIG_SCHEMA_VERSION: Final = 1
#: The ``schema_version`` range this runtime reads: always up to the written version.
SUPPORTED_SCHEMA_VERSIONS: Final = (1, GUARD_CONFIG_SCHEMA_VERSION)
#: guard_config.json plus the copied scripts; protected as a whole tree (§E.1).
HOOKS_OUTPUT_DIR: Final = ".coding-agent-playbook/hooks/"
#: The pre-commit config whose playbook hook ids control-plane-guard keeps (§E.1).
PRECOMMIT_CONFIG: Final = ".pre-commit-config.yaml"

#: One hook ``id:`` line (block or ``- id:`` list style) naming a playbook hook.
PRECOMMIT_ID_RE: Final = re.compile(
    r"""^[ \t]*(?:-[ \t]+)?id:[ \t]*["']?((?:coding-agent-)?playbook-[A-Za-z0-9_.-]+)""",
    re.MULTILINE,
)


def playbook_precommit_ids(text: str) -> list[str]:
    """The playbook hook ids ``text`` (a pre-commit config) declares, sorted and unique.

    Example::

        >>> playbook_precommit_ids("- id: playbook-sync-check\\n- id: ruff\\n")
        ['playbook-sync-check']
    """
    return sorted(set(PRECOMMIT_ID_RE.findall(text)))


RESOURCE_ROOT_ID_FORMAT: Final = "pkg:{package}/resources"


@dataclass(frozen=True, slots=True)
class PolicyKeys:
    """The dotted policy key paths of each verdict row (the ``control_plane.toml_*`` table rows).

    Example: ``PolicyKeys().deny == ("hooks", "guardrails")``.
    """

    deny: tuple[str, ...] = ("hooks", "guardrails")
    ask: tuple[str, ...] = ("framework", "adapters_enabled", "detector_cache", "engine.version")
    ask_removals: tuple[str, ...] = ("overlays_enabled",)
    ask_additions: tuple[str, ...] = ("links.allowed_domains",)
    loosening: tuple[str, ...] = ("metrics",)

    @property
    def every(self) -> tuple[str, ...]:
        """Every policy key path, in row order."""
        return (*self.deny, *self.ask, *self.ask_removals, *self.ask_additions, *self.loosening)


DEFAULT_POLICY_KEYS: Final = PolicyKeys()

#: The engine's control-plane rows (runtime glob grammar; a bare name is an exact
#: repo-root path). ``toml_*`` are the policy key paths of the config verdicts.
CONTROL_PLANE: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "settings": (".claude/settings.json", ".claude/settings.local.json"),
        "user_settings": ("settings.json", "settings.local.json"),
        "config": (".coding-agent-playbook.toml",),
        "local_config": (".coding-agent-playbook.local.toml",),
        "mcp": (".mcp.json",),
        "opencode_config": ("opencode.json", "opencode.jsonc"),
        "precommit": (".pre-commit-config.yaml",),
        # The engine checkout's hooks live in its catalog (SPEC v0.19).
        "hook_sources": (
            "playbook/hooks/",
            "src/*/resources/hooks/",
            "catalog/core/hooks/",
            "catalog/plugins/*/hooks/",
        ),
        "plugin_carriers": (
            ".claude/skills/*/.claude-plugin/",
            "**/hooks/hooks.json",
            ".opencode/plugin/",
            ".opencode/plugins/",
            ".opencode/tool/",
            ".opencode/tools/",
        ),
        "frontmatter_carriers": (".claude/skills/", ".claude/commands/", ".claude/agents/"),
        "toml_deny": DEFAULT_POLICY_KEYS.deny,
        "toml_ask": DEFAULT_POLICY_KEYS.ask,
        "toml_ask_removals": DEFAULT_POLICY_KEYS.ask_removals,
        "toml_ask_additions": DEFAULT_POLICY_KEYS.ask_additions,
        "toml_loosening": DEFAULT_POLICY_KEYS.loosening,
    }
)


# The required part lives in its own class because the module's postponed
# annotations hide ``NotRequired``/``Required`` from ``__required_keys__`` at run
# time; per-class totality keeps the run-time key sets right on every Python.
class _HandlerRecordRequired(TypedDict):
    kind: str
    config: dict[str, Any]


class HandlerRecordJson(_HandlerRecordRequired, total=False):
    """One ``hooks.<id>.handlers.<event>`` record: ``kind`` and ``config``, plus where it runs.

    A ``builtin`` handler carries ``name``, an ``entry_point`` one ``target`` and
    ``dist``, an ``external`` one ``argv`` (``hook_records.parse_hook_record``
    reads it back).

    Example: ``{"kind": "builtin", "name": "guard_x", "config": {}}``.
    """

    name: str | None
    target: str | None
    dist: str | None
    argv: list[str]


class HookRecordJson(TypedDict):
    """One ``guard_config.json`` ``hooks.<id>`` record, as sync writes it and the runtime reads it.

    Built by ``hooks.resolution.resolved.ResolvedHook.to_json``; parsed field by
    field by ``hook_records.parse_hook_record``. ``matcher`` maps each event to its
    matcher keys, each a list of strings.

    Example: ``record["timeout_ms"] == 2000``.
    """

    id: str
    source_package: str
    events: list[str]
    priority: int
    matcher: dict[str, dict[str, list[str]]]
    handlers: dict[str, HandlerRecordJson]
    decisions: list[str]
    timeout_ms: int
    on_error: dict[str, str]
    supports: list[str]
    mandatory: bool
    script_sha256: str | None


#: The keys of every ``hooks.<id>`` record, no more and no fewer.
HOOK_RECORD_KEYS: Final[frozenset[str]] = HookRecordJson.__required_keys__
