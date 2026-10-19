"""The committed Claude Code launcher's path (specs/prK-lifecycle-hooks.md §C.2.3, §C.2.7).

A stdlib leaf, separate from :mod:`.claude`, because two layers read it: the Claude
registrations put the token in every handler ``command``, and the Claude Code
settings merge (``adapters/claude_code/settings/``) uses it to classify conflicts.
The merge must stay stdlib-only, which importing :mod:`.claude` would break, and
``hooks`` may not import the adapters above it (specs/prT-package-layout.md H15).

Example: ``LAUNCHER_PATH == LAUNCHER_TOKEN.lstrip("/")``.
"""

from __future__ import annotations

from typing import Final

__all__ = ["LAUNCHER_PATH", "LAUNCHER_TOKEN"]

#: The secondary ownership signal inside a handler ``command`` (§C.2.3).
LAUNCHER_TOKEN: Final = "/.claude/hooks/playbook/launch.sh"
#: The committed launcher, repo-relative (§C.2.7); its path token in a handler
#: ``command`` is the secondary ownership signal of the settings merge (§C.2.3).
LAUNCHER_PATH: Final = LAUNCHER_TOKEN.lstrip("/")
