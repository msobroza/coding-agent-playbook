"""Tool-call normalization: classify the tool and read its paths and content (§D.2.3).

Both harnesses send Claude-shaped tool names (the OpenCode shim maps its own,
§C.3.3), so one table classifies them; ``apply_patch`` passes through and is
both an edit and a write. Path arguments are read only from the fields the
class defines (``file_path`` or its native ``filePath``, ``notebook_path``,
a search's ``path``): a glob/grep ``path`` is a search directory and is never
read as a file argument. A missing required argument is a contract fault,
because a guard that cannot see the target cannot vouch for the call.
"""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.event import (
    ContentFragment,
    EventName,
    ShellSource,
    ToolCall,
    ToolClass,
    ToolResponse,
)
from coding_agent_playbook.hook_runtime.harness._payload import host_path, opt_str
from coding_agent_playbook.hook_runtime.paths import NormalizedPath, normalize_path

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.harness import ParseContext
    from coding_agent_playbook.hook_runtime.harness._payload import Payload

__all__ = ["APPLY_PATCH", "TOOL_CLASSES", "build_tool_call", "classify"]

APPLY_PATCH: Final = "apply_patch"
_MCP_PREFIX = "mcp__"

#: Claude-shaped tool name -> its classes, the first one primary (the §A.2 table).
TOOL_CLASSES: Final[Mapping[str, tuple[ToolClass, ...]]] = MappingProxyType(
    {
        "Bash": (ToolClass.SHELL,),
        "PowerShell": (ToolClass.SHELL,),
        "Edit": (ToolClass.EDIT,),
        "MultiEdit": (ToolClass.EDIT,),
        "Write": (ToolClass.WRITE,),
        "NotebookEdit": (ToolClass.NOTEBOOK_EDIT,),
        "Read": (ToolClass.READ,),
        "Glob": (ToolClass.SEARCH,),
        "Grep": (ToolClass.SEARCH,),
        "WebFetch": (ToolClass.WEB,),
        "WebSearch": (ToolClass.WEB,),
        "Agent": (ToolClass.SUBAGENT,),
        "Task": (ToolClass.SUBAGENT,),
        APPLY_PATCH: (ToolClass.EDIT, ToolClass.WRITE),
    }
)

#: The path argument of each path-bearing class: Claude's name first, then OpenCode's.
_PATH_KEYS: Final[Mapping[ToolClass, tuple[str, ...]]] = MappingProxyType(
    {
        ToolClass.EDIT: ("file_path", "filePath"),
        ToolClass.WRITE: ("file_path", "filePath"),
        ToolClass.READ: ("file_path", "filePath"),
        ToolClass.NOTEBOOK_EDIT: ("notebook_path",),
        ToolClass.SEARCH: ("path",),
    }
)
_OPTIONAL_PATH = frozenset({ToolClass.SEARCH})
_WRITING = frozenset({ToolClass.EDIT, ToolClass.WRITE, ToolClass.NOTEBOOK_EDIT})
#: Content fields; within a group the first present wins (OpenCode sends both spellings).
_CONTENT_KEYS: Final = (("content",), ("new_string", "newString"), ("new_source",))
_EXIT_CODE = re.compile(r"\AExit code (\d+)")

type _Targets = tuple[
    tuple[NormalizedPath, ...], tuple[NormalizedPath, ...], tuple[ContentFragment, ...]
]


def classify(name: str) -> tuple[ToolClass, ...]:
    """The classes of the Claude-shaped tool ``name``, the primary one first.

    Example::

        >>> classify("mcp__github__create_issue")
        (<ToolClass.MCP: 'mcp'>,)
    """
    if name.startswith(_MCP_PREFIX):
        return (ToolClass.MCP,)
    return TOOL_CLASSES.get(name, (ToolClass.OTHER,))


def build_tool_call(
    payload: Payload,
    ev: CanonicalEvent,
    ctx: ParseContext,
    *,
    native_names: Mapping[str, str] = MappingProxyType({}),
) -> ToolCall | str:
    """The event's ``ToolCall``, or the problem that makes the payload a contract fault.

    ``native_names`` maps a Claude-shaped name back to the harness's own
    (OpenCode's ``Bash`` -> ``bash``); a name it lacks is its own native name.

    Example::

        build_tool_call({"tool_name": "Read", "tool_input": {"file_path": "a"}}, ev, ctx)
    """
    name = opt_str(payload, "tool_name")
    if not name:
        return "tool_name missing or not a string"
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return "tool_input missing or not an object"
    classes = classify(name)
    targets = _targets(name, classes[0], tool_input, ev, ctx)
    if isinstance(targets, str):
        return targets
    shell = _shell(name, classes[0], tool_input, ev, ctx)
    if isinstance(shell, str):
        return shell
    paths, write_paths, content = targets
    return ToolCall(
        name=name,
        native_name=native_names.get(name, name),
        tool_class=classes[0],
        tool_classes=frozenset(classes),
        use_id=opt_str(payload, "tool_use_id"),
        paths=paths,
        write_paths=write_paths,
        content=content,
        mcp_server=_mcp_server(payload, name) if classes[0] is ToolClass.MCP else None,
        response=_response(payload, ev.name, shell=classes[0] is ToolClass.SHELL),
        raw_input=tool_input,
        shell=shell,
    )


