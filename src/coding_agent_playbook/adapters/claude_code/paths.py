"""Where the ``claude_code`` adapter composes its rules (SPEC §10.3.1). Stdlib-only leaf.

The two repo-relative paths live here, apart from the adapter, so the sync-level
guard tables (``_guard_config_protect.COMPOSITE_SINGLETONS``) can name them
without importing the adapter and its renderer (jinja2, yaml).

Why two files: OpenCode v1 attaches ``.claude/CLAUDE.md`` when its read tool
opens a file under ``.claude/`` (once per uncompacted session, SPEC §10.6), so
the rule sections, hook advisories and heartbeat line moved to
:data:`CLAUDE_RULES_PATH`, which neither OpenCode v1.19.3 nor v2 (dev 24c7f7a)
discovers by default, and :data:`CLAUDE_MD_PATH` became a rule-free stub (the
full rationale is in :mod:`.adapter`).

Example::

    >>> CLAUDE_CODE_COMPOSITES
    ('.claude/CLAUDE.md', '.claude/rules/coding-agent-playbook.md')
"""

from __future__ import annotations

from typing import Final

__all__ = ["CLAUDE_CODE_COMPOSITES", "CLAUDE_MD_PATH", "CLAUDE_RULES_PATH"]

#: Rule-free stub. It must still exist: in Claude Code's default
#: ``claude-md-or-agents-md`` mode (v2.1.277+) a CLAUDE.md, .claude/CLAUDE.md or
#: CLAUDE.local.md in the working directory or above it stops Claude from also
#: reading the root AGENTS.md natively (the stub sits at the repo root, above
#: every in-repo launch directory), and a ``.claude/rules/`` file does not count
#: for that, so without the stub Claude would load the rules twice. It names no
#: rules file on purpose: OpenCode v1 still attaches it, and a pointer would
#: invite its model to read the rules again.
CLAUDE_MD_PATH: Final = ".claude/CLAUDE.md"
#: The rule sections, hook advisories and heartbeat line. No ``paths:``
#: frontmatter, so Claude Code always loads it; one engine-owned file, because
#: users own every other ``.claude/rules/*.md``.
CLAUDE_RULES_PATH: Final = ".claude/rules/coding-agent-playbook.md"
#: Both multi-source files the adapter's ``finalize`` composes, in the order it
#: returns them; the guard and drift tables treat each as a composite singleton.
CLAUDE_CODE_COMPOSITES: Final = (CLAUDE_MD_PATH, CLAUDE_RULES_PATH)
