"""control-plane-guard's TOML key-path verdicts on the playbook config (specs/prK-hook-pack.md §E.1).

``.coding-agent-playbook.toml`` is compared key path by key path, parsed
before and after the edit:

- ``DENY``: any change under ``[hooks]`` (``[hooks.*]`` included, such as
  ``[hooks.commit_convention] cutover_date``) or ``[guardrails]``;
- ``ASK``: removals from ``overlays_enabled``, any ``framework`` (it enables a
  layer, like an ``overlays_enabled`` entry; D57), ``adapters_enabled``,
  ``detector_cache`` or ``[engine] version`` change, additions to
  ``[links] allowed_domains``, and ``[metrics]`` loosening. A ``[metrics]``
  change counts as loosening unless it is provably stricter (``mode =
  "both"``, ``fail_on_breach``/``strict`` switched on, a new threshold or a
  lower ``max_worsening``, fewer ``ignore``/``exclude`` entries, a wider
  ``select``): an unknown direction asks;
- ``NONE``: ``[project]`` and every other key.

``.coding-agent-playbook.local.toml`` is gitignored and deep-merged into the
config without a warning, so there any change to one of those key paths
denies. A file that does not parse, before or after, asks.

``tomllib`` is imported inside :func:`toml_verdict` only: it is the §D.1
branch-local row for a ``.toml`` policy edit, so an Edit of a ``.py`` file or a
plain Bash command never loads it. :data:`DEFAULT_POLICY_KEYS` is also the
key list the session-start briefing checks ``.local.toml`` against.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.config.schema import DEFAULT_POLICY_KEYS, PolicyKeys
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "local_policy_overrides",
    "metrics_loosened",
    "toml_verdict",
]

_ABSENT: Final = object()
type Path = tuple[str, ...]


def toml_verdict(
    before: str | None, after: str, *, local: bool, keys: PolicyKeys = DEFAULT_POLICY_KEYS
) -> Decision:
    """The verdict on an edit of the playbook config (``local``: the ``.local.toml``).

    Example::

        >>> toml_verdict("[hooks]\\nenabled = true\\n", "[hooks]\\n", local=False)
        <Decision.DENY: 'deny'>
    """
    import tomllib  # §D.1 branch-local row: only a .toml policy edit pays for it

    try:
        old = tomllib.loads(before) if before is not None else {}
        new = tomllib.loads(after)
    except tomllib.TOMLDecodeError:
        return Decision.ASK
    if local:
        changed = any(_get(old, _path(k)) != _get(new, _path(k)) for k in keys.every)
        return Decision.DENY if changed else Decision.NONE
    return _config_verdict(old, new, keys)


def local_policy_overrides(
    doc: Mapping[str, Any], keys: PolicyKeys = DEFAULT_POLICY_KEYS
) -> list[str]:
    """The policy key paths a parsed ``.local.toml`` sets, in row order.

    Example::

        >>> local_policy_overrides({"overlays_enabled": [], "project": {"name": "x"}})
        ['overlays_enabled']
    """
    return [key for key in keys.every if _get(doc, _path(key)) is not _ABSENT]


def metrics_loosened(before: object, after: object) -> bool:
    """Whether a ``[metrics]`` change may loosen a gate (an unknown direction does).

    Example::

        >>> metrics_loosened({"mode": "both"}, {"mode": "absolute"})
        True
    """
    if not all(value is _ABSENT or isinstance(value, dict) for value in (before, after)):
        return before != after  # a malformed [metrics]: any change is unknown
    old, new = _leaves(before), _leaves(after)
    for path in old.keys() | new.keys():
        was, now = old.get(path, _ABSENT), new.get(path, _ABSENT)
        if was != now and not _tightens(path, was, now):
            return True
    return False


def _config_verdict(old: Mapping[str, Any], new: Mapping[str, Any], keys: PolicyKeys) -> Decision:
    def changed(key: str) -> bool:
        return _get(old, _path(key)) != _get(new, _path(key))

    if any(changed(key) for key in keys.deny):
        return Decision.DENY
    asked = (
        any(changed(key) for key in keys.ask)
        or any(_items(old, key) - _items(new, key) for key in keys.ask_removals)
        or any(_items(new, key) - _items(old, key) for key in keys.ask_additions)
        or any(metrics_loosened(_get(old, _path(k)), _get(new, _path(k))) for k in keys.loosening)
    )
    return Decision.ASK if asked else Decision.NONE


def _tightens(path: Path, was: object, now: object) -> bool:
    """Whether changing ``path`` from ``was`` to ``now`` is provably stricter."""
    name = path[-1]
    if path == ("mode",):
        return now == "both"
    if path in (("fail_on_breach",), ("strict",)):
        return now is True
    if name == "max_worsening":
        return _number(now) is not None and (was is _ABSENT or _lower(now, was))
    if path[0] == "thresholds":
        return was is _ABSENT  # a new threshold only adds a gate
    if name in ("ignore", "exclude"):
        return isinstance(now, list) and set(map(str, now)) <= _str_set(was)
    if name == "select":
        return isinstance(now, list) and _str_set(was) <= set(map(str, now))
    return False


def _leaves(value: object, prefix: Path = ()) -> dict[Path, object]:
    """Every leaf of a TOML table by key path; an empty table is a leaf of its own."""
    if not isinstance(value, dict):
        return {prefix: value} if prefix else {}  # the root is a table or absent
    if not value and prefix:
        return {prefix: {}}
    found: dict[Path, object] = {}
    for key, item in value.items():
        found.update(_leaves(item, (*prefix, str(key))))
    return found


def _get(doc: object, path: Path) -> object:
    node = doc
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return _ABSENT
        node = node[key]
    return node


def _path(dotted: str) -> Path:
    return tuple(dotted.split("."))


def _items(doc: Mapping[str, Any], key: str) -> set[str]:
    return _str_set(_get(doc, _path(key)))


def _str_set(value: object) -> set[str]:
    if value is _ABSENT:
        return set()
    return set(map(str, value)) if isinstance(value, list) else {repr(value)}


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _lower(now: object, was: object) -> bool:
    new, old = _number(now), _number(was)
    return new is not None and old is not None and new < old
