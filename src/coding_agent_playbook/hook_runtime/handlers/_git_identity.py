"""git-commit-push-policy-guard's identity and signing rows, pure (specs/prK-hook-pack.md §E.4).

The agent must not change who a commit says wrote it, nor how it is signed.
Each row reads one parsed segment; none runs git:

- a ``GIT_AUTHOR_*`` / ``GIT_COMMITTER_*`` prefix or ``export``;
- ``user.name`` / ``user.email`` / signing config injected by ``git -c``,
  ``--config-env``, ``GIT_CONFIG_COUNT`` / ``KEY_n`` / ``VALUE_n`` or
  ``GIT_CONFIG_PARAMETERS``;
- any write to that config through ``git config`` (set, ``--unset``,
  ``--add``, ``--replace-all``, any scope); reads and ``--get`` pass;
- ``--author`` on a commit, and an agent-added ``-S`` / ``--gpg-sign`` /
  ``--no-gpg-sign`` (``-s`` / ``-u`` / ``--no-sign`` on ``tag``): the user's own
  ``commit.gpgSign`` still applies.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._git_options import config_words, git_args

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.hook_runtime.gitargv import GitInvocation
    from coding_agent_playbook.hook_runtime.shell import Segment

__all__ = ["COMMIT_WRITERS", "IDENTITY_KEYS", "IDENTITY_REASON", "identity_rule"]

#: The config keys that set who wrote a commit, or how it is signed (compared lowercased).
IDENTITY_KEYS: Final = frozenset(
    {
        "user.name",
        "user.email",
        "author.name",
        "author.email",
        "committer.name",
        "committer.email",
        "user.signingkey",
        "commit.gpgsign",
        "tag.gpgsign",
        "gpg.format",
        "gpg.program",
    }
)
#: The subcommands that write commits (or tags) and so read identity and signing.
COMMIT_WRITERS: Final = frozenset(
    {"commit", "merge", "rebase", "commit-tree", "cherry-pick", "revert", "am", "tag", "pull"}
)
IDENTITY_REASON: Final = (
    "Blocked: the agent must not change git identity, authorship or signing.\n"
    "Commit as the configured user; ask the user if git config needs to change."
)
_IDENTITY_ENV: Final = ("GIT_AUTHOR_", "GIT_COMMITTER_")
_CONFIG_KEY_ENV: Final = re.compile(r"GIT_CONFIG_KEY_\d+")
_CONFIG_WRITE_VERBS: Final = frozenset(
    {"set", "unset", "--unset", "--unset-all", "--add", "--replace-all", "--rename-section"}
)
_SIGNING_FLAGS: Final = ("S", "--gpg-sign", "--no-gpg-sign")
_TAG_SIGNING_FLAGS: Final = ("s", "u", "--sign", "--local-user", "--no-sign")


def identity_rule(segment: Segment, git: GitInvocation | None) -> str | None:
    """The identity or signing rule ``segment`` breaks, or ``None``.

    Example::

        >>> from coding_agent_playbook.hook_runtime.gitargv import parse_git
        >>> from coding_agent_playbook.hook_runtime.shell import parse_shell
        >>> seg = parse_shell("git commit --author=x -m m", "posix", "/r").segments[0]
        >>> identity_rule(seg, parse_git(seg))
        'author'
    """
    if _env_sets_identity(segment.env):
        return "identity_env"
    program = posixpath.basename(segment.argv[0]) if segment.argv else ""
    if program == "export":
        pairs = [arg.partition("=") for arg in segment.argv[1:] if "=" in arg]
        return "identity_env" if _env_sets_identity((n, v) for n, _, v in pairs) else None
    if git is None:
        return None
    if any(key.lower() in IDENTITY_KEYS for key, _ in git.config):
        return "identity_config"
    return _subcommand_rule(git)


def _subcommand_rule(git: GitInvocation) -> str | None:
    sub = git.subcommand or ""
    if sub == "config":
        return "identity_config" if _config_write(git.args) else None
    if sub not in COMMIT_WRITERS:
        return None
    parsed = git_args(git.args, sub)
    if parsed.has("--author"):
        return "author"
    signing = _TAG_SIGNING_FLAGS if sub == "tag" else _SIGNING_FLAGS
    return "signing" if parsed.has(*signing) else None


def _config_write(args: tuple[str, ...]) -> bool:
    """A ``git config`` that writes one of :data:`IDENTITY_KEYS` (a bare key is a read)."""
    words = config_words(args)
    if not words or words[0].lower() not in IDENTITY_KEYS:
        return False
    return len(words) > 1 or any(arg in _CONFIG_WRITE_VERBS for arg in args)


def _env_sets_identity(env: Iterable[tuple[str, str]]) -> bool:
    for name, value in env:
        if name.startswith(_IDENTITY_ENV):
            return True
        if _CONFIG_KEY_ENV.fullmatch(name) and value.lower() in IDENTITY_KEYS:
            return True
        if name == "GIT_CONFIG_PARAMETERS" and any(k in value.lower() for k in IDENTITY_KEYS):
            return True
    return False
