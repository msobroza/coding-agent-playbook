"""block-precommit-bypass's command rows, one parsed shell segment at a time (specs/prK-hook-pack.md §E.2).

:func:`segment_verdict` judges what one segment *runs*; the handler adds the
``.git/hooks/**`` write targets. Denied:

- ``--no-verify`` on commit, push, merge, rebase, cherry-pick or am, and ``-n``
  on ``git commit`` only (combined short flags too; on push ``-n`` is dry-run);
- ``SKIP=`` naming a playbook hook id (any ``SKIP=`` under ``strict_skip``),
  ``PRE_COMMIT_ALLOW_NO_CONFIG`` and ``pre-commit uninstall``;
- ``core.hooksPath`` set through ``git -c``, ``git config`` or the
  ``GIT_CONFIG_*`` / ``GIT_CONFIG_PARAMETERS`` environment, and ``alias.*``
  injected through the environment;
- an ``alias.*`` value that carries ``--no-verify``, a commit ``-n`` or ``hooksPath``.

``git commit-tree`` and ``git update-ref`` outside an in-progress rebase ask.
Option values (``-m "fix -n handling"``) and heredoc bodies are data, never flags.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.shell.git_command import parse_git
from coding_agent_playbook.hook_runtime.shell.git_options import config_words, git_args

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.hook_runtime.shell.git_command import GitInvocation
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

    type Verdict = tuple[Decision, str]

__all__ = ["BYPASS_SUBCOMMANDS", "PLUMBING", "alias_bypasses", "segment_verdict"]

#: The subcommands that run hooks ``--no-verify`` skips.
BYPASS_SUBCOMMANDS: Final = frozenset({"commit", "push", "merge", "rebase", "cherry-pick", "am"})
#: Plumbing that writes commits or refs without running any hook.
PLUMBING: Final = frozenset({"commit-tree", "update-ref"})
_CONFIG_KEY: Final = re.compile(r"GIT_CONFIG_KEY_\d+")
_HOOKS_PATH: Final = "core.hookspath"


def segment_verdict(
    segment: Segment, *, ids: frozenset[str], strict_skip: bool, in_rebase: bool
) -> Verdict | None:
    """The ``(decision, rule)`` of one segment's command and env prefix, or ``None``.

    Example::

        >>> from coding_agent_playbook.hook_runtime.shell.parse import parse_shell
        >>> seg = parse_shell("git commit -nm x", "posix", "/r").segments[0]
        >>> segment_verdict(seg, ids=frozenset({"playbook-validate"}), strict_skip=False,
        ...                 in_rebase=False)
        (<Decision.DENY: 'deny'>, 'no_verify')
    """
    found = _env_verdict(segment.env, ids, strict_skip)
    if found is not None or not segment.argv:
        return found
    program, args = posixpath.basename(segment.argv[0]), segment.argv[1:]
    if program == "export":
        pairs = [arg.partition("=") for arg in args if "=" in arg]
        return _env_verdict([(name, value) for name, _, value in pairs], ids, strict_skip)
    if program == "pre-commit":
        return (Decision.DENY, "precommit_uninstall") if "uninstall" in args else None
    git = parse_git(segment)
    return None if git is None else _git_verdict(git, in_rebase)


def alias_bypasses(value: str) -> bool:
    """Whether an ``alias.*`` value skips hooks: ``--no-verify``, ``hooksPath`` or commit ``-n``.

    Example::

        >>> alias_bypasses("commit --no-verify"), alias_bypasses("log -n 5")
        (True, False)
    """
    lowered = value.lower()
    if "--no-verify" in lowered or "hookspath" in lowered:
        return True
    words = value.split()
    if "commit" not in words:
        return False
    return "n" in git_args(words[words.index("commit") + 1 :], "commit").shorts


def _env_verdict(
    env: Iterable[tuple[str, str]], ids: frozenset[str], strict_skip: bool
) -> Verdict | None:
    """The env prefix rows: ``SKIP=``, ``PRE_COMMIT_ALLOW_NO_CONFIG``, injected git config."""
    for name, value in env:
        if name == "SKIP" and _skips(value, ids, strict_skip):
            return Decision.DENY, "skip_env"
        if name == "PRE_COMMIT_ALLOW_NO_CONFIG" and value:
            return Decision.DENY, "allow_no_config"
        if name == "GIT_CONFIG_PARAMETERS" and _injects(value.lower()):
            return Decision.DENY, "config_injection"
        if _CONFIG_KEY.fullmatch(name) and _injects_key(value.lower()):
            return Decision.DENY, "config_injection"
    return None


def _skips(value: str, ids: frozenset[str], strict_skip: bool) -> bool:
    skipped = {item.strip() for item in value.split(",") if item.strip()}
    return bool(skipped) and (strict_skip or bool(skipped & ids))


def _injects(lowered: str) -> bool:
    return _HOOKS_PATH in lowered or "alias." in lowered


def _injects_key(lowered: str) -> bool:
    return lowered == _HOOKS_PATH or lowered.startswith("alias.")


def _git_verdict(git: GitInvocation, in_rebase: bool) -> Verdict | None:
    for key, value in git.config:  # ``-c`` (env pairs were judged above)
        lowered = key.lower()
        if lowered == _HOOKS_PATH or (lowered.startswith("alias.") and alias_bypasses(value)):
            return Decision.DENY, "hooks_path" if lowered == _HOOKS_PATH else "alias"
    sub = git.subcommand or ""
    if sub == "config":
        return _config_verdict(git.args)
    parsed = git_args(git.args, sub)
    if sub in BYPASS_SUBCOMMANDS and parsed.has("--no-verify"):
        return Decision.DENY, "no_verify"
    if sub == "commit" and parsed.has("n"):
        return Decision.DENY, "no_verify"
    if sub in PLUMBING and not in_rebase:
        return Decision.ASK, "plumbing"
    return None


def _config_verdict(args: Sequence[str]) -> Verdict | None:
    """``git config [set] core.hooksPath ...`` and ``git config alias.<x> <bypass>``."""
    words = config_words(args)
    if not words:
        return None
    key, value = words[0].lower(), " ".join(words[1:])
    if key == _HOOKS_PATH:
        return Decision.DENY, "hooks_path"
    if key.startswith("alias.") and alias_bypasses(value):
        return Decision.DENY, "alias"
    return None
