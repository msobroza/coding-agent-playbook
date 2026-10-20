"""The ``ruff`` table of ``guard_config.json`` (specs/prK-hook-pack.md §E.3, OQ-37).

The committed half of the §E.3 post-edit pipeline's ruff tables (the per-machine
half is ``ruff_probe``, split by the machine-independence lock, §D.8.3): the
table comes **only** from the repo's own ruff config (``.ruff.toml`` >
``ruff.toml`` > ``pyproject.toml``'s ``[tool.ruff]``, ruff's precedence): the
project's explicit ``select`` / ``ignore`` and ``safe_fix_select`` = ``{I, UP}``
∩ that selection, the only rules post-edit-ruff-format may fix (no second style
source). Ruff's *default* selection is left implicit (``default_select``): it
changed in ruff 0.17, so listing it would make the committed file differ by
machine.

Config inheritance (``extend = "..."``) is not followed: a project that
inherits its selection gets no safe fixes, never wrong ones.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.ruff import intersect_selectors, selector_matches

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = [
    "RUFF_CONFIG_FILES",
    "SAFE_FIX_ALLOWLIST",
    "RuffSelection",
    "read_project_ruff_selection",
    "ruff_table",
]

#: The rules M1 may ever fix: import sorting and pyupgrade (§E.3).
SAFE_FIX_ALLOWLIST: Final = ("I", "UP")
#: Ruff's own precedence when one directory holds several config files.
RUFF_CONFIG_FILES: Final = (".ruff.toml", "ruff.toml", "pyproject.toml")
# --- the project's selection (guard_config.json) -------------------------------------------


@dataclass(frozen=True)
class RuffSelection:
    """The project's explicit ruff selection; ``default_select`` when it sets no ``select``.

    Example: ``RuffSelection(select=("E", "I"), ignore=("E501",), default_select=False)``.
    """

    select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    default_select: bool = True


def read_project_ruff_selection(repo_root: Path) -> RuffSelection:
    """The selection of the ruff config ruff itself would read at ``repo_root``.

    A ``pyproject.toml`` without ``[tool.ruff]`` is not a ruff config; an
    unreadable or malformed file counts as no config (ruff's defaults).

    Example::

        >>> read_project_ruff_selection(Path("/no/such/repo"))
        RuffSelection(select=(), ignore=(), default_select=True)
    """
    for name in RUFF_CONFIG_FILES:
        document = _load_toml(repo_root / name)
        table = _ruff_table_of(document, pyproject=name == "pyproject.toml")
        if table is not None:
            return _selection(table)
    return RuffSelection()


def _load_toml(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None


def _ruff_table_of(document: dict[str, Any] | None, *, pyproject: bool) -> dict[str, Any] | None:
    if document is None or not pyproject:
        return document
    tool = document.get("tool")
    ruff = tool.get("ruff") if isinstance(tool, dict) else None
    return ruff if isinstance(ruff, dict) else None


def _selection(table: dict[str, Any]) -> RuffSelection:
    """``[lint]`` keys first, the deprecated top-level ones as a fallback (ruff's own order)."""
    lint = table.get("lint")
    lint = lint if isinstance(lint, dict) else {}
    select = _strings(lint, "select") if "select" in lint else _strings(table, "select")
    explicit = "select" in lint or "select" in table
    extend = [*_strings(lint, "extend-select"), *_strings(table, "extend-select")]
    ignore = [
        *_strings(lint, "ignore"),
        *_strings(table, "ignore"),
        *_strings(lint, "extend-ignore"),
        *_strings(table, "extend-ignore"),
    ]
    return RuffSelection(
        select=tuple(sorted({*select, *extend})),
        ignore=tuple(sorted(set(ignore))),
        default_select=not explicit,
    )


def _strings(table: Mapping[str, Any], key: str) -> list[str]:
    value = table.get(key)
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def ruff_table(selection: RuffSelection) -> dict[str, Any]:
    """``guard_config.json``'s ``ruff`` table: machine-independent, from the repo alone.

    ``safe_fix_ignore`` re-applies the project's ignores inside the safe-fix
    prefixes, because M1's CLI ``--select`` resets the config's ``ignore``.

    Example::

        >>> ruff_table(RuffSelection(("E", "I", "UP"), ("UP007",), False))["safe_fix_select"]
        ['I', 'UP']
    """
    selected = intersect_selectors(SAFE_FIX_ALLOWLIST, selection.select)
    safe = [s for s in selected if not any(selector_matches(g, s) for g in selection.ignore)]
    safe_ignore = [g for g in selection.ignore if any(selector_matches(s, g) for s in safe)]
    return {
        "default_select": selection.default_select,
        "project_select": list(selection.select),
        "project_ignore": list(selection.ignore),
        "safe_fix_select": safe,
        "safe_fix_ignore": safe_ignore,
    }
