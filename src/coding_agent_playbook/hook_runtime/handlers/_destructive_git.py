"""destructive-command-guard's git rows, one parsed ``git`` invocation at a time (specs/prK-hook-pack.md §E.4).

Deny: ``push --force|-f|+refspec|--delete`` and ``--force-with-lease`` to a
protected branch (``config.protected_branches``, ``fnmatch`` globs, the target
read from the refspec, else the upstream, else the current branch); ``push
--mirror``; ``update-ref -d`` of a protected ref; ``filter-branch`` on one and
every ``filter-repo`` (it rewrites all refs by default).

Ask: a lossy in-repo command only when ``git status`` shows work it would lose
(``reset --hard``, ``checkout -- <paths>`` / ``checkout -f``, ``restore`` of
the worktree, ``clean -f``; ``clean -x`` always, since ignored files such as
``.env`` are not listed); a non-force push to the default branch; a force push
without lease to any other branch; ``branch -D``; ``worktree remove --force``;
a bare ``stash`` / ``pop`` / ``drop`` / ``clear`` while other worktrees share
the stash stack. A command aimed at another repository (``-C``, ``--git-dir``)
asks whenever it would need this worktree's state to be judged.

:class:`GitFacts` runs each local git query at most once, and only for the
row that needs it, so a ``git log`` costs no subprocess.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.handlers._destructive_paths import Hit
from coding_agent_playbook.hook_runtime.paths import find_repo
from coding_agent_playbook.hook_runtime.shell.git_options import git_args

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from coding_agent_playbook.hook_runtime.event import RepoInfo
    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort
    from coding_agent_playbook.hook_runtime.shell.git_command import GitInvocation
    from coding_agent_playbook.hook_runtime.shell.git_options import GitArgs

__all__ = ["DEFAULT_PROTECTED_BRANCHES", "STASH_RECIPE", "GitFacts", "git_hit"]

DEFAULT_PROTECTED_BRANCHES: Final = ("main", "master", "release/*")
STASH_RECIPE: Final = (
    "The stash stack is shared by every worktree of this repo: use git stash push -u -m <tag>,\n"
    "note its SHA (git stash list --format='%H %gs'), then git stash apply <sha>."
)
_FEATURE_BRANCH: Final = "Push a feature branch; the user merges."
_HEADS: Final = "refs/heads/"
_REMOTES: Final = "refs/remotes/"
#: ``(XY, path)`` status codes of an untracked path.
_UNTRACKED: Final = "??"


class GitFacts:
    """This worktree's git state, each query run once on first need.

    Example::

        >>> GitFacts(git, repo).branch()  # doctest: +SKIP
        'main'
    """

    def __init__(self, git: GitPort, repo: RepoInfo) -> None:
        self.git = git
        self.repo = repo
        self._cache: dict[str, Any] = {}

    def _once(self, key: str, query: Callable[[], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = query()
        return self._cache[key]

    def branch(self) -> str | None:
        """The current branch (``None`` when detached)."""
        found: str | None = self._once("branch", lambda: self.git.symbolic_ref("HEAD"))
        return found

    def default_branch(self) -> str | None:
        """The default branch's name (``origin/main`` -> ``main``), via the one shared resolver."""
        found: str | None = self._once("default", self.git.default_branch)
        return None if found is None else found.removeprefix("origin/")

    def upstream_branch(self) -> str | None:
        """The upstream's branch name on its remote, or ``None`` without one."""
        ref: str | None = self._once("upstream", self.git.upstream)
        if ref is None or not ref.startswith(_REMOTES):
            return None
        return ref[len(_REMOTES) :].split("/", 1)[-1]

    def status(self) -> tuple[tuple[str, str], ...]:
        """``git status --porcelain`` entries."""
        found: tuple[tuple[str, str], ...] = self._once("status", self.git.porcelain_status)
        return found

    def tracked_changes(self) -> bool:
        """Whether a staged or unstaged change to a tracked file exists."""
        return any(xy != _UNTRACKED for xy, _ in self.status())

    def untracked(self) -> bool:
        """Whether an untracked, non-ignored file exists."""
        return any(xy == _UNTRACKED for xy, _ in self.status())


