"""Harness I/O: payload parsers and wire renderers (specs/prK-lifecycle-hooks.md §D.2.2, §D.3.5).

Each harness module has one parser and one renderer. A parser turns the
stdin bytes into a ``CanonicalEvent``, a ``ForeignPayload`` (another harness
reached us through ``.claude/settings.json``: stay inert, §C.5.2) or a
``ContractFault`` (our own harness sent something unusable: the failure
policy decides, §D.4). A renderer turns a ``CombinedResult`` into the
``WireOutput`` the dispatcher writes once; it never touches a stream itself.

The dispatch process exits ``0`` or ``DENY_EXIT``. It never exits 2 itself:
the launcher and the OpenCode shim map 10 to the harness deny, so a crash or
a usage error that happens to exit 2 can never pass for a deny (K-7).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.event import CanonicalEvent, EventName, RepoInfo
from coding_agent_playbook.hook_runtime.paths import find_repo

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = [
    "CLAUDE_EVENT_NAMES",
    "DENY_EXIT",
    "HARNESS_DENY_EXIT",
    "STDIN_CAP_BYTES",
    "ContractFault",
    "ForeignPayload",
    "ParseContext",
    "ParseOutcome",
    "WireOutput",
]

#: The dispatch process's deny exit; the launcher and the shim map it (K-7).
DENY_EXIT: Final = 10
#: What a harness sees for ``DENY_EXIT``: Claude's blocking exit code.
HARNESS_DENY_EXIT: Final = 2
#: stdin is read up to this many bytes; the rest is drained unread (§D.1).
STDIN_CAP_BYTES: Final = 16 * 1024 * 1024

#: Canonical event -> Claude's (and the shim's Claude-shaped) ``hook_event_name``.
CLAUDE_EVENT_NAMES: Final[Mapping[EventName, str]] = MappingProxyType(
    {
        EventName.SESSION_START: "SessionStart",
        EventName.USER_PROMPT_SUBMIT: "UserPromptSubmit",
        EventName.PRE_TOOL_USE: "PreToolUse",
        EventName.POST_TOOL_USE: "PostToolUse",
        EventName.POST_TOOL_USE_FAILURE: "PostToolUseFailure",
        EventName.STOP: "Stop",
        EventName.SUBAGENT_STOP: "SubagentStop",
        EventName.PRE_COMPACT: "PreCompact",
        EventName.SESSION_END: "SessionEnd",
    }
)


@dataclass(frozen=True, slots=True)
class WireOutput:
    """What one dispatch writes: stdout, stderr and the process exit code.

    ``exit_code`` is the dispatch process's own (``0`` or ``DENY_EXIT``);
    ``harness_exit_code`` is what the harness sees after the launcher maps it.

    Example::

        >>> WireOutput(exit_code=DENY_EXIT).harness_exit_code
        2
    """

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0

    @property
    def harness_exit_code(self) -> int:
        """The launcher's mapping: ``DENY_EXIT`` becomes 2, anything else 0 (A-C2)."""
        return HARNESS_DENY_EXIT if self.exit_code == DENY_EXIT else 0


@dataclass(frozen=True, slots=True, kw_only=True)
class ForeignPayload:
    """A payload another harness sent: exit 0 with no output, logged once per session.

    ``marker`` names the heuristic that fired (``event_mismatch``,
    ``missing_session_id``, ``foreign_marker:<key>``, ``timestamp``,
    ``claude_project_dir_unset``). Example:
    ``ForeignPayload(event=EventName.STOP, marker="timestamp")``.
    """

    event: EventName
    marker: str
    session_id: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class ContractFault:
    """Our own harness sent a payload the runtime cannot use (§D.4).

    ``problem`` says what was wrong without quoting payload content; the
    failure policy asks on ``pre_tool_use`` and stays silent elsewhere.
    Example: ``ContractFault(event=EventName.PRE_TOOL_USE, problem="tool_name missing")``.
    """

    event: EventName
    problem: str
    session_id: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class ParseContext:
    """Everything a parser needs besides the payload bytes.

    ``argv_event`` is the event the registration was made for; ``env`` the
    hook process environment; ``project_dir`` the ``--project-dir`` argument
    (``None`` when absent); ``home`` expands ``~`` in tool paths (``None``:
    never expanded); ``truncated`` says stdin hit ``STDIN_CAP_BYTES``.
    ``platform`` and ``find_repo`` are injectable so goldens are host-independent.

    Example: ``ParseContext(argv_event=EventName.STOP, env=os.environ)``.
    """

    argv_event: EventName
    env: Mapping[str, str]
    project_dir: str | None = None
    home: str | None = None
    platform: str = sys.platform
    truncated: bool = False
    find_repo: Callable[[str], RepoInfo | None] = field(default=find_repo)


type ParseOutcome = CanonicalEvent | ForeignPayload | ContractFault
