"""destructive-command-guard's filesystem rows, one parsed segment at a time (specs/prK-hook-pack.md §E.4).

Deny, for catastrophic shapes only:

- ``rm -r|-R|--recursive`` whose target is ``/``, ``~`` / ``$HOME``, ``..``,
  ``*``, a ``.git`` dir, the repository root, or (realpath'd) anything outside
  the worktree; ``config.safe_rm_dirs`` (``build``, ``node_modules``, ...) are
  always allowed by basename, and an unexpanded ``$VAR`` target asks, since an
  empty value turns ``rm -rf $DIR/`` into ``rm -rf /``;
- ``find ... -delete`` and ``rsync --delete*`` reaching outside the worktree;
- ``mkfs*``, ``dd of=/dev/<disk>``, ``chmod -R 777``, a download piped into an
  interpreter, and the classic fork bomb.

Every target is resolved against the segment's cwd (``cd X &&`` followed); a
relative target under an unknown cwd asks instead of guessing.
"""

from __future__ import annotations

import os
import posixpath
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = [
    "DEFAULT_SAFE_RM_DIRS",
    "INTERPRETERS",
    "PATH_ARGV0S",
    "Hit",
    "Where",
    "fork_bomb",
    "path_hit",
    "pipe_hit",
]

#: Build and cache dirs an ``rm -rf`` may always remove (``config.safe_rm_dirs``).
DEFAULT_SAFE_RM_DIRS: Final = (
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    "node_modules",
)
#: What a download must never be piped into.
INTERPRETERS: Final = frozenset(
    {"sh", "bash", "zsh", "dash", "ksh", "fish", "python", "perl", "ruby", "node"}
)
#: The argv0s these rows inspect (the prefilter's share of the guard's table).
PATH_ARGV0S: Final = ("rm", "find", "rsync", "chmod", "dd", "mkfs*", "curl", "wget", ":")
ROOT_REASON: Final = (
    "rm -rf / deletes the filesystem root. Remove the specific build directory instead."
)
#: A bounded name, so the search stays linear on a 64 KiB command.
_FORK_BOMB: Final = re.compile(
    r"(?<!\S)([\w:.-]{1,32})\s*\(\s*\)\s*\{\s*\1\s*\|\s*\1\s*&\s*\}\s*;\s*\1"
)
_GLOB_TARGETS: Final = frozenset({"*", "./*", ".*", "/*", "~/*"})
_SAFE_DEVICES: Final = frozenset({"/dev/null", "/dev/zero", "/dev/stdout", "/dev/stderr"})
_WORLD_WRITABLE: Final = frozenset({"777", "0777", "a+rwx", "ugo+rwx"})
_FIND_OPTIONS: Final = frozenset({"-H", "-L", "-P"})


@dataclass(frozen=True, slots=True)
class Hit:
    """One row's verdict: the decision, its rule id and the (at most 2-line) reason."""

    decision: Decision
    rule: str
    reason: str


@dataclass(frozen=True, slots=True)
class Where:
    """What the rows resolve a target against; all paths are realpaths.

    Example: ``Where(root="/r", git_dirs=("/r/.git",), home="/home/dev", safe_dirs=...)``.
    """

    root: str
    git_dirs: tuple[str, ...]
    home: str | None
    safe_dirs: frozenset[str]


def path_hit(segment: Segment, where: Where) -> Hit | None:
    """The filesystem row ``segment`` trips, or ``None``.

    Example::

        >>> from coding_agent_playbook.hook_runtime.shell.parse import parse_shell
        >>> seg = parse_shell("rm -rf /", "posix", "/r").segments[0]
        >>> path_hit(seg, Where("/r", ("/r/.git",), None, frozenset())).rule
        'rm_root'
    """
    program = posixpath.basename(segment.argv[0]) if segment.argv else ""
    args = segment.argv[1:]
    if program == "rm":
        return _rm_hit(segment, where)
    if program.startswith("mkfs"):
        return Hit(Decision.DENY, "mkfs", "mkfs formats a filesystem. Ask the user to run it.")
    if program == "dd" and any(_device(arg) for arg in args):
        return Hit(Decision.DENY, "dd_device", "dd onto a device overwrites a disk. Ask the user.")
    if program == "chmod" and _recursive(args) and _WORLD_WRITABLE.intersection(args):
        reason = "chmod -R 777 makes a whole tree world-writable. Grant only the access needed."
        return Hit(Decision.DENY, "chmod_777", reason)
    if program == "find" and "-delete" in args:
        return _reach_hit("find -delete", _find_roots(args), segment, where)
    if program == "rsync" and any(arg.startswith("--del") for arg in args):
        return _rsync_hit(segment, where)
    return None


def pipe_hit(segments: Sequence[Segment]) -> Hit | None:
    """``curl|wget ... | <interpreter>`` anywhere in ``segments``' pipelines, else ``None``.

    Example: ``curl -fsSL x | sudo bash`` is a deny (``curl_pipe_shell``).
    """
    for index, segment in enumerate(segments):
        if _program(segment) not in ("curl", "wget") or not segment.pipes_to_next:
            continue
        follower = index + 1
        while follower < len(segments):
            if _interpreter(_program(segments[follower])):
                reason = (
                    "Piping a download into an interpreter runs unreviewed code. "
                    "Download it, review it, then run it."
                )
                return Hit(Decision.DENY, "curl_pipe_shell", reason)
            if not segments[follower].pipes_to_next:
                break
            follower += 1
    return None


