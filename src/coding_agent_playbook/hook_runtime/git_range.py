"""``SafeGit``'s queries over revisions rather than the working tree (specs/prK-hook-pack.md §E.2, §F.5).

The off-workstation twins (``playbook gate-scan``, ``playbook ci``) diff a
commit range, and E.4 and F.1 later need the same default branch, so the one
resolver lives here: ``refs/remotes/origin/HEAD``, then ``main``, then
``master`` (remote-tracking first, since CI checkouts have no local branch).

:class:`RangeQueries` is a mixin of ``SafeGit``, split out of ``git.py`` for
§D.1's 300-line module rule; it calls only ``run`` / ``bare_run``, so every
query keeps ``SafeGit``'s hardening, and none needs a state directory (CI has
none). Ref-only queries (``symbolic-ref``, ``for-each-ref``, ``merge-base``)
read no worktree content and skip filter discovery, like ``symbolic_ref``.

A revision is refused before git sees it when it could be read as an option
(``--output=...``) or would break the ``cat-file --batch`` line protocol.

The Stop stages add three working-tree forms: ``diff_worktree`` (the
gate-integrity scan's added and removed lines), ``archive_to`` (the lint
baseline's ``git archive`` export, extracted with ``tarfile``'s ``data``
filter so no member lands outside the export or keeps a special mode) and
``grep_word`` (tests-nudge's "is this name used by any test" probe).
``rev_commit`` resolves one revision for subagent-stop-verify's report.
secret-content-guard's push scan (§E.4) adds ``upstream`` and
``unpushed_lines``: the commits a ``git push`` would publish, as ``log -p``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol

from coding_agent_playbook.hook_runtime._git_parse import (
    DiffLines,
    parse_batch_blob,
    parse_diff_lines,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from coding_agent_playbook.hook_runtime.proc import ProcResult

__all__ = [
    "DEFAULT_BRANCH_REFS",
    "ORIGIN_HEAD",
    "PATCH_FLAGS",
    "RangePort",
    "RangeQueries",
    "pick_default_branch",
]

ORIGIN_HEAD: Final = "refs/remotes/origin/HEAD"
#: The default-branch candidates after ``origin/HEAD``, most preferred first.
DEFAULT_BRANCH_REFS: Final = (
    "refs/remotes/origin/main",
    "refs/heads/main",
    "refs/remotes/origin/master",
    "refs/heads/master",
)
_SHORT_PREFIXES: Final = ("refs/remotes/", "refs/heads/")
#: The patch form every parsed diff uses; explicit prefixes defeat diff.noprefix/mnemonicPrefix.
PATCH_FLAGS: Final = (
    "-U0",
    "--no-color",
    "-M",
    "--no-relative",
    "--src-prefix=a/",
    "--dst-prefix=b/",
)
#: Characters that would split a revision into two arguments or two batch lines.
_REV_BREAKERS: Final = frozenset(" \t\n\r\x00:")


class RangePort(Protocol):
    """The revision queries of ``GitPort``; ``FakeGit`` scripts them."""

    def default_branch(self) -> str | None: ...

    def merge_base(self, left: str, right: str) -> str | None: ...

    def diff_range(self, base: str, head: str) -> DiffLines: ...

    def show(self, rev: str, repo_rel: str) -> bytes | None: ...

    def diff_worktree(self, base: str) -> DiffLines: ...

    def archive_to(self, rev: str, dest: str, *, skip: Callable[[str], bool]) -> int: ...

    def grep_word(self, word: str, roots: Sequence[str]) -> bool: ...

    def rev_commit(self, rev: str) -> str | None: ...

    def upstream(self) -> str | None: ...

    def unpushed_lines(self, upstream: str | None) -> DiffLines: ...


class _Runner(Protocol):
    """The part of ``SafeGit`` the mixin calls (the mixin's self-type)."""

    def run(
        self,
        args: Sequence[str],
        *,
        input: bytes | None = None,
        index_file: str | None = None,
        ok_codes: tuple[int, ...] = (0,),
    ) -> ProcResult: ...

    def bare_run(
        self,
        args: Sequence[str],
        *,
        input: bytes | None = None,
        index_file: str | None = None,
        ok_codes: tuple[int, ...] = (0,),
    ) -> ProcResult: ...


class RangeQueries:
    """``SafeGit``'s :class:`RangePort` implementation (a mixin over ``run`` / ``bare_run``).

    Example::

        >>> git.default_branch(), git.merge_base("origin/main", "HEAD")  # doctest: +SKIP
        ('origin/main', '9f2c...')
    """

    def default_branch(self: _Runner) -> str | None:
        """``origin/HEAD``'s target, else ``main``, else ``master``; ``None`` when none exists."""
        head = self.bare_run(["symbolic-ref", "--quiet", "--short", ORIGIN_HEAD], ok_codes=(0, 1))
        target = _decoded(head.stdout)
        if head.ok and target:
            return target
        listed = self.bare_run(["for-each-ref", "--format=%(refname)", *DEFAULT_BRANCH_REFS])
        return pick_default_branch(_decoded(listed.stdout).split())

    def merge_base(self: _Runner, left: str, right: str) -> str | None:
        """The best common ancestor of two revisions, ``None`` when they share no history."""
        argv = ["merge-base", checked_rev(left), checked_rev(right)]
        result = self.bare_run(argv, ok_codes=(0, 1))
        sha = _decoded(result.stdout)
        return sha if result.ok and sha else None

    def diff_range(self: _Runner, base: str, head: str) -> DiffLines:
        """The ``-U0`` patch from ``base`` to ``head``, parsed (both are revisions)."""
        result = self.run(["diff", checked_rev(base), checked_rev(head), *PATCH_FLAGS])
        return parse_diff_lines(result.stdout)

    def show(self: _Runner, rev: str, repo_rel: str) -> bytes | None:
        """The bytes of ``repo_rel`` at ``rev``, or ``None`` when absent there."""
        if not repo_rel or "\n" in repo_rel or "\x00" in repo_rel:
            return None
        spec = f"{checked_rev(rev)}:{repo_rel}\n".encode()
        return parse_batch_blob(self.run(["cat-file", "--batch"], input=spec).stdout)

    def diff_worktree(self: _Runner, base: str) -> DiffLines:
        """The ``-U0`` patch from revision ``base`` to the working tree, parsed."""
        return parse_diff_lines(self.run(["diff", checked_rev(base), *PATCH_FLAGS]).stdout)

    def archive_to(self: _Runner, rev: str, dest: str, *, skip: Callable[[str], bool]) -> int:
        """Export ``rev``'s tree into the directory ``dest``; returns the files written.

        A member whose repo path ``skip`` accepts (a secret glob) is never
        extracted. Filters are neutralized like every hardened call, so a
        ``smudge`` driver never runs during the export.
        """
        import io
        import tarfile

        data = self.run(["archive", "--format=tar", checked_rev(rev)]).stdout
        written = 0
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            for member in archive:
                if member.isdir() or skip(member.name):
                    continue
                try:
                    archive.extract(member, dest, filter="data")
                except tarfile.FilterError:  # e.g. a committed symlink leaving the export
                    continue
                written += 1
        return written

    def grep_word(self: _Runner, word: str, roots: Sequence[str]) -> bool:
        """Whether ``word`` occurs as a whole word in a tracked or untracked text file under ``roots``.

        A fixed string, never a regex (``-F``); ignored files and binaries are skipped.
        """
        if not word or "\n" in word or not roots:
            return False
        pathspecs = [_literal(root) for root in roots]
        argv = ["grep", "--untracked", "-I", "-q", "-w", "-F", "-e", word, "--", *pathspecs]
        return self.run(argv, ok_codes=(0, 1)).ok

    def rev_commit(self: _Runner, rev: str) -> str | None:
        """The commit ``rev`` names, ``None`` when it names none (no worktree read)."""
        argv = ["rev-parse", "--verify", "--quiet", f"{checked_rev(rev)}^{{commit}}"]
        result = self.bare_run(argv, ok_codes=(0, 1))
        sha = _decoded(result.stdout)
        return sha if result.ok and sha else None

    def upstream(self: _Runner) -> str | None:
        """The current branch's upstream ref (``refs/remotes/origin/x``); ``None`` without one.

        git exits 128 for "no upstream configured" even with ``--quiet``.
        """
        argv = ["rev-parse", "--verify", "--quiet", "--symbolic-full-name", "@{u}"]
        result = self.bare_run(argv, ok_codes=(0, 1, 128))
        ref = _decoded(result.stdout)
        return ref if result.ok and ref else None

    def unpushed_lines(self: _Runner, upstream: str | None) -> DiffLines:
        """The ``-U0`` patches of the commits a push publishes, parsed.

        ``<upstream>..HEAD``; without an upstream, ``HEAD --not --remotes``, so a
        new branch's first push is scanned too (every commit no remote has).
        """
        revs = [f"{checked_rev(upstream)}..HEAD"] if upstream else ["HEAD", "--not", "--remotes"]
        result = self.run(["log", "-p", "--format=", *PATCH_FLAGS, *revs])
        return parse_diff_lines(result.stdout)


def pick_default_branch(refs: Iterable[str]) -> str | None:
    """The preferred existing candidate of :data:`DEFAULT_BRANCH_REFS`, short, or ``None``.

    Example::

        >>> pick_default_branch(["refs/heads/master", "refs/remotes/origin/main"])
        'origin/main'
    """
    present = set(refs)
    found = next((ref for ref in DEFAULT_BRANCH_REFS if ref in present), None)
    if found is None:
        return None
    prefix = next(p for p in _SHORT_PREFIXES if found.startswith(p))
    return found[len(prefix) :]


def checked_rev(rev: str) -> str:
    """``rev`` unchanged, or ``GitError`` when git could read it as an option or two words.

    Example::

        >>> checked_rev("origin/main~2")
        'origin/main~2'
    """
    if rev and not rev.startswith("-") and not _REV_BREAKERS.intersection(rev):
        return rev
    from coding_agent_playbook.hook_runtime.git import GitError  # git.py imports this module

    raise GitError(
        f"refusing revision {rev!r}: expected a branch, tag, sha or rev expression "
        "that does not start with '-' and has no whitespace or ':'"
    )


def _literal(root: str) -> str:
    """``root`` as a literal pathspec (no glob or magic); the repo root is ``.``."""
    return f":(literal){root.strip('/') or '.'}"


def _decoded(output: bytes) -> str:
    return output.decode("utf-8", errors="replace").strip()
