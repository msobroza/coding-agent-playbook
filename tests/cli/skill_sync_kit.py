"""Shared builders for the end-to-end native-skill ``playbook sync`` tests.

One home for the config that enables every native skills root and for reading
the lockfile's owned paths, so a change to the adapter list or to the lockfile
API is made once (``test_sync_skills.py``, ``test_sync_tool_caches.py``).

Example::

    repo = make_synthetic_repo(tmp_path, config_text=SHARED_SKILLS_CONFIG)
    assert ".claude/skills/demo/SKILL.md" in lock_entry_paths(repo)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.config.files import FileSystemStateSource

if TYPE_CHECKING:
    from pathlib import Path

#: A synthetic repo config whose adapters write every native skills root.
SHARED_SKILLS_CONFIG: Final = """\
schema_version = 1
adapters_enabled = ["continue", "claude_code", "opencode", "shared_skills"]
overlays_enabled = []

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"
"""


def lock_entry_paths(repo: Path) -> set[str]:
    """Every path the lockfile of ``repo`` owns; fails the test when there is no lockfile.

    Example: ``lock_entry_paths(repo)`` -> ``{".claude/skills/demo/SKILL.md", ...}``.
    """
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None, f"no lockfile in {repo}"
    return {entry.path for entry in lockfile.entries}