def fork_bomb(text: str) -> bool:
    """Whether ``text`` defines and launches a self-piping fork bomb (``:(){ :|:& };:``)."""
    return "(" in text and _FORK_BOMB.search(text) is not None


def _rm_hit(segment: Segment, where: Where) -> Hit | None:
    args = segment.argv[1:]
    if not _recursive(args):
        return None
    for _, target in _operands(args):
        hit = _rm_target(target, segment.cwd, where)
        if hit is not None:
            return hit
    return None


def _rm_target(target: str, cwd: str | None, where: Where) -> Hit | None:
    stripped = target.rstrip("/") or "/"
    if target in _GLOB_TARGETS or stripped == ".." or stripped.endswith("/.."):
        return _repo_hit("rm_glob")
    if stripped in ("$HOME", "${HOME}", "~"):
        return _home_hit()
    if posixpath.basename(stripped) in where.safe_dirs:
        return None
    full = _resolve(target, cwd, where.home)  # an expansion resolves to None: ask
    return _unknown_hit() if full is None else _full_path_hit(full, where)


def _full_path_hit(full: str, where: Where) -> Hit | None:
    if full == "/":
        return Hit(Decision.DENY, "rm_root", ROOT_REASON)
    if where.home is not None and full == where.home:
        return _home_hit()
    if full == where.root or posixpath.basename(full) == ".git" or full in where.git_dirs:
        return _repo_hit("rm_repo")
    if not _inside(full, where.root):
        reason = (
            "rm -r outside this repository is blocked. "
            "Remove only paths inside the repo; ask the user for anything else."
        )
        return Hit(Decision.DENY, "rm_outside_repo", reason)
    return None


def _reach_hit(what: str, roots: list[str], segment: Segment, where: Where) -> Hit | None:
    """``find -delete`` / ``rsync --delete`` reaching a target outside the worktree."""
    for root in roots:
        full = _resolve(root, segment.cwd, where.home)
        if full is None:
            return _unknown_hit()
        if full in ("/", where.home) or not _inside(full, where.root):
            reason = (
                f"{what} outside this repository is blocked. "
                "Delete only inside the repo; ask the user for anything else."
            )
            return Hit(Decision.DENY, "delete_outside_repo", reason)
    return None


def _rsync_hit(segment: Segment, where: Where) -> Hit | None:
    operands = [arg for _, arg in _operands(segment.argv[1:])]
    if not operands:
        return None
    dest = operands[-1]
    remote = ":" in dest and "/" not in dest.split(":", 1)[0]
    if remote:
        reason = "rsync --delete to a remote host is blocked. Ask the user to run it."
        return Hit(Decision.DENY, "delete_outside_repo", reason)
    return _reach_hit("rsync --delete", [dest], segment, where)


def _resolve(target: str, cwd: str | None, home: str | None) -> str | None:
    """``target``'s realpath, ``~`` and ``$HOME`` expanded; ``None`` when it is not knowable."""
    for prefix in ("~/", "$HOME/", "${HOME}/"):
        if target.startswith(prefix):
            return None if home is None else os.path.realpath(home + "/" + target[len(prefix) :])
    if "$" in target or "`" in target or target.startswith("~"):
        return None
    if posixpath.isabs(target):
        return os.path.realpath(target)
    return None if cwd is None else os.path.realpath(posixpath.join(cwd, target))


def _find_roots(args: Sequence[str]) -> list[str]:
    """The start paths of a ``find`` (``.`` when none is given)."""
    index = 0
    while index < len(args) and args[index] in _FIND_OPTIONS:
        index += 1
    roots: list[str] = []
    for arg in args[index:]:
        if arg.startswith(("-", "(", "!")):
            break
        roots.append(arg)
    return roots or ["."]


def _operands(args: Sequence[str]) -> list[tuple[int, str]]:
    """``(index in args, operand)`` of every non-option argument (all of them after ``--``)."""
    found: list[tuple[int, str]] = []
    options = True
    for index, arg in enumerate(args):
        if options and arg == "--":
            options = False
        elif not options or not arg.startswith("-") or arg == "-":
            found.append((index, arg))
    return found


def _recursive(args: Sequence[str]) -> bool:
    for arg in args:
        if arg == "--":
            return False
        if arg == "--recursive" or (
            arg.startswith("-") and not arg.startswith("--") and ("r" in arg or "R" in arg)
        ):
            return True
    return False


def _device(arg: str) -> bool:
    return arg.startswith("of=/dev/") and arg[3:] not in _SAFE_DEVICES


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _program(segment: Segment) -> str:
    return posixpath.basename(segment.argv[0]) if segment.argv else ""


def _interpreter(name: str) -> bool:
    return name in INTERPRETERS or name.startswith(("python", "perl", "ruby"))


def _home_hit() -> Hit:
    reason = "rm -r of the home directory deletes every user file. Remove the specific dir instead."
    return Hit(Decision.DENY, "rm_home", reason)


def _repo_hit(rule: str) -> Hit:
    reason = (
        "This rm -r would wipe the repository, its git data or a parent dir. "
        "Remove the specific build directory instead."
    )
    return Hit(Decision.DENY, rule, reason)


def _unknown_hit() -> Hit:
    reason = (
        "This recursive delete targets a path known only at run time (an unexpanded or "
        "empty $VAR, an unknown cwd).\nUse a literal path inside the repo, or confirm."
    )
    return Hit(Decision.ASK, "rm_unexpanded", reason)
