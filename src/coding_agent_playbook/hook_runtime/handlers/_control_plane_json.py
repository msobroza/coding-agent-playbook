"""control-plane-guard's JSON verdicts: Claude settings, ``.mcp.json``, ``opencode.json(c)`` (specs/prK-hook-pack.md §E.1).

Each verdict compares the parsed document before and after the edit:

- **settings** (``.claude/settings*.json``, the user's ``settings*.json``):
  ``DENY`` when a managed playbook element (a scoped lock row: an element of
  the array at its JSON pointer whose canonical hash is the recorded one)
  disappears or changes, ``disableAllHooks`` or ``enableAllProjectMcpServers``
  is switched on, ``env`` changes at all (hatches and ``PYTHONPATH``
  injection; a speed bump, §D.7) or ``permissions.defaultMode`` becomes
  ``bypassPermissions``; ``ASK`` for new ``permissions.allow`` entries, an
  added or enabled MCP server, and ``enabledPlugins`` /
  ``extraKnownMarketplaces`` additions. The user's own hooks, ``model`` and
  every other key pass.
- **MCP** (``.mcp.json``; ``opencode.json(c)``'s ``mcp`` and ``plugin`` keys):
  ``ASK`` for an added or enabled server or plugin; nothing denies.

A document that does not parse (OpenCode's JSONC comments and trailing
commas are stripped first) or is not an object is ``None``: the caller asks.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook._canonical_json import element_sha256
from coding_agent_playbook.hook_runtime.decision import Decision

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

__all__ = [
    "load_json_object",
    "mcp_verdict",
    "opencode_verdict",
    "settings_verdict",
    "strip_jsonc",
]

type Doc = Mapping[str, Any]

_JSON_SCOPE: Final = "json:"
_ABSENT: Final = object()
_SPECIAL: Final = re.compile(r'"|//|/\*')
_STRING_OR_TRAILING_COMMA: Final = re.compile(r'"|,(?=\s*[}\]])')


def load_json_object(text: str, *, jsonc: bool = False) -> dict[str, Any] | None:
    """``text`` parsed as a JSON object (JSONC when ``jsonc``), else ``None``.

    Example::

        >>> load_json_object('{"a": 1, // note\\n}', jsonc=True)
        {'a': 1}
    """
    try:
        document = json.loads(strip_jsonc(text) if jsonc else text)
    except (ValueError, RecursionError):
        return None
    return document if isinstance(document, dict) else None


def settings_verdict(before: Doc, after: Doc, managed: Iterable[tuple[str, str]]) -> Decision:
    """The verdict on a Claude settings edit; ``managed`` holds ``(scope, sha256)`` rows.

    Example::

        >>> settings_verdict({}, {"disableAllHooks": True}, ())
        <Decision.DENY: 'deny'>
    """
    if _managed_removed(before, after, managed) or _settings_denied(before, after):
        return Decision.DENY
    if _settings_asked(before, after):
        return Decision.ASK
    return Decision.NONE


def mcp_verdict(before: Doc, after: Doc) -> Decision:
    """``.mcp.json``: ``ASK`` when a server is added or re-enabled, else ``NONE``.

    Example::

        >>> mcp_verdict({}, {"mcpServers": {"x": {"command": "x"}}})
        <Decision.ASK: 'ask'>
    """
    return Decision.ASK if _servers_enabled(before, after, "mcpServers") else Decision.NONE


def opencode_verdict(before: Doc, after: Doc) -> Decision:
    """``opencode.json(c)``: ``ASK`` for an added or enabled ``mcp`` server or ``plugin``.

    Example::

        >>> opencode_verdict({"plugin": []}, {"plugin": ["p"]})
        <Decision.ASK: 'ask'>
    """
    plugins = _strings(after.get("plugin")) - _strings(before.get("plugin"))
    if plugins or _servers_enabled(before, after, "mcp"):
        return Decision.ASK
    return Decision.NONE


def strip_jsonc(text: str) -> str:
    """``text`` without ``//`` / ``/* */`` comments and trailing commas (strings kept intact).

    Example::

        >>> strip_jsonc('{"u": "a//b", /* c */ "v": [1,],}')
        '{"u": "a//b",   "v": [1]}'
    """
    return _drop_trailing_commas(_drop_comments(text))


# --- settings rows ------------------------------------------------------------------------


def _managed_removed(before: Doc, after: Doc, managed: Iterable[tuple[str, str]]) -> bool:
    """Whether an element that matched a managed row before the edit no longer does."""
    for scope, sha256 in managed:
        if not scope.startswith(_JSON_SCOPE):
            continue
        pointer = scope.removeprefix(_JSON_SCOPE)
        if sha256 in _hashes(before, pointer) and sha256 not in _hashes(after, pointer):
            return True
    return False


def _settings_denied(before: Doc, after: Doc) -> bool:
    switched_on = any(
        _changed(before, after, (key,)) and after.get(key) not in (None, False)
        for key in ("disableAllHooks", "enableAllProjectMcpServers")
    )
    bypass = _get(after, ("permissions", "defaultMode")) == "bypassPermissions"
    return (
        switched_on
        or _changed(before, after, ("env",))
        or (bypass and _changed(before, after, ("permissions", "defaultMode")))
    )


def _settings_asked(before: Doc, after: Doc) -> bool:
    """New allow rules, MCP servers, plugins or marketplaces: the user approves each."""
    added = (
        _added(before, after, ("permissions", "allow"), _strings),
        _added(before, after, ("enabledMcpjsonServers",), _strings),
        _added(after, before, ("disabledMcpjsonServers",), _strings),  # a server re-enabled
        _added(before, after, ("enabledPlugins",), _enabled_keys),
        _added(before, after, ("extraKnownMarketplaces",), _keys),
    )
    return any(added) or _servers_enabled(before, after, "mcpServers")


def _added(
    before: Doc, after: Doc, path: tuple[str, ...], items: Callable[[object], set[str]]
) -> set[str]:
    """The ``items`` at ``path`` that ``after`` has and ``before`` has not."""
    return items(_get(after, path)) - items(_get(before, path))


def _servers_enabled(before: Doc, after: Doc, key: str) -> bool:
    """Whether a server under ``key`` is new, or was disabled and no longer is."""
    old, new = before.get(key), after.get(key)
    if not isinstance(new, dict):
        return False
    old = old if isinstance(old, dict) else {}
    return any(name not in old or (_off(old[name]) and not _off(new[name])) for name in new)


def _off(server: object) -> bool:
    """A disabled server: ``disabled: true`` (Claude) or ``enabled: false`` (OpenCode)."""
    return isinstance(server, dict) and (
        server.get("disabled") is True or server.get("enabled") is False
    )


# --- document access ----------------------------------------------------------------------


def _get(doc: object, path: tuple[str, ...]) -> object:
    node = doc
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return _ABSENT
        node = node[key]
    return node


def _changed(before: Doc, after: Doc, path: tuple[str, ...]) -> bool:
    return _get(before, path) != _get(after, path)


def _hashes(doc: Doc, pointer: str) -> set[str]:
    keys = tuple(p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:])
    array = _get(doc, keys)
    return {element_sha256(item) for item in array} if isinstance(array, list) else set()


def _strings(value: object) -> set[str]:
    return {item for item in value if isinstance(item, str)} if isinstance(value, list) else set()


def _keys(value: object) -> set[str]:
    return set(value) if isinstance(value, dict) else set()


def _enabled_keys(value: object) -> set[str]:
    return (
        {k for k, v in value.items() if v not in (False, None)}
        if isinstance(value, dict)
        else set()
    )


# --- JSONC --------------------------------------------------------------------------------


def _drop_comments(text: str) -> str:
    parts: list[str] = []
    index = 0
    while (found := _SPECIAL.search(text, index)) is not None:
        start = found.start()
        parts.append(text[index:start])
        if found.group() == '"':
            index = _string_end(text, start)
            parts.append(text[start:index])
        elif found.group() == "//":
            end = text.find("\n", start)
            index = len(text) if end < 0 else end
        else:
            end = text.find("*/", start + 2)
            index = len(text) if end < 0 else end + 2
            parts.append(" ")
    parts.append(text[index:])
    return "".join(parts)


def _drop_trailing_commas(text: str) -> str:
    parts: list[str] = []
    index = 0
    while (found := _STRING_OR_TRAILING_COMMA.search(text, index)) is not None:
        start = found.start()
        parts.append(text[index:start])
        if found.group() == '"':
            index = _string_end(text, start)
            parts.append(text[start:index])
        else:
            index = start + 1  # the comma itself is dropped
    parts.append(text[index:])
    return "".join(parts)


def _string_end(text: str, start: int) -> int:
    """The index just past the JSON string opening at ``start`` (escapes skipped)."""
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == '"':
            return index + 1
        index += 1
    return len(text)
