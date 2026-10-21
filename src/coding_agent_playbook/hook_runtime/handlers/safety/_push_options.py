"""git-commit-push-policy-guard's push-option judge, always on (specs/prF-forge-adapter.md §8.4, Q51).

A forge reads git push options server-side: GitLab skips its secret push
protection, sets CI/CD variables or inputs, skips the pipeline or opens a
merge request. The options come from ``git push -o`` / ``--push-option`` and,
when none is given, from ``push.pushOption`` config, so every surface that
sets one is read, whatever the remote's forge (Q7):

- ``git push -o X`` / ``--push-option[=]X`` / ``-oX``, and git's unambiguous
  abbreviations of ``--push-option`` (``--push-opt=X``);
- ``push.pushOption`` through ``git -c`` / ``--config-env``, a
  ``GIT_CONFIG_COUNT`` / ``KEY_n`` / ``VALUE_n`` or ``GIT_CONFIG_PARAMETERS``
  env prefix (on any command: a forge CLI that pushes inherits it) or
  ``export``, a ``git config`` write, and a ``pushOption =`` line a file tool
  writes into the repository's git config file;
- a commit message carrying a forge's secret-skip marker
  (``[skip secret push protection]``, any case), judged when ``git commit``
  writes it (the commits a push publishes are not read: no git on the hot path).

The table is each forge's ``push_options`` (``forge.dialects``): skipping the
secret push protection or bypassing a security policy's push protection denies; a CI variable or input, or a skipped
pipeline, asks; ``merge_request.create`` (GitLab's merge request) is a pull
request, which the caller's ``push_requires_green`` judges as the push it is,
and ``merge_request.description`` is sent text, no verdict of its own. Each
function returns every verdict; the caller keeps the strongest. Reasons name
the option, never its value (a ``ci.variable`` value may be a secret), and
never teach a way around.

A private module: it registers no handler.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.shell.git_options import config_words, git_args

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from coding_agent_playbook.forge.dialects import PushOptionEffect
    from coding_agent_playbook.hook_runtime.shell.git_command import GitInvocation
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

    type Verdict = tuple[Decision, str, str]

__all__ = ["config_file_verdicts", "marker_verdicts", "segment_options", "segment_verdicts"]

_KEY: Final = "push.pushoption"
_LONG: Final = "--push-option"
#: The shortest abbreviation git takes for ``--push-option``: no other push option starts so.
_LONG_PREFIX: Final = "--pu"
_CONFIG_KEY_ENV: Final = re.compile(r"GIT_CONFIG_KEY_(\d+)")
#: ``GIT_CONFIG_PARAMETERS``' ``'key'='value'`` pairs, and git's older ``'key=value'``.
_PARAMETER: Final = re.compile(r"'([^'=]+)'='([^']*)'|'([^'=]+)=([^']*)'")
#: A ``pushOption = value`` line of a git config file (any section: the conservative read).
_CONFIG_LINE: Final = re.compile(r"^\s*pushoption\s*=\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)
_CONFIRM: Final = "Confirm with the user."


def segment_options(segment: Segment, git: GitInvocation | None) -> list[str]:
    """Every push option ``segment`` sets or writes, in order (``name`` or ``name=value``).

    Example::

        >>> segment_options(seg("git push -o ci.skip"), parse_git(seg("git push -o ci.skip")))
        ... # doctest: +SKIP
        ['ci.skip']
    """
    found = list(_env_options(segment.env))
    program = posixpath.basename(segment.argv[0]) if segment.argv else ""
    if program == "export":
        pairs = [arg.partition("=") for arg in segment.argv[1:] if "=" in arg]
        found.extend(_env_options((name, value) for name, _, value in pairs))
    if git is None:
        return found
    found.extend(value for key, value in git.config if key.lower() == _KEY)
    sub = git.subcommand or ""
    if sub == "push":
        found.extend(git_args(git.args, sub).values_of("-o"))
        found.extend(_long_options(git.args))
    elif sub == "config":
        words = config_words(git.args)
        if words and words[0].lower() == _KEY and len(words) > 1:
            found.append(words[1])
    return found


def segment_verdicts(segment: Segment, git: GitInvocation | None) -> list[Verdict]:
    """The verdicts on the push options ``segment`` sets.

    Example: ``segment_verdicts(seg, git)[0][1] == "push_option_skip_ci"`` for ``git push -o ci.skip``.
    """
    return _verdicts(segment_options(segment, git))


def config_file_verdicts(before: str | None, after: str) -> list[Verdict]:
    """The verdicts on the ``pushOption`` lines ``after`` adds to a git config file's ``before``.

    Example: ``config_file_verdicts("", "[push]\\n\\tpushOption = ci.skip\\n")[0][0]`` is ``ASK``.
    """
    kept = _CONFIG_LINE.findall(before or "")
    added: list[str] = []
    for value in _CONFIG_LINE.findall(after):
        if value in kept:
            kept.remove(value)
        else:
            added.append(value.strip("\"'"))
    return _verdicts(added)


def marker_verdicts(messages: Iterable[str]) -> list[Verdict]:
    """Deny a commit message that carries a forge's secret-skip marker (§8.4), any case.

    Example: ``marker_verdicts(["fix [skip secret push protection]"])[0][0]`` is ``DENY``.
    """
    from coding_agent_playbook.forge.dialects import FORGES

    for message in messages:
        lowered = message.lower()
        marker = next(
            (m for forge in FORGES for m in forge.secret_skip_markers if m.lower() in lowered),
            None,
        )
        if marker is not None:
            reason = (
                f"Blocked: the commit message carries {marker}, which turns off the forge's "
                "secret push protection for the push.\nTake it out of the message."
            )
            return [(Decision.DENY, "secret_skip_marker", reason)]
    return []


def _effects(option: str) -> Iterator[PushOptionEffect]:
    from coding_agent_playbook.forge.dialects import FORGES

    for forge in FORGES:
        effect = forge.push_option(option)
        if effect is not None:
            yield effect


def _option_verdict(option: str) -> Verdict | None:
    name = option.partition("=")[0].strip()
    effects = set(_effects(option))
    if "skips_secret_detection" in effects:
        reason = (
            f"Blocked: the push option {name} turns off the forge's secret push protection.\n"
            "Push without it; if the forge flags a false positive, tell the user."
        )
        return Decision.DENY, "push_option_secret_skip", reason
    if "bypasses_security_policy" in effects:
        reason = (
            f"Blocked: the push option {name} bypasses the forge's security policy push "
            "protection.\nPush without it; if the policy blocks the push, tell the user."
        )
        return Decision.DENY, "push_option_policy_bypass", reason
    if "sets_ci_input" in effects:
        reason = (
            f"The push option {name} sets a CI/CD variable or input of the pipeline this push "
            f"starts.\n{_CONFIRM}"
        )
        return Decision.ASK, "push_option_ci_input", reason
    if "skips_ci" in effects:
        reason = f"The push option {name} skips the forge's CI pipeline for this push.\n{_CONFIRM}"
        return Decision.ASK, "push_option_skip_ci", reason
    return None


def _env_options(env: Iterable[tuple[str, str]]) -> Iterator[str]:
    """``push.pushOption`` values a ``GIT_CONFIG_*`` env sets (any index: the conservative read)."""
    pairs = dict(env)
    for name, value in pairs.items():
        match = _CONFIG_KEY_ENV.fullmatch(name)
        if match is not None and value.lower() == _KEY:
            yield pairs.get(f"GIT_CONFIG_VALUE_{match[1]}", "")
        elif name == "GIT_CONFIG_PARAMETERS":
            for found in _PARAMETER.finditer(value):
                key, option = (found[1], found[2]) if found[1] else (found[3], found[4])
                if key.lower() == _KEY:
                    yield option


def _verdicts(options: Iterable[str]) -> list[Verdict]:
    return [verdict for option in options if (verdict := _option_verdict(option)) is not None]


def _long_options(args: Sequence[str]) -> Iterator[str]:
    """``--push-option`` values, the abbreviations git accepts included (``--push-opt=X``)."""
    index = 0
    while index < len(args) and args[index] != "--":
        name, glued, value = args[index].partition("=")
        index += 1
        if len(name) < len(_LONG_PREFIX) or not _LONG.startswith(name):
            continue
        if glued:
            yield value
        elif index < len(args):
            yield args[index]
            index += 1
