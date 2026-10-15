"""git-commit-push-policy-guard's trailer rows, shared by the guard and its twin (specs/prK-hook-pack.md §E.4).

The engine ships the rows empty; a consumer's ``[hooks.git-commit-push-policy-guard]``
or an overlay fills them. :func:`commit_msg_violations` is the one judge of a
message, in session (the guard, on the parsed ``git commit``) and off the
workstation (``playbook check-commit-trailers``, commit-msg and CI):

- ``CP401`` a trailer whose key is in ``forbid_trailers`` (case-insensitive);
- ``CP402`` a ``Co-authored-by`` trailer naming no one in ``allowed_coauthors``
  (only when that list is set);
- ``CP403`` a ``required_trailers`` key that is missing, or whose value does
  not match its regex.

Only the trailer block counts: comment lines and everything after the ``>8``
scissors line dropped (as git does), then the last paragraph, never the
subject's. Each ``Key: value`` line of it is a trailer, folded continuation
lines included; unlike git's 25% rule a stray prose line does not hide the
trailers below it, as forges also read them. Subject and body form belong to
commitizen (§F.4), not here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["COAUTHOR_KEY", "GitPolicy", "commit_msg_violations", "trailer_block"]

#: The trailer key ``allowed_coauthors`` governs, compared case-insensitively.
COAUTHOR_KEY: Final = "co-authored-by"
_TRAILER: Final = re.compile(r"([A-Za-z0-9][A-Za-z0-9-]*)[ \t]*:[ \t]*(.*)")
_SCISSORS: Final = re.compile(r"^#? ?-+ >8 -+$")
_EMAIL: Final = re.compile(r"<([^<>]+)>")
_MAX_SHOWN: Final = 80


@dataclass(frozen=True, slots=True)
class GitPolicy:
    """The trailer rows of git-commit-push-policy-guard (all empty in the engine).

    Example::

        >>> GitPolicy.from_config({"forbid_trailers": ["Co-Authored-By"]}).has_rows
        True
    """

    forbid_trailers: tuple[str, ...] = ()
    allowed_coauthors: tuple[str, ...] = ()
    required_trailers: tuple[tuple[str, str], ...] = ()

    @property
    def has_rows(self) -> bool:
        """Whether any trailer row is configured (the twin and its CI row run only then)."""
        return bool(self.forbid_trailers or self.allowed_coauthors or self.required_trailers)

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> GitPolicy:
        """The rows of a handler config; values of the wrong shape are left out.

        Example::

            >>> GitPolicy.from_config({"required_trailers": {"Refs": "^[A-Z]+-\\\\d+$"}})
            GitPolicy(forbid_trailers=(), allowed_coauthors=(), required_trailers=(('Refs', '^[A-Z]+-\\\\d+$'),))
        """
        required = config.get("required_trailers")
        pairs = required.items() if isinstance(required, dict) else ()
        return cls(
            forbid_trailers=_strings(config.get("forbid_trailers")),
            allowed_coauthors=_strings(config.get("allowed_coauthors")),
            required_trailers=tuple(
                (str(key), value) for key, value in pairs if isinstance(value, str)
            ),
        )


def trailer_block(message: str) -> list[tuple[str, str]]:
    """The ``(key, value)`` trailers of ``message``'s trailer block, in order.

    Example::

        >>> trailer_block("feat: x\\n\\nbody\\n\\nRefs: AB-1\\nCo-authored-by: A <a@x>\\n")
        [('Refs', 'AB-1'), ('Co-authored-by', 'A <a@x>')]
    """
    paragraphs = _paragraphs(_cleaned(message))
    if len(paragraphs) < 2:  # the first paragraph is the subject, never trailers
        return []
    trailers: list[tuple[str, str]] = []
    folded = False
    for line in paragraphs[-1]:
        if line[:1] in (" ", "\t") and folded:  # a continuation of the trailer above
            key, value = trailers[-1]
            trailers[-1] = (key, f"{value} {line.strip()}")
            continue
        match = _TRAILER.fullmatch(line)
        folded = match is not None
        if match is not None:
            trailers.append((match.group(1), match.group(2).strip()))
    return trailers


def commit_msg_violations(message: str, policy: GitPolicy) -> list[str]:
    """One ``CPxxx`` line per broken trailer row (module docstring); ``[]`` when none.

    Example::

        >>> commit_msg_violations("fix: x\\n\\nCo-Authored-By: Bot <b@x>\\n",
        ...                       GitPolicy(forbid_trailers=("co-authored-by",)))
        ['CP401 forbidden trailer Co-Authored-By']
    """
    if not policy.has_rows:
        return []
    trailers = trailer_block(message)
    return [
        *_forbidden(trailers, policy),
        *_coauthors(trailers, policy),
        *_required(trailers, policy),
    ]


def _forbidden(trailers: list[tuple[str, str]], policy: GitPolicy) -> list[str]:
    banned = {name.lower() for name in policy.forbid_trailers}
    keys = dict.fromkeys(key for key, _ in trailers if key.lower() in banned)
    return [f"CP401 forbidden trailer {key}" for key in keys]


def _coauthors(trailers: list[tuple[str, str]], policy: GitPolicy) -> list[str]:
    if not policy.allowed_coauthors:
        return []
    allowed = {entry.strip().lower() for entry in policy.allowed_coauthors}
    return [
        f"CP402 co-author not in allowed_coauthors: {_shown(value)}"
        for key, value in trailers
        if key.lower() == COAUTHOR_KEY and not _is_allowed(value, allowed)
    ]


def _is_allowed(value: str, allowed: set[str]) -> bool:
    email = _EMAIL.search(value)
    return value.strip().lower() in allowed or (
        email is not None and email.group(1).strip().lower() in allowed
    )


def _required(trailers: list[tuple[str, str]], policy: GitPolicy) -> list[str]:
    lines: list[str] = []
    for name, pattern in policy.required_trailers:
        values = [value for key, value in trailers if key.lower() == name.lower()]
        problem = _pattern_problem(pattern)
        if problem is not None:
            lines.append(f"CP403 required trailer {name}: {problem}")
        elif not values:
            lines.append(f"CP403 missing required trailer {name}")
        elif not any(re.search(pattern, value) for value in values):
            lines.append(f"CP403 trailer {name} does not match {pattern}")
    return lines


def _pattern_problem(pattern: str) -> str | None:
    """Why ``pattern`` must not run on a message an agent wrote, else ``None``."""
    from coding_agent_playbook.security.secrets import screen_regex

    return screen_regex(pattern)


def _cleaned(message: str) -> list[str]:
    """The message lines git keeps: comments and everything below the scissors dropped."""
    kept: list[str] = []
    for line in message.splitlines():
        if _SCISSORS.match(line.strip()):
            break
        if not line.startswith("#"):
            kept.append(line.rstrip())
    return kept


def _paragraphs(lines: list[str]) -> list[list[str]]:
    paragraphs: list[list[str]] = [[]]
    for line in lines:
        if line.strip():
            paragraphs[-1].append(line)
        elif paragraphs[-1]:
            paragraphs.append([])
    return [paragraph for paragraph in paragraphs if paragraph]


def _shown(value: str) -> str:
    text = " ".join(value.split())
    return text if len(text) <= _MAX_SHOWN else f"{text[: _MAX_SHOWN - 1]}…"


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)
