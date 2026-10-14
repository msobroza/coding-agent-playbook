"""Adapter ABC. See SPEC.md §10.1.

Concrete adapters (Continue, Claude Code, OpenCode, AGENTS.md) land in PRs 6-9.
Third-party adapters register via the ``coding_agent_playbook.adapters`` entry
point declared in ``pyproject.toml``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from coding_agent_playbook._sentinel import has_sentinel

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from coding_agent_playbook._typing import Prompt, Rule, Skill


class Adapter(ABC):
    """Translate canonical artifacts into a harness's native format."""

    name: str

    @abstractmethod
    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        """Write a rendered rule to the harness-specific location(s).

        Return the paths actually written. Adapters that route rules through
        another adapter (e.g. OpenCode -> AGENTS.md) return an empty list.
        """

    @abstractmethod
    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Write a rendered prompt and return the paths written."""

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Degrade a skill to a prompt.

        The default treats a skill as a prompt. Subclasses with native skill
        support override this, as do adapters whose harness reads another
        adapter's output (e.g. OpenCode reads ``.claude/skills/`` natively and
        returns an empty list).
        """
        return self.write_prompt(skill.to_prompt(), repo_root)

    def finalize(self, repo_root: Path) -> list[Path]:
        """Emit any buffered composite output. Default: nothing.

        Adapters that concatenate artifacts into a single file (e.g. Claude
        Code's ``CLAUDE.md``) override this and return the composed paths.
        """
        return []

    def cleanup_stale(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Remove generated files that no longer back a current artifact.

        Returns the deleted paths. Subclasses override only for custom cleanup.
        """
        return self._default_cleanup(written_paths, repo_root)

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        """Directories the default cleanup scanner should walk.

        Subclasses override to point at the adapter's harness-specific output
        directories (e.g. ``.continue/rules``, ``.opencode/command``). The ABC
        default returns ``[]`` so any adapter that does not opt in is a no-op
        for cleanup — matching the behaviour declared by :meth:`cleanup_stale`.
        """
        return []

    def _default_cleanup(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Default cleanup: for each directory in ``_output_directories``,
        walk the tree; for every file that :meth:`_carries_sentinel`, delete it
        if its resolved path is not in ``written_paths``. Return the deleted
        paths.

        Files without the sentinel marker are user-authored and are never
        touched. Binary or undecodable files are skipped silently so the
        scanner cannot crash a sync.
        """
        deleted: list[Path] = []
        for output_dir in self._output_directories(repo_root):
            if not output_dir.is_dir():
                continue
            for path in output_dir.rglob("*"):
                if not path.is_file() or path.resolve() in written_paths:
                    continue
                if self._carries_sentinel(path):
                    path.unlink()
                    deleted.append(path)
        return deleted

    @staticmethod
    def _carries_sentinel(path: Path) -> bool:
        """Whether ``path`` is engine-generated per :func:`_sentinel.has_sentinel`.

        The sentinel must sit on line 1, or on the first body line after a
        leading YAML frontmatter block; anywhere else it is user prose. Binary,
        undecodable or unreadable files count as user-owned (``False``), so a
        cleanup scan never crashes a sync.

        Example::

            if self._carries_sentinel(repo_root / "AGENTS.md"):
                ...  # engine-owned: safe to delete once stale
        """
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return False
        return has_sentinel(text)
