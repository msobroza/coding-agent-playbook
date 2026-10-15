"""Adapter ABC. See SPEC.md §10.1.

Concrete adapters (Continue, Claude Code, OpenCode, AGENTS.md) land in PRs 6-9.
Third-party adapters register via the ``coding_agent_playbook.adapters`` entry
point declared in ``pyproject.toml``.

The lifecycle-hook additions (specs/prK-lifecycle-hooks.md §C.1.1) are all
concrete defaults, like ``write_skill``: an ``@abstractmethod`` would break
every third-party adapter written before hooks existed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar

from coding_agent_playbook._file_identity import FileSet
from coding_agent_playbook._sentinel import file_has_sentinel
from coding_agent_playbook.security.files import is_secret_file, user_home

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from coding_agent_playbook._typing import Prompt, Rule, Skill
    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.hooks_config import HooksConfig
    from coding_agent_playbook.lockfile import LockEntry, Lockfile


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

    #: Canonical hook event -> the decisions this adapter renders natively. The
    #: empty default means advisory-only: hooks degrade to text (§C.1.1, §C.5.1).
    #: Built-in hook-capable adapters take their row from ``hook_policy.HOOK_SUPPORT``.
    hook_support: ClassVar[Mapping[str, frozenset[str]]] = MappingProxyType({})

    #: Repo-relative files this adapter co-owns with the user and the harness
    #: (Claude Code's ``.claude/settings.json``): it edits managed elements in
    #: place, so ``playbook sync`` never gives one a whole-file lock entry,
    #: gitignores it, flags it as staged output, or deletes it.
    shared_outputs: ClassVar[tuple[str, ...]] = ()

    #: Repo-relative files :meth:`finalize` writes that are hook runtime plumbing
    #: (the Claude Code launcher, the OpenCode shim), not composed artifacts: their
    #: lock entries get ``kind = "runtime"`` and no artifact id (§B.6), which tells
    #: guard-generated-outputs there is no source artifact to point an editor at.
    runtime_outputs: ClassVar[tuple[str, ...]] = ()

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

    # Concrete on purpose (B027): an abstract hook would break every out-of-tree adapter.
    def begin_sync(  # noqa: B027
        self,
        repo_root: Path,
        prior_lock: Lockfile | None,
        *,
        hooks_config: HooksConfig | None = None,
    ) -> None:
        """Called once per sync before any ``write_*``. Default: no-op.

        ``repo_root`` is the real repository (the input root), even when output
        goes to a scratch directory (``sync --check``): adapters that own
        sub-file regions read the co-owned file and their prior ownership hashes
        from ``prior_lock`` here. ``hooks_config`` is the parsed ``[hooks]`` table.

        Example::

            adapter.begin_sync(ctx.repo_root, state_source.load_lockfile())
        """

    def write_hook(self, hook: ResolvedHook, repo_root: Path) -> list[Path]:
        """Degrade a hook to advisory text: its advisory rule goes through :meth:`write_rule`.

        Mirrors ``write_skill`` -> ``to_prompt``. Hook-capable adapters override
        and fall back to ``super().write_hook`` for hooks they cannot enforce. A
        hook whose body is blank (or whose advisory is off) degrades to nothing.

        Example::

            written = adapter.write_hook(hook, repo_root)  # e.g. 30-guardrail-<id>.md
        """
        rule = hook.advisory
        return [] if rule is None else self.write_rule(rule, repo_root)

    def managed_lock_entries(self) -> list[LockEntry]:
        """Sub-file ownership records (scoped lock entries) of the last :meth:`finalize`.

        Default: ``[]``. The Claude Code adapter returns one per managed
        ``settings.json`` element, including the ones this sync left unchanged.
        """
        return []

    def finalize(self, repo_root: Path) -> list[Path]:
        """Emit any buffered composite output. Default: nothing.

        Adapters that concatenate artifacts into a single file (e.g. Claude
        Code's ``CLAUDE.md``) override this and return the composed paths.
        """
        return []

    def cleanup_stale(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Remove generated files that no longer back a current artifact.

        Deletes exactly what :meth:`stale_outputs` reports and returns those
        paths. Do not override it: subclasses customize *what* is stale by
        overriding :meth:`stale_outputs`, so ``playbook sync --check`` (which
        only asks) and write mode (which deletes) can never disagree (SPEC
        §10.1). A path already gone (reported twice by an override) is skipped.
        """
        stale = self.stale_outputs(written_paths, repo_root)
        for path in stale:
            path.unlink(missing_ok=True)
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

        Deprecated, kept only so an out-of-tree adapter written against the
        pre-v0.16 contract (SPEC §10.1: ``cleanup_stale`` returning
        ``self._default_cleanup(...)``) keeps working. Override
        :meth:`stale_outputs` instead.
        """
        stale = self._stale_by_sentinel(written_paths, repo_root)
        for path in stale:
            path.unlink(missing_ok=True)
        return stale

    def _stale_by_sentinel(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Sentinel-tagged files under :meth:`_output_directories` not in ``written_paths``.

        Files without the sentinel at an anchored position (:meth:`_carries_sentinel`)
        are user-authored and never reported. Binary or undecodable files are
        skipped silently so the scanner cannot crash a sync, and only the files
        :meth:`_scan_targets` admits are opened. "Not in ``written_paths``"
        compares file identity too, so after a case-only rename on a
        case-insensitive filesystem the file just written is never reported
        under its old name. Reads only; deletes nothing.
        """
        written = FileSet.of(written_paths)
        candidates = (
            path
            for output_dir in self._output_directories(repo_root)
            if output_dir.is_dir()
            for path in output_dir.rglob("*")
        )
        return [
            path
            for path in self._scan_targets(candidates, repo_root)
            if not written.holds(path) and self._carries_sentinel(path)
        ]

    @staticmethod
    def _scan_targets(candidates: Iterable[Path], repo_root: Path) -> list[Path]:
        """The ``candidates`` a stale-output scan may open, each file once, in order.

        Skips non-files; symlinks (the engine never writes one into an output
        directory, so a link is the user's, and reading through it could leave
        the repo); and secret paths, by name or by target (SPEC §17.3: the
        engine never opens a credential file, so ``playbook sync --check`` run as
        a pre-commit hook cannot read one). A secret-named engine output is
        still settled by the lockfile leftover policy (SPEC §4.2 step 9). A file
        reached under two spellings (an output dir aliased to another by a
        symlink) is kept once, so ``cleanup_stale`` never unlinks it twice.

        Example::

            targets = Adapter._scan_targets((repo_root / ".continue").rglob("*"), repo_root)
        """
        home = user_home()
        seen = FileSet()
        targets: list[Path] = []
        for path in candidates:
            if path.is_symlink() or not path.is_file() or seen.holds(path):
                continue
            if is_secret_file(path, relative_to=repo_root, home=home):
                continue
            seen.add(path)
            targets.append(path)
        return targets

    @staticmethod
    def _carries_sentinel(path: Path) -> bool:
        """Whether ``path`` is engine-generated per :func:`_sentinel.file_has_sentinel`.

        The sentinel line must be line 1, or the first body line after a
        leading YAML frontmatter block; anywhere else it is user prose. Binary,
        undecodable or unreadable files count as user-owned (``False``), so a
        cleanup scan never crashes a sync. The read is bounded to that head and
        shared with the hook guards (specs/prK-hook-pack.md §E.1).

        Example::

            if self._carries_sentinel(repo_root / "AGENTS.md"):
                ...  # engine-owned: safe to delete once stale
        """
        return file_has_sentinel(path)