def _targets(
    name: str, primary: ToolClass, tool_input: dict[str, Any], ev: CanonicalEvent, ctx: ParseContext
) -> _Targets | str:
    """``(paths, write_paths, content)`` of the call, or the missing-argument problem."""
    if name == APPLY_PATCH:
        return _patch_targets(tool_input, ev, ctx)
    keys = _PATH_KEYS.get(primary)
    if keys is None:
        return (), (), ()
    raw = next((v for v in (opt_str(tool_input, k) for k in keys) if v), None)
    if raw is None:
        missing = f"tool_input.{keys[0]} missing or not a string"
        return ((), (), ()) if primary in _OPTIONAL_PATH else missing
    paths = (_normalize(raw, ev, ctx),)
    if primary not in _WRITING:
        return paths, (), ()
    return paths, paths, _content(tool_input, raw)


def _patch_targets(
    tool_input: dict[str, Any], ev: CanonicalEvent, ctx: ParseContext
) -> _Targets | str:
    text = opt_str(tool_input, "patch_text") or opt_str(tool_input, "patchText")
    if text is None:
        return "tool_input.patch_text missing or not a string"
    # Imported here: only OpenCode's apply_patch carries an envelope to parse.
    from coding_agent_playbook.hook_runtime.harness._patch import parse_patch

    envelope = parse_patch(text)
    paths = tuple(_normalize(raw, ev, ctx) for raw in envelope.paths)
    content = tuple(
        ContentFragment(path=raw, field="patch", text=added) for raw, added in envelope.added
    )
    return paths, paths, content


def _content(tool_input: dict[str, Any], raw_path: str) -> tuple[ContentFragment, ...]:
    """The text a write or edit persists: ``content``, ``new_string``, ``edits[].new_string``."""
    fragments = []
    for group in _CONTENT_KEYS:
        key = next((k for k in group if isinstance(tool_input.get(k), str)), None)
        if key is not None:
            fragments.append(ContentFragment(path=raw_path, field=key, text=tool_input[key]))
    edits = tool_input.get("edits")
    for index, edit in enumerate(edits if isinstance(edits, list) else ()):
        text = opt_str(edit, "new_string") if isinstance(edit, dict) else None
        if text is not None:
            fragments.append(
                ContentFragment(path=raw_path, field=f"edits[{index}].new_string", text=text)
            )
    return tuple(fragments)


def _shell(
    name: str, primary: ToolClass, tool_input: dict[str, Any], ev: CanonicalEvent, ctx: ParseContext
) -> ShellSource | str | None:
    """The shell source of a SHELL call (OpenCode's ``workdir`` is its cwd), else ``None``."""
    if primary is not ToolClass.SHELL:
        return None
    command = opt_str(tool_input, "command")
    if command is None:
        return "tool_input.command missing or not a string"
    workdir = opt_str(tool_input, "workdir")
    cwd = host_path(workdir, base=ev.cwd, ctx=ctx) if workdir else ev.cwd
    return ShellSource(
        text=command, kind="powershell" if name == "PowerShell" else "posix", cwd=cwd
    )


def _normalize(raw: str, ev: CanonicalEvent, ctx: ParseContext) -> NormalizedPath:
    return normalize_path(raw, base=ev.cwd, repo=ev.repo, home=ctx.home, platform=ctx.platform)


def _mcp_server(payload: Payload, name: str) -> str | None:
    """Claude's ``mcp_server.name`` (v2.1.274+), else the ``<server>`` of ``mcp__<server>__<tool>``."""
    server = payload.get("mcp_server")
    if isinstance(server, dict) and isinstance(server.get("name"), str):
        return str(server["name"])
    parts = name.split("__")
    return parts[1] if len(parts) >= 3 and parts[1] else None


def _response(payload: Payload, event: EventName, *, shell: bool) -> ToolResponse | None:
    """What a post event reports about the finished call; ``None`` before it ran.

    A successful shell call keeps its output text (only a shell's: a Read's
    response is file content no hook needs).
    """
    if event is EventName.POST_TOOL_USE:
        output = payload.get("tool_response")
        interrupted = isinstance(output, dict) and output.get("interrupted") is True
        text = _shell_output(output) if shell else None
        return ToolResponse(ok=True, is_interrupt=interrupted, output=text)
    if event is EventName.POST_TOOL_USE_FAILURE:
        error = opt_str(payload, "error")
        match = _EXIT_CODE.match(error or "")
        return ToolResponse(
            ok=False,
            exit_code=int(match.group(1)) if match else None,
            error=error,
            is_interrupt=payload.get("is_interrupt") is True,
        )
    return None


def _shell_output(response: object) -> str | None:
    """Claude's ``stdout`` + ``stderr``, OpenCode's ``output``; ``None`` when neither is text."""
    if isinstance(response, str):
        return response
    if not isinstance(response, dict):
        return None
    parts = [response.get(key) for key in ("stdout", "stderr", "output")]
    texts = [part for part in parts if isinstance(part, str) and part]
    return "\n".join(texts) if texts else None
