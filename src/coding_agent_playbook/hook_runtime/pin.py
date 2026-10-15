"""The per-worktree interpreter pin and per-machine tool pins (specs/prK-lifecycle-hooks.md §C.2.7, §D.8.3).

The committed launcher is identical on every machine, so the absolute
interpreter it runs comes from ``<git_dir>/playbook-hooks/interpreter``, and
absolute tool paths come from ``machine.json`` beside it; neither is ever in
a committed file (D-13). Sync, ``doctor --repin`` and the Stop stage runner
use these helpers; they are jinja2-free and stdlib-only.

- The interpreter pin is ``sys.executable`` **unresolved**: a venv's
  ``bin/python`` is a symlink, and resolving it escapes the venv and its
  site-packages. The first writer wins, so the pin never flaps between a
  venv, pre-commit's cached env and ``uvx``; it is rewritten only when it no
  longer names an executable file (or on ``--repin``).
- A tool pin keeps ``[st_size, st_mtime_ns, st_ino]``: a stage whose tool no
  longer matches is skipped as ``tool_changed``, never reported green.
- Hooks are git-only in v1: outside git there is no state root and no pin.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.paths import find_repo
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME, StateStore, StateUnavailable

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

__all__ = [
    "INTERPRETER_PIN",
    "MACHINE_PINS",
    "MachinePins",
    "PinResult",
    "ToolPin",
    "ensure_interpreter_pin",
    "is_ephemeral",
    "read_interpreter_pin",
    "read_machine_pins",
    "tool_signature",
    "write_machine_pins",
]

INTERPRETER_PIN: Final = "interpreter"
MACHINE_PINS: Final = "machine.json"
MACHINE_PINS_SCHEMA: Final = 1
#: uv's cached tool envs (``uvx``) and pipx's ``run`` envs are deleted at will.
_EPHEMERAL = re.compile(r"/archive-v\d+/|/pipx/\.cache/")

type Signature = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class PinResult:
    """What :func:`ensure_interpreter_pin` left in place, and whether it wrote it."""

    path: Path
    interpreter: str
    written: bool
    ephemeral: bool


@dataclass(frozen=True, slots=True)
class ToolPin:
    """One tool's argv as sync resolved it, and its program's stat signature."""

    argv: tuple[str, ...]
    sig: Signature | None

    def unchanged(self) -> bool:
        """Whether the program still has the signature sync recorded."""
        return self.sig is not None and tool_signature(self.argv[0]) == self.sig


@dataclass(frozen=True, slots=True)
class MachinePins:
    """The parsed ``machine.json``."""

    engine_version: str
    tools: Mapping[str, ToolPin]
    resource_roots: Mapping[str, str]

    def tool(self, name: str) -> ToolPin | None:
        """The pin of logical tool ``name``, or ``None`` when sync recorded none."""
        return self.tools.get(name)


def tool_signature(path: str) -> Signature | None:
    """``(st_size, st_mtime_ns, st_ino)`` of ``path`` (symlinks followed), or ``None``.

    Example::

        >>> tool_signature("/no/such/tool") is None
        True
    """
    try:
        info = os.stat(path)
    except OSError:
        return None
    return (info.st_size, info.st_mtime_ns, info.st_ino)


def is_ephemeral(executable: str) -> bool:
    """Whether ``executable`` lives in a cache that uv or pipx may delete at any time.

    Example::

        >>> is_ephemeral("/home/u/.cache/uv/archive-v0/x/bin/python")
        True
    """
    return _EPHEMERAL.search(executable.replace("\\", "/")) is not None


def ensure_interpreter_pin(
    *,
    git_dir: str | None = None,
    start: str = ".",
    executable: str | None = None,
    force: bool = False,
) -> PinResult | None:
    """Pin ``executable`` (default ``sys.executable``) unless a usable pin exists.

    ``git_dir`` defaults to the repository found from ``start``; ``force``
    overwrites (``doctor --repin``). ``None`` outside git or when the state
    root is unusable.

    Example::

        >>> ensure_interpreter_pin(start=str(repo_root)).written  # doctest: +SKIP
        True
    """
    store = _store(git_dir, start)
    if store is None:
        return None
    current = _read_pin(store)
    if current is not None and not force and _is_executable(current):
        return PinResult(store.path(INTERPRETER_PIN), current, False, is_ephemeral(current))
    interpreter = sys.executable if executable is None else executable
    try:
        store.replace_bytes(INTERPRETER_PIN, f"{interpreter}\n".encode())
    except StateUnavailable:
        return None
    return PinResult(store.path(INTERPRETER_PIN), interpreter, True, is_ephemeral(interpreter))


def read_interpreter_pin(*, git_dir: str | None = None, start: str = ".") -> str | None:
    """The pinned interpreter path, or ``None`` when there is none.

    Example::

        >>> read_interpreter_pin(start=str(repo_root))  # doctest: +SKIP
        '/repo/.venv/bin/python'
    """
    store = _store(git_dir, start)
    return None if store is None else _read_pin(store)


def write_machine_pins(
    *,
    tools: Mapping[str, Sequence[str]],
    engine_version: str,
    resource_roots: Mapping[str, str] | None = None,
    git_dir: str | None = None,
    start: str = ".",
) -> Path | None:
    """Rewrite ``machine.json`` with each tool's argv and its program's signature.

    Example::

        >>> write_machine_pins(tools={"ruff": ["/v/bin/ruff"]}, engine_version="0.1")  # doctest: +SKIP
        PosixPath('/repo/.git/playbook-hooks/machine.json')
    """
    store = _store(git_dir, start)
    if store is None:
        return None
    document = {
        "schema_version": MACHINE_PINS_SCHEMA,
        "engine_version": engine_version,
        "tools": {name: _tool_entry(argv) for name, argv in tools.items()},
        "resource_roots": dict(resource_roots or {}),
    }
    try:
        store.write_json(MACHINE_PINS, document)
    except StateUnavailable:
        return None
    return store.path(MACHINE_PINS)


def read_machine_pins(*, git_dir: str | None = None, start: str = ".") -> MachinePins | None:
    """The parsed ``machine.json``, or ``None`` when absent, unusable or malformed.

    Example::

        >>> read_machine_pins(start=str(repo_root)).tool("ruff").unchanged()  # doctest: +SKIP
        True
    """
    store = _store(git_dir, start)
    if store is None:
        return None
    try:
        document = store.read_json(MACHINE_PINS)
    except StateUnavailable:
        return None
    return _parse_pins(document)


def _store(git_dir: str | None, start: str) -> StateStore | None:
    if git_dir is None:
        repo = find_repo(start)
        if repo is None:
            return None
        git_dir = repo.git_dir
    store = StateStore(os.path.join(git_dir, STATE_DIR_NAME))
    return store if store.usable else None


def _read_pin(store: StateStore) -> str | None:
    try:
        data = store.read_bytes(INTERPRETER_PIN, limit=4096)
    except StateUnavailable:
        return None
    lines = (data or b"").decode("utf-8", errors="replace").splitlines()
    first = lines[0].strip() if lines else ""
    return first or None


def _is_executable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _tool_entry(argv: Sequence[str]) -> dict[str, Any]:
    sig = tool_signature(argv[0]) if argv else None
    return {"argv": list(argv), "sig": None if sig is None else list(sig)}


def _parse_pins(document: dict[str, Any]) -> MachinePins | None:
    tools, roots = document.get("tools"), document.get("resource_roots", {})
    if not isinstance(tools, dict) or not isinstance(roots, dict):
        return None
    parsed = {name: _tool_pin(entry) for name, entry in tools.items()}
    if any(pin is None for pin in parsed.values()):
        return None
    return MachinePins(
        engine_version=str(document.get("engine_version", "")),
        tools=MappingProxyType({name: pin for name, pin in parsed.items() if pin is not None}),
        resource_roots=MappingProxyType({str(k): str(v) for k, v in roots.items()}),
    )


def _tool_pin(entry: object) -> ToolPin | None:
    if not isinstance(entry, dict):
        return None
    argv = entry.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return None
    return ToolPin(tuple(argv), _signature_of(entry.get("sig")))


def _signature_of(value: object) -> Signature | None:
    """A stored ``[size, mtime_ns, ino]``; anything else counts as no signature (never green)."""
    if isinstance(value, list) and len(value) == 3 and all(type(n) is int for n in value):
        return (value[0], value[1], value[2])
    return None
