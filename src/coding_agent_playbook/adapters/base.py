"""Adapter ABC. See SPEC.md §10.1.

Concrete adapters (Continue, Claude Code, OpenCode, AGENTS.md) land in PRs 6-9.
Third-party adapters register via the ``coding_agent_playbook.adapters`` entry
point declared in ``pyproject.toml``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from coding_agent_playbook._file_identity import FileSet
from coding_agent_playbook._sentinel import has_sentinel

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

        Deletes exactly what :meth:`stale_outputs` reports and returns those
        paths. Subclasses customize *what* is stale by overriding
        :meth:`stale_outputs`, so ``playbook sync --check`` (which only asks)
        and write mode (which deletes) can never disagree.
        """
        stale = self.stale_outputs(written_paths, repo_root)
        for path in stale:
            path.unlink()
        return stale

    def stale_outputs(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Return the generated files :meth:`cleanup_stale` would delete, deleting nothing.

        ``playbook sync --check`` reports these as orphans without touching the
        tree (SPEC §12.3). The default is the sentinel scan of
        :meth:`_output_directories` (:meth:`_stale_by_sentinel`).

        Example::

            orphans = adapter.stale_outputs({p.resolve() for p in written}, repo_root)
        """
        return self._stale_by_sentinel(written_paths, repo_root)

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        """Directories the default cleanup scanner should walk.

        Subclasses override to point at the adapter's harness-specific output
        directories (e.g. ``.continue/rules``, ``.opencode/command``). The ABC
        default returns ``[]`` so any adapter that does not opt in is a no-op
        for cleanup — matching the behaviour declared by :meth:`cleanup_stale`.
        """
        return []

    def _default_cleanup(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Delete every file :meth:`_stale_by_sentinel` reports; return the deleted paths.

        Kept for adapters that override :meth:`cleanup_stale` and still want the
        shared directory scan.
        """
        stale = self._stale_by_sentinel(written_paths, repo_root)
        for path in stale:
            path.unlink()
        return stale

    def _stale_by_sentinel(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Sentinel-tagged files under :meth:`_output_directories` not in ``written_paths``.

        Files without the sentinel at an anchored position (:meth:`_carries_sentinel`)
        are user-authored and never reported. Binary or undecodable files are
        skipped silently so the scanner cannot crash a sync. "Not in
        ``written_paths``" compares file identity too, so after a case-only
        rename on a case-insensitive filesystem the file just written is never
        reported under its old name. Reads only; deletes nothing.
        """
        stale: list[Path] = []
        written = FileSet.of(written_paths)
        for output_dir in self._output_directories(repo_root):
            if not output_dir.is_dir():
                continue
            for path in output_dir.rglob("*"):
                if not path.is_file() or written.holds(path):
                    continue
                if self._carries_sentinel(path):
                    stale.append(path)
        return stale

    @staticmethod
    def _carries_sentinel(path: Path) -> bool:
        """Whether ``path`` is engine-generated per :func:`_sentinel.has_sentinel`.

        The sentinel line must be line 1, or the first body line after a
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
