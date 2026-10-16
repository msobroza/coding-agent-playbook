"""gate_scan's file-level rules: loosened checker config and removed gates (specs/prK-hook-pack.md §E.2).

Split from ``gate_scan`` for its size budget; pure, and ``tomllib`` / ``shlex``
load inside the functions that need them, so importing this module stays as
cheap as ``re`` (the Stop stage imports it on every scanned stop).

- **TOML key diffs** (:func:`toml_loosenings`): each protected dotted key is
  compared before and after. Keys with a known direction loosen only one way
  (``strict`` switched off, ``ignore`` grown, ``select`` shrunk, a lower
  ``--cov-fail-under``); any other change is of unknown direction and counts as
  loosening. A table that did not exist before cannot be loosened: adopting
  commitizen or mypy is never flagged.
- **Removals** (:func:`removal_weakenings`): a pre-commit hook ``id`` or a
  workflow step a diff removes without re-adding in the same file, and any
  change to ``.gitleaks.toml``.

Each rule yields a :class:`FileWeakening`; ``gate_scan`` decides justification
from the ``tokens`` a justifying added line must mention.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

__all__ = ["TOML_PREFIXES", "FileWeakening", "removal_weakenings", "toml_loosenings"]

#: The TOML config files scanned, and the prefix a protected key loses in each.
TOML_PREFIXES: Final[Mapping[str, str]] = MappingProxyType(
    {"pyproject.toml": "", "ruff.toml": "tool.ruff.", ".ruff.toml": "tool.ruff."}
)
_PRECOMMIT: Final = ".pre-commit-config.yaml"
_GITLEAKS: Final = ".gitleaks.toml"
_WORKFLOW = re.compile(r"(?:.*/)?\.github/workflows/[^/]+\.ya?ml")
_HOOK_ID = re.compile(r"""^[ \t]*(?:-[ \t]+)?id:[ \t]*["']?([A-Za-z0-9_.-]+)""")
_STEP = re.compile(r"""^[ \t]*-[ \t]+(?:name|uses|run):[ \t]*["']?(.*?)["']?[ \t]*(?:#.*)?$""")
#: Added pytest options that switch tests or their checks off.
_WEAK_OPTS: Final = (
    "--ignore",
    "--deselect",
    "--no-cov",
    "--continue-on-collection",
    "no:",
    "-pno:",
)
#: Dropped pytest options that were enforcing something.
_GUARD_OPTS: Final = ("--strict", "--cov")
_FAIL_UNDER: Final = "--cov-fail-under"
_ABSENT: Final = object()
_VALUE_CHARS: Final = 60


@dataclass(frozen=True, slots=True)
class FileWeakening:
    """One file-level gate weakening: where, which rule, what, and what a reason must name.

    Example: ``FileWeakening(".gitleaks.toml", "gitleaks-config-changed", "...", ())``.
    """

    path: str
    rule: str
    detail: str
    tokens: tuple[str, ...]


# --- TOML key diffs ----------------------------------------------------------------------------


def toml_loosenings(
    path: str, before: str | None, after: str | None, keys: Iterable[str]
) -> list[FileWeakening]:
    """The protected ``keys`` a change of TOML file ``path`` loosens.

    Example::

        >>> [w.detail for w in toml_loosenings("pyproject.toml", "[tool.mypy]\\nstrict = true\\n",
        ...                                    "[tool.mypy]\\n", ["tool.mypy.strict"])]
        ['[tool.mypy] strict: true → (absent)']
    """
    old, new = _parse(before), _parse(after)
    if old is None:  # unparseable before: nothing was enforced through it
        return []
    if new is None:
        return [FileWeakening(path, "config-loosening", f"{_name(path)} no longer parses", ())]
    prefix = TOML_PREFIXES[_name(path)]
    found = (_key_loosening(path, key, old, new, prefix) for key in keys)
    return [weakening for weakening in found if weakening is not None]


def _key_loosening(
    path: str, key: str, old: Mapping[str, object], new: Mapping[str, object], prefix: str
) -> FileWeakening | None:
    if not key.startswith(prefix):
        return None
    parts = tuple(key[len(prefix) :].split("."))
    if not isinstance(_get(old, parts[:-1]), dict):  # a new table loosens nothing
        return None
    was, now = _get(old, parts), _get(new, parts)
    if was == now:
        return None
    detail = _DIRECTIONS.get(parts[-1], _any_change)(was, now)
    if detail is None:
        return None
    table, _, leaf = key.rpartition(".")
    tokens = (leaf, *sorted(_items(was) ^ _items(now)))
    return FileWeakening(path, "config-loosening", f"[{table}] {leaf}: {detail}", tokens)


def _parse(text: str | None) -> dict[str, object] | None:
    import tomllib  # only a scanned config change pays for it

    if text is None:
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None


def _true_is_strict(was: object, now: object) -> str | None:
    return _arrow(was, now) if was is True and now is not True else None


def _true_is_loose(was: object, now: object) -> str | None:
    return _arrow(was, now) if now is True and was is not True else None


def _growth_is_loose(was: object, now: object) -> str | None:
    added = _items(now) - _items(was)
    return f"adds {_joined(added)}" if added else None


def _shrink_is_loose(was: object, now: object) -> str | None:
    dropped = _items(was) - _items(now)
    return f"drops {_joined(dropped)}" if dropped else None


