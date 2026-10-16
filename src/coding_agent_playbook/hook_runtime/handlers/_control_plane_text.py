"""control-plane-guard's line-based verdicts: pre-commit ids and ``hooks:`` frontmatter (specs/prK-hook-pack.md §E.1).

Both files are YAML, and the hot path never loads ``yaml`` (§D.1), so each
verdict reads only the lines it needs:

- ``.pre-commit-config.yaml``: removing a hook whose id starts ``playbook-``
  or ``coding-agent-playbook-`` denies. :data:`PRECOMMIT_ID_RE` finds the
  ``id:`` lines; sync renders the ``precommit`` table with the same regex
  (:func:`playbook_precommit_ids`), so the two never disagree. Commenting a
  hook out removes its line, so it counts as a removal.
- a ``hooks:`` key in the leading frontmatter of a skill, command or agent
  file registers hooks when that artifact runs, which the agent can trigger:
  creating or editing that key asks.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.decision import Decision

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "PRECOMMIT_ID_RE",
    "frontmatter_hooks_verdict",
    "hooks_block",
    "playbook_precommit_ids",
    "precommit_verdict",
]

#: One hook ``id:`` line (block or ``- id:`` list style) naming a playbook hook.
PRECOMMIT_ID_RE: Final = re.compile(
    r"""^[ \t]*(?:-[ \t]+)?id:[ \t]*["']?((?:coding-agent-)?playbook-[A-Za-z0-9_.-]+)""",
    re.MULTILINE,
)
_FRONTMATTER: Final = re.compile(r"\A---[ \t]*\r?\n(.*?)^---[ \t]*\r?$", re.DOTALL | re.MULTILINE)
_HOOKS_KEY: Final = re.compile(r"""["']?hooks["']?[ \t]*:""")


def playbook_precommit_ids(text: str) -> list[str]:
    """The playbook hook ids ``text`` (a pre-commit config) declares, sorted and unique.

    Example::

        >>> playbook_precommit_ids("- id: playbook-sync-check\\n- id: ruff\\n")
        ['playbook-sync-check']
    """
    return sorted(set(PRECOMMIT_ID_RE.findall(text)))


def precommit_verdict(before: str | None, after: str, baseline: Iterable[str] = ()) -> Decision:
    """``DENY`` when the edit drops a playbook hook id, else ``NONE``.

    ``baseline`` (the sync-time ``precommit`` table) stands in for a file that
    is absent now, e.g. deleted by an earlier command.

    Example::

        >>> precommit_verdict("- id: playbook-x\\n", "repos: []\\n")
        <Decision.DENY: 'deny'>
    """
    kept = set(playbook_precommit_ids(after))
    had = set(baseline) if before is None else set(playbook_precommit_ids(before))
    return Decision.DENY if had - kept else Decision.NONE


def hooks_block(text: str | None) -> str | None:
    """The ``hooks:`` key of ``text``'s leading frontmatter with its nested lines, or ``None``.

    Example::

        >>> hooks_block("---\\nname: x\\nhooks:\\n  Stop: []\\n---\\nBody\\n")
        'hooks:\\n  Stop: []'
    """
    found = _FRONTMATTER.match(text or "")
    if found is None:
        return None
    lines = found.group(1).splitlines()
    for index, line in enumerate(lines):
        if _HOOKS_KEY.match(line):
            return "\n".join([line, *_nested(lines[index + 1 :])])
    return None


def frontmatter_hooks_verdict(before: str | None, after: str) -> Decision:
    """``ASK`` when the edit creates or changes a ``hooks:`` frontmatter key, else ``NONE``.

    Example::

        >>> frontmatter_hooks_verdict(None, "---\\nhooks: {}\\n---\\n")
        <Decision.ASK: 'ask'>
    """
    added = hooks_block(after)
    return Decision.ASK if added is not None and added != hooks_block(before) else Decision.NONE


def _nested(lines: list[str]) -> list[str]:
    """The lines below a key up to the next top-level key (YAML lists may sit at column 0)."""
    block: list[str] = []
    for line in lines:
        if line and not line[0].isspace() and not line.startswith("-"):
            break
        block.append(line)
    return block
