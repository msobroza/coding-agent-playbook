"""The ``guard_config.json`` contract names sync's writer shares with the runtime (specs/prT-package-layout.md 9 AC.2.5).

The runtime owns the contract: the file's repo-relative path and the lockfile's,
the ``schema_version`` it writes and the range the runtime reads, the hook output
directory, the pre-commit config and the regex that finds its playbook hook ids,
the format of a resource-root id, and the engine's ``control_plane`` rows with the
policy key paths of its TOML verdicts. Sync's writer imports each name from here,
never from a handler module, and ``hook_runtime`` never imports the writer (ADR
0002's dependency order). The dispatcher loads this module on every event, so it
imports only the standard library.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "CONTROL_PLANE",
    "DEFAULT_POLICY_KEYS",
    "GUARD_CONFIG_REL",
    "GUARD_CONFIG_SCHEMA",
    "HOOKS_OUTPUT_DIR",
    "LOCKFILE_REL",
    "PRECOMMIT_CONFIG",
    "PRECOMMIT_ID_RE",
    "RESOURCE_ROOT_ID_FORMAT",
    "SUPPORTED_SCHEMA_VERSIONS",
    "PolicyKeys",
    "playbook_precommit_ids",
]

GUARD_CONFIG_REL: Final = ".coding-agent-playbook/hooks/guard_config.json"
LOCKFILE_REL: Final = ".coding-agent-playbook.lock"
#: The ``schema_version`` range this runtime reads; additive keys need no bump.
SUPPORTED_SCHEMA_VERSIONS: Final = (1, 1)
#: ``SUPPORTED_SCHEMA_VERSIONS`` must include it.
GUARD_CONFIG_SCHEMA: Final = 1
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
    ask: tuple[str, ...] = ("adapters_enabled", "detector_cache", "engine.version")
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