def _filterwarnings(was: object, now: object) -> str | None:
    dropped = _items(was) - _items(now)
    relaxed = {item for item in _items(now) - _items(was) if not item.startswith("error")}
    return _parts(("drops", dropped), ("adds", relaxed))


def _addopts(was: object, now: object) -> str | None:
    old, new = _options(was), _options(now)
    floor = _fail_under_change(_fail_under(old), _fail_under(new))
    dropped = {o for o in set(old) - set(new) if o.startswith(_GUARD_OPTS) and _FAIL_UNDER not in o}
    weak = {o for o in set(new) - set(old) if o.startswith(_WEAK_OPTS)}
    rest = _parts(("drops", dropped), ("adds", weak))
    return "; ".join(part for part in (floor, rest) if part) or None


def _any_change(was: object, now: object) -> str | None:
    return _arrow(was, now)


#: How a protected key loosens, by its last name; anything else: any change does.
_DIRECTIONS: Final[Mapping[str, Callable[[object, object], str | None]]] = MappingProxyType(
    {
        "strict": _true_is_strict,
        "xfail_strict": _true_is_strict,
        "ignore_missing_imports": _true_is_loose,
        "exclude": _growth_is_loose,
        "ignore": _growth_is_loose,
        "extend-ignore": _growth_is_loose,
        "allowed_prefixes": _growth_is_loose,
        "select": _shrink_is_loose,
        "extend-select": _shrink_is_loose,
        "filterwarnings": _filterwarnings,
        "addopts": _addopts,
    }
)


def _options(value: object) -> list[str]:
    """pytest ``addopts`` as tokens, ``--cov-fail-under N`` joined into one."""
    import shlex  # only an addopts change pays for it

    raw: list[object] = []
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list):
        raw = list(value)
    tokens = [token for item in raw for token in shlex.split(str(item))]
    joined: list[str] = []
    for token in tokens:
        if joined and joined[-1] == _FAIL_UNDER:
            joined[-1] = f"{_FAIL_UNDER}={token}"
        else:
            joined.append(token)
    return joined


def _fail_under(options: Sequence[str]) -> float | None:
    for option in options:
        if option.startswith(f"{_FAIL_UNDER}="):
            try:
                return float(option.partition("=")[2])
            except ValueError:
                return None
    return None


def _fail_under_change(was: float | None, now: float | None) -> str | None:
    if was is None or (now is not None and now >= was):
        return None
    return f"{_FAIL_UNDER} {was:g} → {'(absent)' if now is None else f'{now:g}'}"


# --- removals ----------------------------------------------------------------------------------


def removal_weakenings(
    added: Mapping[str, Sequence[str]], removed: Mapping[str, Sequence[str]]
) -> list[FileWeakening]:
    """Removed pre-commit hooks and workflow steps, and ``.gitleaks.toml`` changes.

    ``added`` and ``removed`` map each path to its added / removed line texts.

    Example::

        >>> [w.rule for w in removal_weakenings({}, {".pre-commit-config.yaml": ["- id: mypy"]})]
        ['precommit-hook-removed']
    """
    found: list[FileWeakening] = []
    for path in sorted(removed):
        name = _name(path)
        if name == _PRECOMMIT:
            found += _lost(path, _HOOK_ID, added.get(path, ()), removed[path], "precommit-hook")
        elif _WORKFLOW.fullmatch(path):
            found += _lost(path, _STEP, added.get(path, ()), removed[path], "workflow-step")
    for path in sorted({*added, *removed}):
        if _name(path) == _GITLEAKS:
            found.append(FileWeakening(path, "gitleaks-config-changed", f"{_GITLEAKS} changed", ()))
    return found


def _lost(
    path: str, pattern: re.Pattern[str], added: Sequence[str], removed: Sequence[str], what: str
) -> list[FileWeakening]:
    gone = _matches(pattern, removed) - _matches(pattern, added)
    noun = what.replace("-", " ")
    return [
        FileWeakening(path, f"{what}-removed", f"{noun} {name!r} removed", (name,))
        for name in sorted(gone)
    ]


def _matches(pattern: re.Pattern[str], lines: Iterable[str]) -> Counter[str]:
    return Counter(match[1] for line in lines if (match := pattern.match(line)) and match[1])


# --- shared ------------------------------------------------------------------------------------


def _name(path: str) -> str:
    return path.rpartition("/")[2]


def _get(doc: object, parts: Sequence[str]) -> object:
    node = doc
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return _ABSENT
        node = node[part]
    return node


def _items(value: object) -> set[str]:
    if value is _ABSENT:
        return set()
    if isinstance(value, list):
        return {str(item) for item in value}
    return {value} if isinstance(value, str) else {_shown(value)}


def _arrow(was: object, now: object) -> str:
    return f"{_shown(was)} → {_shown(now)}"


def _shown(value: object) -> str:
    if value is _ABSENT:
        return "(absent)"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = f'"{value}"' if isinstance(value, str) else repr(value)
    return text if len(text) <= _VALUE_CHARS else text[: _VALUE_CHARS - 1] + "…"


def _joined(items: Iterable[str]) -> str:
    return ", ".join(sorted(items))


def _parts(*pairs: tuple[str, set[str]]) -> str | None:
    text = "; ".join(f"{verb} {_joined(items)}" for verb, items in pairs if items)
    return text or None
