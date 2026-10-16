"""Output-policy glue for ``playbook sync`` (SPEC §12.2/§12.3, ``[output] commit``).

``commands/sync.py`` owns the render pipeline; this module owns what happens to
its output under the commit policy:

- write mode keeps the managed ``.gitignore`` block in step (or removes it for
  ``commit = true``) and warns about generated paths git still tracks;
- ``--check`` reports file drift, orphans ``playbook sync`` would delete, an
  unreadable lockfile and a stale/missing/malformed block;
- ``--check-staged`` lists staged paths that are generated output.

It never mutates git state — it only prints the ``git rm --cached`` command.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook._file_identity import FileSet
from coding_agent_playbook.gitignore import (
    GITIGNORE_FILENAME,
    LOCKFILE_NAME,
    apply_managed_block,
    block_is_current,
    entry_matches,
    ignore_entries,
    relative_posix_paths,
    remove_managed_block,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

    from coding_agent_playbook.git_client import GitClient

#: ``sync --check`` wording for an orphan (specs/prK-lifecycle-hooks.md §P P2).
ORPHAN_HINT = "    Orphaned generated file; run 'playbook sync' to remove."

# Filenames that are state-source-managed and must be excluded from the
# drift diff (otherwise the lockfile written by sync would itself look
# like drift). Keep this in sync with the constants in
# ``sources.filesystem.FileSystemStateSource``.
_STATE_FILES_TO_SKIP: tuple[str, ...] = (
    ".coding-agent-playbook.toml",
    ".coding-agent-playbook.local.toml",
    LOCKFILE_NAME,
)


def update_gitignore(repo_root: Path, written: Sequence[Path], *, commit: bool) -> str | None:
    """Apply (``commit=False``) or remove (``commit=True``) the managed block.

    Returns a one-line status for the sync summary, or ``None`` when the file
    was already up to date. ``ValueError`` from malformed markers propagates.

    Example::

        >>> update_gitignore(Path("."), [Path("AGENTS.md")], commit=False)  # doctest: +SKIP
        'Updated the managed block in .gitignore'
    """
    target = repo_root / GITIGNORE_FILENAME
    if commit:
        changed = remove_managed_block(target)
        return f"Removed the managed block from {GITIGNORE_FILENAME}" if changed else None
    changed = apply_managed_block(target, ignore_entries(written, repo_root))
    return f"Updated the managed block in {GITIGNORE_FILENAME}" if changed else None


def file_drift(written: Sequence[Path], scratch: Path, repo_root: Path) -> list[str]:
    """``--check``: drift lines for every scratch-rendered file missing/different on disk.

    ``_STATE_FILES_TO_SKIP`` (config + lockfile) are StateSource-owned, never
    adapter output, so they are excluded from the diff. A file missing because
    something on the real tree is in its way (a file/folder swap ``playbook
    sync`` refused, SPEC §10.8) names the blocker instead of suggesting a sync
    that cannot fix it.

    Example::

        >>> file_drift([], Path("/scratch"), Path("."))
        []
    """
    drift: list[str] = []
    for path in written:
        rel = path.resolve().relative_to(scratch.resolve())
        if rel.name in _STATE_FILES_TO_SKIP:
            continue
        actual_path = repo_root / rel
        if not actual_path.is_file():
            drift.append(f"  {rel.as_posix()}\n{_missing_hint(actual_path, repo_root)}")
        elif actual_path.read_bytes() != path.read_bytes():
            drift.append(
                f"  {rel.as_posix()}\n"
                "    Generated content differs from on-disk content.\n"
                "    Run 'playbook sync' to regenerate."
            )
    return drift


def orphan_drift(orphans: Sequence[Path], repo_root: Path) -> list[str]:
    """``--check``: one drift line per orphan ``playbook sync`` would delete.

    Each file is shown once (sorted), however many detectors found it — the
    adapters' sentinel cleanup and the lockfile leftover policy overlap for
    sentinel-tagged files. Unlike the ignore entries, an orphan whose target
    lies outside the repo (an output dir symlinked to a shared folder) is kept:
    write mode deletes it through the link, so the check must report it.

    Example::

        >>> lines = orphan_drift([Path("/r/.continue/rules/50-x.md")], Path("/r"))
        >>> lines[0].splitlines()[0]
        '  .continue/rules/50-x.md'
    """
    seen = FileSet()
    shown: set[str] = set()
    for path in orphans:
        if seen.holds(path):
            continue
        seen.add(path)
        shown.add(_display_path(path, repo_root))
    return [f"  {rel}\n{ORPHAN_HINT}" for rel in sorted(shown)]


def _display_path(path: Path, repo_root: Path) -> str:
    """``path`` as the user spells it: repo-relative (unresolved, so through a
    symlinked output dir), else resolved repo-relative, else absolute."""
    for candidate, root in ((path, repo_root), (path.resolve(), repo_root.resolve())):
        try:
            return candidate.relative_to(root).as_posix()
        except ValueError:
            continue
    return path.as_posix()


def unreadable_lockfile_drift(exc: Exception) -> list[str]:
    """``--check``: the drift line for a lockfile that cannot be read (never a traceback).

    Orphans cannot be judged without it (merge-conflict markers, a hand edit
    of the wrong type); ``playbook sync`` rewrites it.

    Example::

        >>> unreadable_lockfile_drift(ValueError("bad"))[0].splitlines()[0]
        '  .coding-agent-playbook.lock'
    """
    return [
        f"  {LOCKFILE_NAME}\n    Unreadable lockfile ({type(exc).__name__}: {exc}); "
        "run 'playbook sync' to rewrite it."
    ]


def _missing_hint(actual_path: Path, repo_root: Path) -> str:
    blocker = _blocker_of(actual_path, repo_root)
    if blocker is None:
        return "    Missing on disk; run 'playbook sync' to create."
    shown = blocker.relative_to(repo_root).as_posix()
    return (
        f"    Missing on disk: {shown} is in the way. 'playbook sync' replaces it only\n"
        "    when it holds nothing but unchanged files it wrote; otherwise move those\n"
        "    files, then re-run 'playbook sync'."
    )


def _blocker_of(actual_path: Path, repo_root: Path) -> Path | None:
    """A non-directory where a parent of ``actual_path`` must go, or a dir at it."""
    current = repo_root
    for part in actual_path.relative_to(repo_root).parts[:-1]:
        current = current / part
        if current.is_symlink() and not current.exists():
            return current
        if current.exists() and not current.is_dir():
            return current
    return actual_path if actual_path.is_dir() else None


def gitignore_drift(repo_root: Path, entries: Sequence[str]) -> list[str]:
    """``--check``: drift lines for the managed block (empty when current).

    Example::

        >>> gitignore_drift(Path("."), ["/AGENTS.md"])  # doctest: +SKIP
        []
    """
    try:
        if block_is_current(repo_root / GITIGNORE_FILENAME, entries):
            return []
    except ValueError as exc:
        return [
            f"  {GITIGNORE_FILENAME}\n    Malformed managed block: {exc}\n"
            "    Repair or delete the block markers, then run 'playbook sync'."
        ]
    return [
        f"  {GITIGNORE_FILENAME}\n"
        "    Managed block is missing or stale ([output] commit = false).\n"
        "    Run 'playbook sync' to regenerate."
    ]


def warn_tracked_output(repo_root: Path, written: Sequence[Path], git: GitClient) -> list[str]:
    """Warn on stderr about generated paths git still tracks; return them.

    Silent (returns ``[]``) when nothing is tracked or git cannot answer (not a
    repository, git missing, timeout). Never changes git state or exit codes.

    Example::

        >>> warn_tracked_output(Path("."), [Path("AGENTS.md")], FakeGitClient())  # doctest: +SKIP
        []
    """
    candidates = sorted({*relative_posix_paths(written, repo_root), LOCKFILE_NAME})
    tracked = git.tracked_paths(repo_root, candidates)
    if not tracked:
        return []
    print(
        "warning: generated output is still tracked by git, but [output] commit = false\n"
        "keeps it local-only (gitignored). Tracked paths:",
        file=sys.stderr,
    )
    _print_paths(tracked, file=sys.stderr)
    print("Stop tracking them (the files stay on disk) with:", file=sys.stderr)
    print(f"  {untrack_command(tracked, repo_root)}", file=sys.stderr)
    return tracked


def report_kept_leftovers(repo_root: Path, kept: Sequence[Path]) -> list[str]:
    """``commit = true``: list on stderr the leftovers an earlier sync left on disk; return them.

    Committed output is normally tracked by git, so the leftover policy keeps a
    removed skill's files instead of deleting them; without this note they would
    linger silently. (``commit = false`` reports tracked ones through
    :func:`warn_tracked_output`, and keeps the rest gitignored.) Silent when
    nothing is kept.

    Example::

        >>> report_kept_leftovers(Path("."), [])
        []
    """
    paths = relative_posix_paths(kept, repo_root)
    if not paths:
        return []
    print(
        "note: kept output an earlier sync wrote that this sync no longer generates\n"
        "(modified since, tracked by git, or an enabled adapter is missing):",
        file=sys.stderr,
    )
    _print_paths(paths, file=sys.stderr)
    print("Delete any you no longer need (git rm for tracked ones).", file=sys.stderr)
    return paths


def staged_generated_paths(staged: Sequence[str], entries: Sequence[str]) -> list[str]:
    """Return the ``staged`` paths covered by any managed-block entry.

    Example::

        >>> staged_generated_paths(["AGENTS.md", "src/a.py"], ["/AGENTS.md"])
        ['AGENTS.md']
    """
    return [path for path in staged if any(entry_matches(path, entry) for entry in entries)]


def report_staged_output(offenders: Sequence[str], repo_root: Path) -> None:
    """Explain (on stdout) why the ``--check-staged`` guard failed."""
    print("Generated output is staged for commit ([output] commit = false keeps it local-only):")
    _print_paths(offenders)
    print("Unstage it (the files stay on disk) with:")
    print(f"  {untrack_command(offenders, repo_root)}")


def untrack_command(paths: Sequence[str], repo_root: Path | None = None) -> str:
    """The exact, shell-quoted ``git rm -r --cached`` command for ``paths``.

    ``paths`` are relative to ``repo_root`` (git ran there), so when that is not
    the current directory — ``playbook sync --repo-root packages/foo`` from a
    monorepo root — the command is prefixed with ``git -C <repo_root>``; run
    bare, the paths would hit (or miss) the wrong files.

    Example::

        >>> untrack_command(["AGENTS.md", "a b.md"])
        "git rm -r --cached -- AGENTS.md 'a b.md'"
        >>> untrack_command(["AGENTS.md"], Path("/no/such/dir"))
        'git -C /no/such/dir rm -r --cached -- AGENTS.md'
    """
    git = (
        "git"
        if repo_root is None or _is_cwd(repo_root)
        else f"git -C {shlex.quote(str(repo_root))}"
    )
    return f"{git} rm -r --cached -- " + " ".join(shlex.quote(path) for path in paths)


def _is_cwd(path: Path) -> bool:
    """True when ``path`` is the current working directory (``False`` if unknowable)."""
    try:
        return path.resolve() == Path.cwd().resolve()
    except OSError:
        return False


def _print_paths(paths: Sequence[str], *, file: TextIO | None = None) -> None:
    """Print one indented path per line to ``file`` (default: stdout)."""
    for path in paths:
        print(f"  {path}", file=file)