def git_hit(inv: GitInvocation, facts: GitFacts, protected: Iterable[str]) -> Hit | None:
    """The git row ``inv`` trips, or ``None`` (module docstring).

    Example::

        >>> git_hit(parse_git(seg("git push -f origin main")), facts, ["main"]).rule
        ... # doctest: +SKIP
        'force_push_protected'
    """
    sub = inv.subcommand or ""
    row = _ROWS.get(sub)
    if row is None:
        return None
    here = _same_worktree(inv, facts.repo)
    return row(git_args(inv.args, sub), _Scope(facts, tuple(protected), here))


class _Scope:
    """What one row reads: the facts, the protected globs, and whether ``inv`` targets them."""

    def __init__(self, facts: GitFacts, protected: tuple[str, ...], here: bool) -> None:
        self.facts = facts
        self.protected = protected
        self.here = here

    def is_protected(self, branch: str | None) -> bool:
        """Whether ``branch`` matches one of the protected globs."""
        from fnmatch import fnmatchcase

        return branch is not None and any(fnmatchcase(branch, glob) for glob in self.protected)

    def lossy(self, rule: str, command: str, *, untracked: bool = False) -> Hit | None:
        """Ask when ``command`` would lose work here (or when it targets another repo)."""
        facts = self.facts
        losing = not self.here or (facts.untracked() if untracked else facts.tracked_changes())
        if not losing:
            return None
        reason = (
            f"git {command} discards uncommitted work in this worktree.\n"
            "Commit it, or git stash push -u -m <tag> first, then rerun."
        )
        return Hit(Decision.ASK, rule, reason)


def _push(args: GitArgs, scope: _Scope) -> Hit | None:
    if args.has("--mirror"):
        return _protected_hit("push_mirror", "every branch")
    specs = args.positionals[1:]
    lease = any(flag.startswith("--force-with-lease") for flag in args.longs)
    force = args.has("--force", "f") or any(spec.startswith("+") for spec in specs)
    delete = args.has("--delete", "d") or any(spec.startswith(":") for spec in specs)
    every = args.has("--all", "--branches")
    targets = [] if every else [_target(s, scope) for s in specs] or [_default_target(scope)]
    if force or lease or delete:
        return _forced_push(targets, every=every, unleased=force and not lease, scope=scope)
    default = scope.facts.default_branch()
    if default is not None and (every or default in targets):
        reason = f"This pushes straight to the default branch {default}.\n{_FEATURE_BRANCH}"
        return Hit(Decision.ASK, "push_default_branch", reason)
    return None


def _forced_push(
    targets: list[str | None], *, every: bool, unleased: bool, scope: _Scope
) -> Hit | None:
    """A force, lease or delete push: deny on a protected target, else ask unless leased."""
    if every:
        return _protected_hit("force_push_protected", "every branch")
    protected = next((t for t in targets if t is not None and scope.is_protected(t)), None)
    if protected is not None:
        return _protected_hit("force_push_protected", protected)
    if None in targets:
        reason = f"A force push whose target branch cannot be read here.\n{_FEATURE_BRANCH}"
        return Hit(Decision.ASK, "force_push_unknown", reason)
    if unleased:
        reason = (
            "A force push without --force-with-lease can drop commits others pushed.\n"
            "Use --force-with-lease, or confirm."
        )
        return Hit(Decision.ASK, "force_push", reason)
    return None


def _target(spec: str, scope: _Scope) -> str | None:
    """The remote branch a refspec updates (``HEAD`` -> the current branch)."""
    dst = spec.lstrip("+")
    if ":" in dst:
        dst = dst.split(":", 1)[1] or dst.split(":", 1)[0]
    if dst in ("HEAD", "@"):
        return scope.facts.branch() if scope.here else None
    return dst.removeprefix(_HEADS) or None


def _default_target(scope: _Scope) -> str | None:
    if not scope.here:
        return None
    return scope.facts.upstream_branch() or scope.facts.branch()


