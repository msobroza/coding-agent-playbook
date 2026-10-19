"""Output-policy glue for ``playbook sync`` (SPEC §12.2/§12.3, ``[output] commit``).

``sync/pipeline.py`` owns the render pipeline; this module owns what happens to
its output under the commit policy:

- write mode keeps the managed ``.gitignore`` block in step (or removes it for
  ``commit = true``) and warns about generated paths git still tracks;
- ``--check`` reports file drift, orphans ``playbook sync`` would delete, an
  unreadable lockfile and a stale/missing/malformed block;
- ``--check-staged`` lists staged paths that are generated output.

A **shared output** (an adapter's ``shared_outputs``: ``.claude/settings.json``,
co-owned with the user and the harness) is never generated output here: it is
dropped before the managed block, the tracked-output warning and the staged
guard (specs/prK-lifecycle-hooks.md §C.0, §B.6).

It never mutates git state — it only prints the ``git rm --cached`` command.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.skill_dirs.writer import swap_blocker
from coding_agent_playbook.config.files import CONFIG_FILENAME, CONFIG_LOCAL_FILENAME
from coding_agent_playbook.generated_output.file_identity import FileSet
from coding_agent_playbook.generated_output.gitignore import (
    GITIGNORE_FILENAME,
    LOCKFILE_NAME,
    apply_managed_block,
    block_is_current,
    entry_matches,
    ignore_entries,
    relative_posix_paths,
    remove_managed_block,
)
from coding_agent_playbook.generated_output.output_io import (
    is_character_device,
    refuse_special_file,
)
from coding_agent_playbook.generated_output.symlinks import link_leaving, real_path
from coding_agent_playbook.sync._output_blockers import write_blocker

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping, Sequence
    from typing import TextIO

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.sync.git_client import GitClient

#: ``sync --check`` wording for an orphan (specs/prK-lifecycle-hooks.md §P P2).
ORPHAN_HINT = "    Orphaned generated file; run 'playbook sync' to remove."

# Filenames that are state-source-managed and must be excluded from the
# drift diff (otherwise the lockfile written by sync would itself look
# like drift): the two config files and the lockfile.
_STATE_FILES_TO_SKIP: tuple[str, ...] = (
    CONFIG_FILENAME,
    CONFIG_LOCAL_FILENAME,
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
    refuse_special_file(target, reading=True)  # reading a FIFO blocks: name it instead (§12.2)
    if commit:
        changed = remove_managed_block(target)
        return f"Removed the managed block from {GITIGNORE_FILENAME}" if changed else None
    changed = apply_managed_block(target, ignore_entries(written, repo_root))
    return f"Updated the managed block in {GITIGNORE_FILENAME}" if changed else None


def file_drift(
    written: Sequence[Path],
    scratch: Path,
    repo_root: Path,
    *,
    shared: Collection[str] = (),
    skill_roots: Collection[str] = (),
) -> list[str]:
    """``--check``: drift lines for every scratch-rendered file missing/different on disk.

    ``_STATE_FILES_TO_SKIP`` (config + lockfile) are StateSource-owned, never
    adapter output, so they are excluded from the diff. A file missing because
    something on the real tree is in its way names it instead of suggesting a
    sync that cannot fix it: the blocker write mode stops on (§12.2), or, inside
    ``<root>/<id>/`` of a native skills root (``skill_roots``, repo-relative),
    what the skill writer skips there (§10.8). ``shared`` (repo-relative, the
    adapters' co-owned files) are written by atomic replace, so a dangling link
    at one of them is no blocker.

    Example::

        >>> file_drift([], Path("/scratch"), Path("."))
        []
    """
    drift: list[str] = []
    for path in written:
        rel = path.resolve().relative_to(scratch.resolve())
        if rel.name in _STATE_FILES_TO_SKIP:
            continue
        hint = _drift_hint(path, rel, repo_root, shared=shared, skill_roots=skill_roots)
        if hint is not None:
            drift.append(f"  {rel.as_posix()}\n{hint}")
    return drift


def _drift_hint(
    rendered: Path,
    rel: Path,
    repo_root: Path,
    *,
    shared: Collection[str],
    skill_roots: Collection[str],
) -> str | None:
    """How ``repo_root / rel`` drifted from ``rendered`` and what fixes it; ``None`` if it did not."""
    actual = repo_root / rel
    if _delivered_into_a_device(rel, repo_root, skill_roots):
        return None
    if not actual.is_file():
        return _missing_hint(rel, repo_root, shared=shared, skill_roots=skill_roots)
    differs = actual.read_bytes() != rendered.read_bytes()
    if not differs and not _lost_exec_bit(rendered, actual):
        return None
    what = "Generated content differs" if differs else "Mode differs"
    leaving = _link_leaving_skill_dir(rel, repo_root, skill_roots)
    if leaving is not None:  # sync never writes through it: "regenerate" would never clear this
        return _link_leaving_hint(leaving, repo_root, what=what)
    return _DIFFERS_HINT if differs else _MODE_HINT


def _lost_exec_bit(rendered: Path, actual: Path) -> bool:
    """POSIX only: the render is executable (a copied script) but the on-disk file is not.

    Only this direction: a text file the user made executable is never rewritten
    with a new mode by ``write_text``, so the reverse could never be cleared.
    """
    if os.name != "posix":
        return False
    return bool(rendered.stat().st_mode & 0o111) and not actual.stat().st_mode & 0o111


def shared_outputs(adapters: Mapping[str, Adapter]) -> frozenset[str]:
    """The repo-relative files ``adapters`` co-own with the user (their ``shared_outputs``).

    Example::

        >>> shared_outputs({"claude_code": ClaudeCodeAdapter()})  # doctest: +SKIP
        frozenset({'.claude/settings.json'})
    """
    return frozenset(path for adapter in adapters.values() for path in type(adapter).shared_outputs)


def native_skill_roots(adapters: Mapping[str, Adapter]) -> frozenset[str]:
    """Each declared ``Adapter.native_skills_root`` of ``adapters`` (``.claude/skills``, …).

    Inside ``<root>/<id>/`` of these roots the skill writer settles what is in
    the way itself (§10.8), so :func:`file_drift` explains a missing file its
    way; ``agent_harness``'s ``skills/`` is written plainly and declares none.

    Example::

        >>> native_skill_roots({"claude_code": ClaudeCodeAdapter()})  # doctest: +SKIP
        frozenset({'.claude/skills'})
    """
    roots = (type(adapter).native_skills_root for adapter in adapters.values())
    return frozenset(root for root in roots if root is not None)


def without_shared(paths: Iterable[Path], repo_root: Path, shared: Iterable[str]) -> list[Path]:
    """``paths`` minus every shared output (compared resolved, so a symlinked dir still matches).

    Example::

        >>> without_shared([Path("/r/AGENTS.md")], Path("/r"), {".claude/settings.json"})
        [PosixPath('/r/AGENTS.md')]
    """
    excluded = {real_path(repo_root / rel) for rel in shared}
    return [path for path in paths if real_path(path) not in excluded]


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


_CREATE_HINT = "    Missing on disk; run 'playbook sync' to create."
_DIFFERS_HINT = (
    "    Generated content differs from on-disk content.\n    Run 'playbook sync' to regenerate."
)
_MODE_HINT = "    Mode differs: generated as executable.\n    Run 'playbook sync' to restore it."


def _missing_hint(
    rel: Path, repo_root: Path, *, shared: Collection[str], skill_roots: Collection[str]
) -> str:
    """Why ``repo_root / rel`` is missing and what fixes it, the way write mode would tell it."""
    actual_path = repo_root / rel
    skill_dir = _native_skill_dir(rel, repo_root, skill_roots)
    stop = write_blocker(actual_path, repo_root, replaces_path=rel.as_posix() in shared)
    if stop is not None and not _strictly_inside(stop.path, skill_dir):
        # write mode stops on it and never removes it (§12.2)
        return f"    Missing on disk: {stop.problem}.\n    {stop.remedy}, then run 'playbook sync'."
    if skill_dir is None:
        return _CREATE_HINT
    return _skill_dir_hint(actual_path, skill_dir, repo_root)


def _native_skill_dir(rel: Path, repo_root: Path, skill_roots: Collection[str]) -> Path | None:
    """``repo_root / <root>/<id>`` when ``rel`` lies strictly inside one, for a native ``<root>``."""
    for root in skill_roots:
        depth = len(PurePosixPath(root).parts)
        if rel.parts[:depth] == PurePosixPath(root).parts and len(rel.parts) > depth + 1:
            return repo_root.joinpath(*rel.parts[: depth + 1])
    return None


def _delivered_into_a_device(rel: Path, repo_root: Path, skill_roots: Collection[str]) -> bool:
    """Whether write mode writes ``rel`` into a character device (``AGENTS.md -> /dev/null``).

    Then there is nothing to compare. Not inside a native skill dir: the skill
    writer replaces a link at its destination with the real file (§10.8).
    """
    in_skill_dir = _native_skill_dir(rel, repo_root, skill_roots) is not None
    return not in_skill_dir and is_character_device(repo_root / rel)


def _link_leaving_skill_dir(
    rel: Path, repo_root: Path, skill_roots: Collection[str]
) -> Path | None:
    """The link leading out of the native skill dir ``rel`` lies in, if one is on its way."""
    skill_dir = _native_skill_dir(rel, repo_root, skill_roots)
    return None if skill_dir is None else link_leaving((repo_root / rel).parent, skill_dir)


def _link_leaving_hint(link: Path, repo_root: Path, *, what: str) -> str:
    """``<what>: <link> is a symbolic link leading outside the skill directory, …`` and the fix."""
    return (
        f"    {what}: {link.relative_to(repo_root).as_posix()} is a symbolic link leading "
        "outside the skill directory, and sync never writes through one.\n"
        "    Remove or re-point the link, then run 'playbook sync'."
    )


def _skill_dir_hint(actual_path: Path, skill_dir: Path, repo_root: Path) -> str:
    """Inside a native skill dir: what the skill writer skips ``actual_path`` for (§10.8)."""
    link = link_leaving(actual_path.parent, skill_dir)
    if link is not None:
        return _link_leaving_hint(link, repo_root, what="Missing on disk")
    blocker = swap_blocker(actual_path, skill_dir)
    if blocker is None:
        return _CREATE_HINT
    shown = blocker.relative_to(repo_root).as_posix()
    return (
        f"    Missing on disk: {shown} is in the way. 'playbook sync' replaces it only\n"
        "    when it holds nothing but unchanged files it wrote; otherwise move those\n"
        "    files, then re-run 'playbook sync'."
    )


def _strictly_inside(path: Path, directory: Path | None) -> bool:
    """Whether ``path`` lies below ``directory`` (both as spelled, made absolute)."""
    if directory is None:
        return False
    inner, outer = Path(os.path.abspath(path)), Path(os.path.abspath(directory))
    return inner != outer and inner.is_relative_to(outer)


def gitignore_drift(repo_root: Path, entries: Sequence[str]) -> list[str]:
    """``--check``: drift lines for the managed block (empty when current).

    A FIFO, socket or block device at ``.gitignore`` raises ``NotRegularFileError``
    (reading a FIFO would block), which ``playbook sync`` reports as a blocker.

    Example::

        >>> gitignore_drift(Path("."), ["/AGENTS.md"])  # doctest: +SKIP
        []
    """
    refuse_special_file(repo_root / GITIGNORE_FILENAME, reading=True)
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
