"""The canonical event every harness payload is normalized into (specs/prK-lifecycle-hooks.md §D.2.1).

Handlers see one frozen, slotted ``CanonicalEvent`` whatever the harness. The
runtime may not import ``types`` or ``hook_policy`` (§D.1), so the enumerations
here re-declare their sync-side twins; ``tests/hook_runtime/test_event.py`` pins
each one to its single source. Content-bearing fields stay out of ``repr``: the
decision log stores no content (D-10), and a stray ``repr`` in an internal note
must not leak any.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.shell import ShellCommand, ShellConfig, ShellKind

SESSION_ID_MAX_CHARS: Final = 128
STOP_MESSAGE_MAX_CHARS: Final = 8_000
TOOL_ERROR_MAX_CHARS: Final = 2_000

_UNSAFE_SESSION_CHAR = re.compile(r"[^A-Za-z0-9._-]")


class EventName(StrEnum):
    """The nine canonical hook events, valued by their shared snake_case names (§A.2).

    Example: ``EventName("pre_tool_use") is EventName.PRE_TOOL_USE``.
    """

    SESSION_START = "session_start"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    POST_TOOL_USE_FAILURE = "post_tool_use_failure"
    STOP = "stop"
    SUBAGENT_STOP = "subagent_stop"
    PRE_COMPACT = "pre_compact"
    SESSION_END = "session_end"


class Harness(StrEnum):
    """The dispatching harnesses, valued by their adapter entry-point names.

    Example: ``Harness("opencode") is Harness.OPENCODE``.
    """

    CLAUDE_CODE = "claude_code"
    OPENCODE = "opencode"


class ToolClass(StrEnum):
    """The §A.2 tool classes (K-1) plus ``OTHER``, the runtime-only class of unmapped tools.

    Only a matcher that matches every tool selects ``OTHER``. Example:
    ``ToolClass("notebook_edit") is ToolClass.NOTEBOOK_EDIT``.
    """

    SHELL = "shell"
    EDIT = "edit"
    WRITE = "write"
    NOTEBOOK_EDIT = "notebook_edit"
    READ = "read"
    SEARCH = "search"
    WEB = "web"
    SUBAGENT = "subagent"
    MCP = "mcp"
    OTHER = "other"


def sanitize_session_id(raw: object) -> str:
    """Return ``raw`` as a session id that is safe as one path component.

    The id names a directory under the state root (§D.6.1): every character
    outside ``[A-Za-z0-9._-]`` becomes ``_``, the result is cut to 128
    characters, and an all-dots id (``.``, ``..``) has its dots replaced too.
    A missing or non-string id is ``""``.

    Example::

        >>> sanitize_session_id("../etc/passwd"), sanitize_session_id("..")
        ('.._etc_passwd', '__')
    """
    if not isinstance(raw, str):
        return ""
    safe = _UNSAFE_SESSION_CHAR.sub("_", raw)[:SESSION_ID_MAX_CHARS]
    if safe and not safe.strip("."):
        return "_" * len(safe)
    return safe


@dataclass(frozen=True, slots=True, kw_only=True)
class RepoInfo:
    """The event's repository, found without git by ``paths.find_repo`` (§D.2.4).

    ``git_dir`` is per worktree (``.git`` or ``.git/worktrees/<name>``) and
    ``common_dir`` shared. ``sibling_roots`` are the other worktrees sharing
    ``common_dir``, main checkout included: their paths still belong to this
    repository (OQ-24). Example: ``RepoInfo(worktree_root="/r", git_dir="/r/.git",
    common_dir="/r/.git", is_linked_worktree=False)``.
    """

    worktree_root: str
    git_dir: str
    common_dir: str
    is_linked_worktree: bool
    sibling_roots: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class StopInfo:
    """What a ``stop`` / ``subagent_stop`` event carries.

    Only the last 8,000 characters of ``last_assistant_message`` are kept: the
    output-contract stage reads the end of a turn, and no handler needs more.
    Example: ``StopInfo(stop_hook_active=False, last_assistant_message="done")``.
    """

    stop_hook_active: bool
    last_assistant_message: str = field(default="", repr=False)
    agent_transcript_path: str | None = None

    def __post_init__(self) -> None:
        message = self.last_assistant_message
        if len(message) > STOP_MESSAGE_MAX_CHARS:
            object.__setattr__(self, "last_assistant_message", message[-STOP_MESSAGE_MAX_CHARS:])


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolResponse:
    """The outcome a ``post_tool_use`` / ``post_tool_use_failure`` event reports.

    ``exit_code`` comes from the ``Exit code N`` prefix of a failure; ``error``
    keeps its first 2,000 characters, where the cause usually is. Example:
    ``ToolResponse(ok=False, exit_code=1, error="boom")``.
    """

    ok: bool
    exit_code: int | None = None
    error: str | None = None
    is_interrupt: bool = False

    def __post_init__(self) -> None:
        if self.error is not None and len(self.error) > TOOL_ERROR_MAX_CHARS:
            object.__setattr__(self, "error", self.error[:TOOL_ERROR_MAX_CHARS])


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentFragment:
    """Text a tool call is about to persist, as ``(path, field, text)``.

    ``path`` is the raw payload path (the ``NormalizedPath.raw`` it belongs to)
    and ``field`` the payload field (``content``, ``edits[2].new_string``,
    ``patch``, ...). Example: ``ContentFragment(path="a.py", field="content", text="x")``.
    """

    path: str
    field: str
    # Qualified: the ``field`` annotation above shadows ``dataclasses.field`` here.
    text: str = dataclasses.field(repr=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ShellSource:
    """What a shell tool call's ``command`` is parsed from (§D.2.5).

    ``cwd`` is where the first segment starts (OpenCode's ``workdir``, else the
    event cwd); ``config`` is ``guard_config.shell``, or ``None`` for the engine
    default. Example: ``ShellSource(text="ls", cwd="/r")``.
    """

    text: str = field(repr=False)
    kind: ShellKind = "posix"
    cwd: str | None = None
    config: ShellConfig | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCall:
    """Everything a handler may inspect about one tool call, parsed once per event.

    ``tool_classes`` is every class the call belongs to (OpenCode's
    ``apply_patch`` both edits and writes, §D.2.3) and defaults to
    ``{tool_class}``. ``raw_input`` is kept as a read-only copy. ``command`` is
    parsed from ``shell`` on first access only, so non-shell events never load
    the shell parser.

    Example::

        >>> ToolCall(name="Edit", native_name="Edit", tool_class=ToolClass.EDIT).command is None
        True
    """

    name: str
    native_name: str
    tool_class: ToolClass
    tool_classes: frozenset[ToolClass] = frozenset()
    use_id: str | None = None
    paths: tuple[NormalizedPath, ...] = ()
    write_paths: tuple[NormalizedPath, ...] = ()
    content: tuple[ContentFragment, ...] = ()
    mcp_server: str | None = None
    response: ToolResponse | None = None
    raw_input: Mapping[str, object] = field(default_factory=dict, repr=False)
    shell: ShellSource | None = None
    #: The memoized parse of ``shell``; ``None`` until ``command`` is first read.
    _command: ShellCommand | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        classes = self.tool_classes or frozenset({self.tool_class})
        if self.tool_class not in classes:
            raise ValueError(
                f"tool_class {self.tool_class.value!r} is not in tool_classes "
                f"{sorted(cls.value for cls in classes)!r}"
            )
        object.__setattr__(self, "tool_classes", classes)
        object.__setattr__(self, "raw_input", MappingProxyType(dict(self.raw_input)))

    @property
    def command(self) -> ShellCommand | None:
        """The parsed shell command, or ``None`` for a call without ``shell``."""
        if self.shell is not None and self._command is None:
            object.__setattr__(self, "_command", _parse_shell(self.shell))
        return self._command

    def with_shell_config(self, config: ShellConfig) -> ToolCall:
        """A copy whose ``command`` parses with ``config`` (loaded after the payload)."""
        if self.shell is None:
            return self
        return dataclasses.replace(self, shell=dataclasses.replace(self.shell, config=config))


def _parse_shell(source: ShellSource) -> ShellCommand:
    # Imported here so that an Edit or Read event never loads the shell parser (§D.1).
    from coding_agent_playbook.hook_runtime.shell import DEFAULT_SHELL_CONFIG, parse_shell

    return parse_shell(source.text, source.kind, source.cwd, source.config or DEFAULT_SHELL_CONFIG)


@dataclass(frozen=True, slots=True, kw_only=True)
class CanonicalEvent:
    """One harness event, normalized; handlers never mutate it.

    ``session_id`` is sanitized on construction. ``repo`` is ``None`` outside
    git, where hooks are inert (K-12). ``cwd`` follows the agent's ``cd`` while
    ``project_dir`` stays at the session root. ``prompt`` is never logged and
    never persisted.

    Example::

        >>> CanonicalEvent(name=EventName.STOP, harness=Harness.CLAUDE_CODE,
        ...                session_id="s/1", cwd="/r", project_dir="/r").session_id
        's_1'
    """

    name: EventName
    harness: Harness
    session_id: str
    cwd: str
    project_dir: str
    turn_id: str | None = None
    repo: RepoInfo | None = None
    permission_mode: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None
    tool: ToolCall | None = None
    prompt: str | None = field(default=None, repr=False)
    source: str | None = None
    stop: StopInfo | None = None
    transcript_path: str | None = None
    unattended: bool = False
    truncated: bool = False
    raw_event_name: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", sanitize_session_id(self.session_id))
