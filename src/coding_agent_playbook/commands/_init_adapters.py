"""The adapter list ``playbook init`` offers and writes (SPEC §12.1).

Split out of ``commands/init.py`` (over the module-size budget) so the default set,
the interactive choices and the flag help share one source of truth.
"""

from __future__ import annotations

from typing import Final

#: What ``playbook init`` enables when ``--adapters`` is absent. ``continue`` is
#: opt-in since SPEC v0.21: upstream Continue is in maintenance, and its IDE loads
#: the root AGENTS.md and ``.claude/skills/`` without an adapter of its own.
DEFAULT_ADAPTERS: Final[tuple[str, ...]] = ("claude_code", "opencode", "shared_skills")

#: The interactive choices: the defaults, then the opt-in harness adapter. Only
#: installed built-ins: the old ``codex`` choice named no adapter, and a missing
#: adapter makes every later sync keep all leftovers.
ADAPTER_CHOICES: Final[tuple[str, ...]] = (*DEFAULT_ADAPTERS, "continue")

ADAPTERS_QUESTION: Final = (
    "Which assistants will the team use? continue is opt-in; "
    "Codex reads AGENTS.md and .agents/skills/ (shared_skills)"
)

ADAPTERS_FLAG_HELP: Final = (
    f"comma-separated adapter names (default: {','.join(DEFAULT_ADAPTERS)}; add continue to opt in)"
)


def adapters_from_flag(raw: str | None) -> list[str]:
    """Parse ``--adapters``; absent or blank means :data:`DEFAULT_ADAPTERS`.

    Example::

        >>> adapters_from_flag(None)
        ['claude_code', 'opencode', 'shared_skills']
        >>> adapters_from_flag("continue, claude_code")
        ['continue', 'claude_code']
    """
    text = raw or ",".join(DEFAULT_ADAPTERS)
    return [name.strip() for name in text.split(",") if name.strip()]


def adapters_union(committed: list[str], answered: list[str]) -> list[str]:
    """The committed adapters in their order, then each answered one not listed yet.

    A re-run never drops an adapter the team enabled by hand (a committed
    ``continue`` stays), and adds the answered (default) ones it lacks.

    Example::

        >>> adapters_union(["continue", "custom"], ["claude_code", "continue"])
        ['continue', 'custom', 'claude_code']
    """
    return [*committed, *(name for name in dict.fromkeys(answered) if name not in committed)]
