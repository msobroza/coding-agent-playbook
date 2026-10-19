"""``playbook check-commit-trailers`` — the trailer rows as a commit-msg and CI twin (specs/prK-hook-pack.md §E.4).

git-commit-push-policy-guard judges the agent's commits in session; this twin
judges every commit, the human's and the editor-composed ones included, with
the same ``security.commit_trailers.commit_msg_violations`` (``CP4xx`` rows
only: subject form is commitizen's, §F.4):

- ``check-commit-trailers <msgfile>``: the pre-commit ``commit-msg`` stage
  (``coding-agent-playbook-commit-trailers``) passes the message file;
- ``check-commit-trailers --range A..B``: every commit of a range (``playbook
  ci`` runs ``<merge base>..HEAD``), each line prefixed by its short sha.

The rows come from ``policy`` (the guard's merged config, whatever
``[hooks]`` says). Exit 0 when nothing breaks a row (always, with no rows),
1 on a violation, 2 when the message, the range or the config cannot be read.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands.twins._runner import TWIN_ERRORS, TwinOutcome, run_twin
from coding_agent_playbook.commands.twins.policy import commit_trailer_policy
from coding_agent_playbook.hook_runtime.shell.git_command import MESSAGE_MAX_BYTES
from coding_agent_playbook.security.commit_trailers import commit_msg_violations

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.hook_runtime.git import SafeGit
    from coding_agent_playbook.security.commit_trailers import GitPolicy

__all__ = ["range_messages", "run", "violation_lines"]

_SHORT_SHA: Final = 12


def run(args: argparse.Namespace, *, git: SafeGit | None = None) -> int:
    """Check the message file or every commit of ``--range``; returns 0, 1 or 2.

    Example::

        >>> run(build_parser().parse_args(["check-commit-trailers", ".git/COMMIT_EDITMSG"]))
        ... # doctest: +SKIP
        0
    """
    return run_twin(
        args.repo_root, lambda root: _outcome(args, root, git), errors=(*TWIN_ERRORS, OSError)
    )


def _outcome(args: argparse.Namespace, repo_root: Path, git: SafeGit | None) -> TwinOutcome:
    if (args.msgfile is None) == (args.rev_range is None):
        raise ValueError("pass a message file or --range A..B, not both")
    policy = commit_trailer_policy(repo_root)
    if not policy.has_rows:
        return TwinOutcome(0, "")
    lines = violation_lines(_messages(args, repo_root, git), policy)
    return TwinOutcome(1 if lines else 0, "\n".join(lines))


def violation_lines(messages: list[tuple[str, str]], policy: GitPolicy) -> list[str]:
    """``<label>: CP4xx ...`` for every row each ``(label, message)`` breaks.

    Example::

        >>> violation_lines([("a1b2", "fix: x\\n\\nCo-Authored-By: B <b@x>")],
        ...                 GitPolicy(forbid_trailers=("Co-Authored-By",)))
        ['a1b2: CP401 forbidden trailer Co-Authored-By']
    """
    return [
        f"{label}: {line}"
        for label, text in messages
        for line in commit_msg_violations(text, policy)
    ]


def range_messages(git: SafeGit, text: str) -> list[tuple[str, str]]:
    """``(short sha, message)`` of every commit in ``A..B`` / ``A...B``, oldest first.

    Example::

        >>> range_messages(git, "origin/main..HEAD")  # doctest: +SKIP
        [('9f2c1a7b3d4e', 'feat: x\\n\\nRefs: AB-1\\n')]
    """
    from coding_agent_playbook.commands.twins._git_scope import resolve_range
    from coding_agent_playbook.hook_runtime.git_range import checked_rev

    span = resolve_range(git, text)
    revs = f"{checked_rev(span.base)}..{checked_rev(span.head)}"
    output = git.run(["log", "--reverse", "-z", "--format=%H%n%B", revs]).stdout
    records = output.decode("utf-8", errors="replace").split("\x00")
    found: list[tuple[str, str]] = []
    for record in records:
        sha, _, message = record.strip("\n").partition("\n")
        if sha:
            found.append((sha[:_SHORT_SHA], message))
    return found


def _messages(
    args: argparse.Namespace, repo_root: Path, git: SafeGit | None
) -> list[tuple[str, str]]:
    if args.rev_range is not None:
        from coding_agent_playbook.commands.twins._git_scope import open_git

        return range_messages(git if git is not None else open_git(repo_root), args.rev_range)
    path = Path(args.msgfile)
    data = path.read_bytes()[: MESSAGE_MAX_BYTES + 1]
    if len(data) > MESSAGE_MAX_BYTES:
        raise ValueError(f"{path}: larger than {MESSAGE_MAX_BYTES} bytes; not a commit message")
    return [(str(path), data.decode("utf-8", errors="replace"))]
