"""secrets-path-guard's native twin in ``.claude/settings.json`` (specs/prK-hook-pack.md §E.4).

While the guard is on, Claude Code also gets the deny rows it enforces
itself, which hold when the hook interpreter is missing or times out (a
hook then fails open): ``permissions.deny`` ``Read(...)`` / ``Edit(...)`` rows
from the same globs and exemptions, and ``sandbox.filesystem.denyRead`` for
the ``~/`` credential stores (binding sandboxed Bash only, so a speed bump
unless a managed setting enforces the sandbox).

Rows are gitignore patterns, last match wins: ``**/<glob>`` for a basename
glob, ``~/...`` as is, ``./<glob>`` for a repo-anchored one, and exemptions
as ``!`` negations. Each scoped exemption follows its own glob directly and
precedes every other glob, and the global exemptions come last, so
``.env.credentials.py`` (spared by ``!**/*credentials*.py``) is denied again by
``**/.env*``. The rows go through K3's managed-array merge: one lock entry per
string, user entries untouched, ours removed when the guard is turned off.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.security.patterns import (
    SECRET_GLOB_EXEMPT,
    SECRET_PATH_EXEMPT,
    SECRET_PATH_GLOBS,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.hook_policy import ResolvedHook

__all__ = [
    "DENY_POINTER",
    "DENY_READ_POINTER",
    "SECRETS_PATH_GUARD",
    "gitignore_patterns",
    "secret_native_rows",
]

SECRETS_PATH_GUARD: Final = "secrets-path-guard"
DENY_POINTER: Final = "/permissions/deny"
DENY_READ_POINTER: Final = "/sandbox/filesystem/denyRead"
_TOOLS: Final = ("Read", "Edit")
_HOME: Final = "~/"
_ANY_BELOW: Final = "/**"


def secret_native_rows(hooks: Iterable[ResolvedHook]) -> dict[str, tuple[str, ...]]:
    """The managed strings per pointer while secrets-path-guard is on, else ``{}``.

    Example::

        >>> secret_native_rows([])
        {}
    """
    hook = next((h for h in hooks if h.id == SECRETS_PATH_GUARD), None)
    handler = None if hook is None else hook.handlers.get("pre_tool_use")
    if handler is None:
        return {}
    deny = _unique([*SECRET_PATH_GLOBS, *_strings(handler.config.get("extra_globs"))])
    allow = _unique([*SECRET_PATH_EXEMPT, *_strings(handler.config.get("allow_paths"))])
    patterns = gitignore_patterns(deny, allow, SECRET_GLOB_EXEMPT)
    rows = tuple(f"{tool}({pattern})" for tool in _TOOLS for pattern in patterns)
    deny_read = _unique(_sandbox_path(glob) for glob in deny if glob.startswith(_HOME))
    return {DENY_POINTER: rows, DENY_READ_POINTER: deny_read}


def gitignore_patterns(
    deny: Iterable[str], allow: Iterable[str], scoped: Mapping[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """The deny globs and ``!`` exemptions in last-match-wins order (module docstring).

    Example::

        >>> gitignore_patterns([".env*", "*credentials*"], [".env.example"],
        ...                    {"*credentials*": ("*credentials*.py",)})
        ('**/*credentials*', '!**/*credentials*.py', '**/.env*', '!**/.env.example')
    """
    globs = list(deny)
    first = [glob for glob in globs if glob in scoped]
    ordered: list[str] = []
    for glob in first:
        ordered += [_pattern(glob), *(f"!{_pattern(e)}" for e in scoped[glob])]
    ordered += [_pattern(glob) for glob in globs if glob not in scoped]
    ordered += [f"!{_pattern(glob)}" for glob in allow]
    return _unique(ordered)


def _pattern(glob: str) -> str:
    """One catalog glob in gitignore syntax, anchored as ``security.paths`` reads it."""
    if glob.startswith(_HOME):
        return glob
    if "/" not in glob:
        return f"**/{glob}"
    return f"/{glob}" if glob.startswith("/") else f"./{glob}"


def _sandbox_path(glob: str) -> str:
    """A ``~/`` glob as a sandbox path: a credential directory stands for its contents."""
    return glob[: -len(_ANY_BELOW)] if glob.endswith(_ANY_BELOW) else glob


def _strings(value: object) -> list[str]:
    return (
        [item for item in value if isinstance(item, str) and item]
        if isinstance(value, list)
        else []
    )


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))