def _protected_hit(rule: str, branch: str) -> Hit:
    reason = f"This rewrites or deletes the protected branch {branch}.\n{_FEATURE_BRANCH}"
    return Hit(Decision.DENY, rule, reason)


def _reset(args: GitArgs, scope: _Scope) -> Hit | None:
    return scope.lossy("reset_hard_dirty", "reset --hard") if args.has("--hard") else None


def _checkout(args: GitArgs, scope: _Scope) -> Hit | None:
    discards = bool(args.pathspecs) or "." in args.positionals or args.has("--force", "f")
    return scope.lossy("checkout_discard", "checkout") if discards else None


def _restore(args: GitArgs, scope: _Scope) -> Hit | None:
    staged_only = args.has("--staged", "S") and not args.has("--worktree", "W")
    return None if staged_only else scope.lossy("restore_discard", "restore")


def _clean(args: GitArgs, scope: _Scope) -> Hit | None:
    if not args.has("--force", "f") or args.has("--dry-run", "n"):
        return None
    if args.has("x", "X"):
        reason = (
            "git clean -x also deletes ignored files (.env, local data, venvs).\n"
            "Remove the specific paths instead, or confirm."
        )
        return Hit(Decision.ASK, "clean_ignored", reason)
    return scope.lossy("clean_untracked", "clean -f", untracked=True)


def _branch(args: GitArgs, scope: _Scope) -> Hit | None:
    if args.has("D") or (args.has("--delete", "d") and args.has("--force", "f")):
        reason = "git branch -D deletes a branch even when it is unmerged.\nUse -d, or confirm."
        return Hit(Decision.ASK, "branch_force_delete", reason)
    return None


def _worktree(args: GitArgs, scope: _Scope) -> Hit | None:
    if args.positionals[:1] == ("remove",) and args.has("--force", "f"):
        reason = "git worktree remove --force discards that worktree's changes.\nConfirm first."
        return Hit(Decision.ASK, "worktree_remove_force", reason)
    return None


def _stash(args: GitArgs, scope: _Scope) -> Hit | None:
    verb = args.positionals[0] if args.positionals else None
    if verb not in (None, "pop", "drop", "clear") or not scope.facts.repo.sibling_roots:
        return None
    return Hit(Decision.ASK, "stash_shared", STASH_RECIPE)


def _update_ref(args: GitArgs, scope: _Scope) -> Hit | None:
    if not args.has("d") or not args.positionals:
        return None
    ref = args.positionals[0].removeprefix(_HEADS)
    return _protected_hit("update_ref_delete", ref) if scope.is_protected(ref) else None


def _filter_branch(args: GitArgs, scope: _Scope) -> Hit | None:
    refs = [ref.removeprefix(_HEADS) for ref in (*args.positionals, *args.pathspecs)]
    if "--all" in refs or args.has("--all"):
        return _protected_hit("rewrite_history", "every branch")
    named = next((ref for ref in refs if scope.is_protected(ref)), None)
    if named is None and not refs and scope.is_protected(scope.facts.branch()):
        named = scope.facts.branch()
    return None if named is None else _protected_hit("rewrite_history", named)


def _filter_repo(args: GitArgs, scope: _Scope) -> Hit | None:
    return _protected_hit("rewrite_history", "every branch")


def _same_worktree(inv: GitInvocation, repo: RepoInfo) -> bool:
    """Whether ``inv`` runs in this worktree (an unknown cwd or ``--git-dir`` is not)."""
    if inv.cwd is None or inv.git_dir is not None or inv.work_tree is not None:
        return False
    found = find_repo(inv.cwd)
    return found is not None and os.path.realpath(found.worktree_root) == os.path.realpath(
        repo.worktree_root
    )


_ROWS: Final[dict[str, Callable[[GitArgs, _Scope], Hit | None]]] = {
    "push": _push,
    "reset": _reset,
    "checkout": _checkout,
    "restore": _restore,
    "clean": _clean,
    "branch": _branch,
    "worktree": _worktree,
    "stash": _stash,
    "update-ref": _update_ref,
    "filter-branch": _filter_branch,
    "filter-repo": _filter_repo,
}
