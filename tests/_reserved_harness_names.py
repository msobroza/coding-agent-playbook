"""The names each target harness reserves, as test data for the catalog's reserved-name gate.

A core prompt's slash, or a skill id of core or of a bundled plugin, that equals
one of these names shadows the harness's own command or skill in a synced repo
(ADR 0011, spec #270). The gate lives in
``tests/catalog/test_reserved_harness_names.py``; it is not a ``playbook validate``
check, so a harness release never fails a consumer's sync.

One frozenset per harness, so updating the names after a harness release is one
edit to that harness's set. Checked on 2026-10-24 against Claude Code 2.1.292,
OpenCode v1.19.4 and Codex 0.153.4 (and its main branch).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Claude Code: the official commands table with every alias, plus its bundled
#: skills (feature-gated ones included: a project skill with a bundled skill's
#: name replaces its slash command).
CLAUDE_CODE_RESERVED: Final = frozenset(
    {
        # Commands and their aliases.
        "add-dir",
        "agents",
        "allowed-tools",
        "android",
        "app",
        "bashes",
        "branch",
        "btw",
        "bug",
        "checkpoint",
        "chrome",
        "clear",
        "color",
        "compact",
        "config",
        "context",
        "continue",
        "copy",
        "cost",
        "desktop",
        "diff",
        "doctor",
        "effort",
        "exit",
        "export",
        "extra-usage",
        "fast",
        "feedback",
        "fork",
        "heapdump",
        "help",
        "hooks",
        "ide",
        "init",
        "insights",
        "install-github-app",
        "install-slack-app",
        "ios",
        "keybindings",
        "login",
        "logout",
        "mcp",
        "memory",
        "mobile",
        "model",
        "new",
        "output-style",
        "passes",
        "permissions",
        "plan",
        "plugin",
        "pr-comments",
        "privacy-settings",
        "quit",
        "rc",
        "release-notes",
        "reload-plugins",
        "remote-control",
        "remote-env",
        "rename",
        "reset",
        "resume",
        "review",
        "rewind",
        "sandbox",
        "settings",
        "skills",
        "stats",
        "status",
        "statusline",
        "stickers",
        "tasks",
        "terminal-setup",
        "theme",
        "todos",
        "upgrade",
        "usage",
        "vim",
        "voice",
        # Bundled skills, which the commands table also lists as commands.
        "batch",
        "claude-api",
        "code-review",
        "debug",
        "fewer-permission-prompts",
        "keybindings-help",
        "loop",
        "plugin-authoring",
        "pr",
        "prototype",
        "run",
        "schedule",
        "security-review",
        "simplify",
        "update-config",
        "verify",
        "workflow-authoring",
    }
)

#: OpenCode: the built-in prompt commands, the TUI slash commands with their
#: aliases, and the built-in skill.
OPENCODE_RESERVED: Final = frozenset(
    {
        # Built-in prompt commands.
        "init",
        "review",
        # TUI slash commands and their aliases.
        "clear",
        "compact",
        "connect",
        "continue",
        "details",
        "editor",
        "exit",
        "export",
        "help",
        "models",
        "new",
        "q",
        "quit",
        "redo",
        "resume",
        "sessions",
        "share",
        "summarize",
        "themes",
        "thinking",
        "undo",
        "unshare",
        # Built-in skill.
        "customize-opencode",
    }
)

#: Codex: the slash commands and the system skills (``plan`` is listed under
#: both, as the TUI command and as a probable system skill).
CODEX_RESERVED: Final = frozenset(
    {
        # Slash commands.
        "agent",
        "agents",
        "apps",
        "approvals",
        "clear",
        "collab",
        "compact",
        "copy",
        "debug-config",
        "diff",
        "exit",
        "experimental",
        "fast",
        "feedback",
        "fork",
        "init",
        "logout",
        "mcp",
        "mention",
        "model",
        "new",
        "permissions",
        "personality",
        "plan",
        "ps",
        "quit",
        "rename",
        "resume",
        "review",
        "sandbox-add-read-dir",
        "setup-default-sandbox",
        "skills",
        "status",
        "statusline",
        "theme",
        "undo",
        # System skills.
        "imagegen",
        "openai-docs",
        "review-agent",
        "skill-creator",
        "skill-installer",
    }
)

#: Harness display name -> the names it reserves; the gate names the harness on a collision.
RESERVED_HARNESS_NAMES: Final[Mapping[str, frozenset[str]]] = {
    "Claude Code": CLAUDE_CODE_RESERVED,
    "OpenCode": OPENCODE_RESERVED,
    "Codex": CODEX_RESERVED,
}
