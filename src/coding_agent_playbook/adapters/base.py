"""Adapter ABC. See SPEC.md §10.1.

Concrete adapters (Continue, Claude Code, OpenCode, AGENTS.md) land in PRs 6-9.
Third-party adapters register via the ``coding_agent_playbook.adapters`` entry
point declared in ``pyproject.toml``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from coding_agent_playbook._file_identity import FileSet
from coding_agent_playbook.renderer import carries_engine_sentinel

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from coding_agent_playbook._typing import Prompt, Rule, Skill


class Adapter(ABC):
    """Translate canonical artifacts into a harness's native format."""

    name: str

    #: Repo-relative POSIX locations this adapter writes: a trailing ``/`` marks
    #: a directory (everything beneath it), anything else is one file. ``playbook
    #: sync`` deletes output an earlier sync left behind only inside a declared
    #: location (a hand-edited lockfile cannot point it at ``.git/`` or a source
    #: file) and never prunes empty directories above one (SPEC §4.2 step 9,
    #: §10.1). Declared on the class, so a since-disabled adapter still counts.
    output_locations: ClassVar[tuple[str, ...]] = ()

    #: Whether this adapter writes the sentinel as the first body line after a
    #: frontmatter block (frontmatter must stay on line 1 for its harness), so the
    #: default cleanup also recognises that position. Off by default: adapters
    #: that write the sentinel on line 1 keep the strict line-1 rule.
    sentinel_after_frontmatter: ClassVar[bool] = False

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
        support (``claude_code``, ``opencode``, ``shared_skills``) override this
        and delegate to the shared ``SkillWriter``; rules-only adapters (e.g.
        ``agents_md``) override it to return an empty list.
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
        walk the tree; for every engine-owned file (:func:`carries_engine_sentinel`:
        the :data:`SENTINEL` on line 1, or — when the adapter sets
        :attr:`sentinel_after_frontmatter` — the sentinel comment as the first
        line after a leading frontmatter block), delete it if its resolved path
        is not in ``written_paths``. Return the deleted paths.

        Files without the sentinel marker are user-authored and are never
        touched. Binary or undecodable files are skipped silently so the
        scanner cannot crash a sync. "Not in ``written_paths``" compares file
        identity too, so after a case-only rename on a case-insensitive
        filesystem the file just written is never deleted under its old name.
        """
        deleted: list[Path] = []
        written = FileSet.of(written_paths)
        for output_dir in self._output_directories(repo_root):
            if not output_dir.is_dir():
                continue
            for path in output_dir.rglob("*"):
                if not path.is_file():
                    continue
                if written.holds(path):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                if carries_engine_sentinel(text, after_frontmatter=self.sentinel_after_frontmatter):
                    path.unlink()
                    deleted.append(path)
        return deleted
