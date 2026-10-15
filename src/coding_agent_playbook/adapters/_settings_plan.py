"""Decide which managed elements of ``.claude/settings.json`` change (specs/prK-lifecycle-hooks.md §C.2.3-§C.2.5, §C.2.8).

The plan works on the parsed document only; :mod:`.claude_settings` turns it
into splices. Ownership comes from the prior lockfile alone: an element is
``owned`` when its canonical-JSON hash equals a prior scoped entry, and
``suspect`` when it carries no recorded hash but every handler runs the
playbook launcher. The launcher token never claims ownership silently; it
only classifies conflicts (§C.2.3). Stdlib-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook._canonical_json import canonical_json
from coding_agent_playbook.adapters._json_edits import ArrayEdit
from coding_agent_playbook.lockfile import LockEntry, compute_hash

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from coding_agent_playbook.adapters._json_spans import PathStep

__all__ = [
    "CLAUDE_SETTINGS_PATH",
    "LAUNCHER_TOKEN",
    "MANAGED_STRING_POINTERS",
    "DesiredGroup",
    "SettingsPlan",
    "SettingsShapeError",
    "canonical_json",
    "json_pointer",
    "launcher_kind",
    "plan_settings",
    "pointer_keys",
    "scoped_lock_entry",
]

CLAUDE_SETTINGS_PATH: Final = ".claude/settings.json"
#: The secondary ownership signal inside a handler ``command`` (§C.2.3).
LAUNCHER_TOKEN: Final = "/.claude/hooks/playbook/launch.sh"
#: The string arrays the engine may manage, one lock entry per string (§C.2.4 step 6, E-Q2).
MANAGED_STRING_POINTERS: Final = (
    "/permissions/allow",
    "/permissions/deny",
    "/sandbox/filesystem/denyRead",
    "/sandbox/network/allowedDomains",
)
_ADAPTER: Final = "claude_code"
_RESTORE_HINT: Final = "Change hooks in playbook/hooks/ or [hooks], then run 'playbook sync'."


class SettingsShapeError(ValueError):
    """A value at ``path`` (object keys and array indexes) that the merge cannot work on."""

    def __init__(self, path: Sequence[PathStep], message: str) -> None:
        super().__init__(message)
        self.path = tuple(path)
        self.message = message


@dataclass(frozen=True)
class DesiredGroup:
    """One managed matcher group the engine wants under ``hooks.<Event>``.

    Example::

        DesiredGroup("registration:stop", {"hooks": [{"type": "command", ...}]})
    """

    artifact_id: str
    group: Mapping[str, Any]


@dataclass
class SettingsPlan:
    """What the merge will do: array edits, ownership records and user-facing lines."""

    edits: list[ArrayEdit] = field(default_factory=list)
    entries: list[LockEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    updated: int = 0
    removed: int = 0


def json_pointer(keys: Iterable[str]) -> str:
    """RFC 6901 pointer for object ``keys`` (``~`` and ``/`` escaped).

    Example::

        >>> json_pointer(["hooks", "PreToolUse"])
        '/hooks/PreToolUse'
    """
    return "".join("/" + key.replace("~", "~0").replace("/", "~1") for key in keys)


def pointer_keys(pointer: str) -> tuple[str, ...]:
    """The object keys of an RFC 6901 ``pointer`` (the inverse of :func:`json_pointer`).

    Example::

        >>> pointer_keys("/permissions/allow")
        ('permissions', 'allow')
    """
    return tuple(p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:])


def scoped_lock_entry(
    path: str, pointer: str, element: object, *, artifact_id: str, adapter: str = _ADAPTER
) -> LockEntry:
    """The ownership record of one managed ``element`` of the array at ``pointer``.

    Example::

        scoped_lock_entry(".claude/settings.json", "/hooks/Stop", group,
                          artifact_id="registration:stop")
    """
    data = canonical_json(element)
    return LockEntry(
        path=path,
        sha256=compute_hash(data),
        bytes=len(data),
        kind="runtime",
        artifact_id=artifact_id,
        adapter=adapter,
        scope=f"json:{pointer}",
    )


def plan_settings(
    doc: object,
    desired: Mapping[str, Sequence[DesiredGroup]],
    prior: Iterable[LockEntry],
    strings: Mapping[str, Sequence[str]],
    *,
    path: str,
) -> SettingsPlan:
    """Plan every managed hook group and managed string of ``doc`` (§C.2.4 steps 3-4).

    ``desired`` maps Claude event names to the groups wanted there, in the
    order new event keys should be appended; ``strings`` maps managed pointers
    to wanted strings. Anything absent is unwanted, so its owned elements go.
    Raises :class:`SettingsShapeError` for a wrong shape (``doc`` must be an
    object) or a mixed group.

    Example::

        plan_settings(doc, {"Stop": [DesiredGroup("registration:stop", group)]}, lock.entries, {},
                      path=".claude/settings.json")
    """
    unknown = sorted(set(strings) - set(MANAGED_STRING_POINTERS))
    if unknown:
        raise ValueError(f"unmanaged pointers {unknown}; expected one of {MANAGED_STRING_POINTERS}")
    if not isinstance(doc, dict):
        raise SettingsShapeError(
            (), f"the top level must be a JSON object (Claude Code settings), got {_describe(doc)}"
        )
    scoped = [e for e in prior if e.path == path and e.scope.startswith("json:")]
    plan = SettingsPlan()
    hooks = _hook_events(doc)
    for event in [*hooks, *(e for e in desired if e not in hooks)]:
        _plan_event(plan, event, hooks.get(event, []), desired.get(event, ()), scoped, path)
    plan.entries = _registration_entries(desired, path)
    for pointer in MANAGED_STRING_POINTERS:
        _plan_strings(plan, doc, pointer, strings.get(pointer, ()), scoped, path)
    return plan


def _registration_entries(
    desired: Mapping[str, Sequence[DesiredGroup]], path: str
) -> list[LockEntry]:
    """One scoped entry per desired group, no-op ones included (§C.2.4 step 9)."""
    return [
        scoped_lock_entry(
            path, json_pointer(("hooks", event)), want.group, artifact_id=want.artifact_id
        )
        for event, wants in desired.items()
        for want in wants
    ]


def _describe(value: object) -> str:
    """``<json type> <compact JSON preview>`` for error messages."""
    kinds = {dict: "object", list: "array", str: "string", bool: "boolean", type(None): "null"}
    preview = json.dumps(value, ensure_ascii=False)
    preview = preview if len(preview) <= 60 else preview[:57] + "..."
    return f"{kinds.get(type(value), 'number')} {preview}"


def _hook_events(doc: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """``doc["hooks"]`` checked to be an object of arrays of objects (§C.2.4 step 2)."""
    hooks = doc.get("hooks", {})
    if not isinstance(hooks, dict):
        raise SettingsShapeError(
            ("hooks",),
            f"hooks must be an object mapping event names to arrays of matcher groups, "
            f"got {_describe(hooks)}",
        )
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise SettingsShapeError(
                ("hooks", event),
                f"hooks.{event} must be an array of matcher-group objects, got {_describe(groups)}",
            )
        for i, group in enumerate(groups):
            if not isinstance(group, dict):
                raise SettingsShapeError(
                    ("hooks", event, i),
                    f"hooks.{event}[{i}] must be a matcher-group object, got {_describe(group)}",
                )
    return hooks


@dataclass(frozen=True)
class _Found:
    """An owned or suspect element of one event array."""

    index: int
    key: bytes
    suspect: bool


def launcher_kind(group: Mapping[str, Any]) -> Literal["user", "suspect", "mixed"]:
    """``suspect`` when every handler runs the playbook launcher, ``mixed`` when only some do.

    Example: ``launcher_kind({"hooks": [{"command": "./mine.sh"}]}) == "user"``.
    """
    handlers = group.get("hooks")
    if not isinstance(handlers, list) or not handlers:
        return "user"
    flags = [
        isinstance(h, dict) and isinstance(h.get("command"), str) and LAUNCHER_TOKEN in h["command"]
        for h in handlers
    ]
    if all(flags):
        return "suspect"
    return "mixed" if any(flags) else "user"


def _classify(event: str, groups: list[dict[str, Any]], owned: set[str]) -> list[_Found]:
    """The owned and suspect elements of ``hooks[event]``, in array order."""
    found: list[_Found] = []
    for i, group in enumerate(groups):
        key = canonical_json(group)
        if compute_hash(key) in owned:
            found.append(_Found(i, key, suspect=False))
            continue
        kind = launcher_kind(group)
        if kind == "mixed":
            raise SettingsShapeError(
                ("hooks", event, i),
                f"hooks.{event}[{i}] mixes the playbook launcher with other handlers; "
                "move your handler to its own matcher group",
            )
        if kind == "suspect":
            found.append(_Found(i, key, suspect=True))
    return found


def _plan_event(
    plan: SettingsPlan,
    event: str,
    groups: list[dict[str, Any]],
    wants: Sequence[DesiredGroup],
    scoped: list[LockEntry],
    path: str,
) -> None:
    """Apply the §C.2.4 step-4 decision table to one event array."""
    scope = "json:" + json_pointer(("hooks", event))
    recorded = [e for e in scoped if e.scope == scope]
    decision = _decide(_classify(event, groups, {e.sha256 for e in recorded}), wants)
    _report(plan, f"{path} hooks.{event}", decision, recorded)
    plan.edits.append(
        ArrayEdit(
            ("hooks", event),
            delete=decision.delete,
            replace=decision.replace,
            append=tuple(w.group for w in decision.append),
        )
    )
    plan.updated += len(decision.replace) + len(decision.append)
    plan.removed += len(decision.delete)


@dataclass(frozen=True)
class _EventDecision:
    """The decision-table outcome for one event array."""

    replace: dict[int, Mapping[str, Any]]
    append: list[DesiredGroup]
    delete: frozenset[int]
    copies: int
    restored_suspect: bool


def _decide(found: list[_Found], wants: Sequence[DesiredGroup]) -> _EventDecision:
    """Keep equal elements, reuse stale ones in place for changed wants, append the rest.

    A leftover equal to a kept want is a duplicate copy; other leftovers are
    stale and are replaced in array order, or deleted when no want is left.
    """
    want_keys = [canonical_json(w.group) for w in wants]
    matched = _match_equal(found, want_keys)
    leftover = [f for f in found if f.index not in matched.values()]
    copies = [f for f in leftover if f.key in want_keys]
    stale = [f for f in leftover if f.key not in want_keys]
    unmatched = [w for w in range(len(wants)) if w not in matched]
    reused = stale[: len(unmatched)]
    return _EventDecision(
        replace={f.index: wants[w].group for f, w in zip(reused, unmatched, strict=False)},
        append=[wants[w] for w in unmatched[len(reused) :]],
        delete=frozenset(f.index for f in [*copies, *stale[len(reused) :]]),
        copies=len(copies),
        restored_suspect=any(f.suspect for f in reused),
    )


def _report(
    plan: SettingsPlan, where: str, decision: _EventDecision, recorded: list[LockEntry]
) -> None:
    """The §C.1.5 lines: duplicates and hand edits warn, a re-added group is a note.

    A suspect restored without any prior entry for the event is not reported:
    with a gitignored lockfile it is most likely a teammate's older render.
    """
    if decision.copies:
        noun = "copy" if decision.copies == 1 else "copies"
        plan.warnings.append(
            f"{where}: removed {decision.copies} duplicate {noun} of a managed entry."
        )
    if recorded and decision.restored_suspect:
        plan.warnings.append(
            f"{where}: managed entry was edited by hand; restored. {_RESTORE_HINT}"
        )
    recorded_ids = {e.artifact_id for e in recorded}
    plan.notes.extend(
        f"{where}: managed entry was missing; re-added. {_RESTORE_HINT}"
        for want in decision.append
        if want.artifact_id in recorded_ids
    )


def _match_equal(found: list[_Found], want_keys: list[bytes]) -> dict[int, int]:
    """Pair each wanted group with the first unpaired element canonically equal to it."""
    matched: dict[int, int] = {}
    for w, key in enumerate(want_keys):
        hit = next((f for f in found if f.key == key and f.index not in matched.values()), None)
        if hit is not None:
            matched[w] = hit.index
    return matched


def _plan_strings(
    plan: SettingsPlan,
    doc: Mapping[str, Any],
    pointer: str,
    wanted: Sequence[str],
    scoped: list[LockEntry],
    path: str,
) -> None:
    """The generic managed string-array operation at ``pointer`` (§C.2.4 step 6, §C.2.8).

    A wanted string the user already wrote is left to the user: neither
    duplicated nor claimed, so disabling its guard never deletes a user entry.
    """
    scope = f"json:{pointer}"
    ours = {e.sha256 for e in scoped if e.scope == scope}
    if not wanted and not ours:
        return  # never inspect (or reject) an array the engine has no stake in
    keys = pointer_keys(pointer)
    unique = list(dict.fromkeys(wanted))
    delete, present = _strings_to_delete(_string_array(doc, keys), unique, ours)
    append = tuple(s for s in unique if s not in present)
    claimed = [s for s in unique if s in append or compute_hash(canonical_json(s)) in ours]
    plan.edits.append(ArrayEdit(keys, delete=delete, append=append))
    plan.entries.extend(
        scoped_lock_entry(path, pointer, s, artifact_id=f"permission:{keys[-1]}:{s}")
        for s in claimed
    )
    plan.updated += len(append)
    plan.removed += len(delete)


def _strings_to_delete(
    current: list[Any], wanted: list[str], ours: set[str]
) -> tuple[frozenset[int], set[str]]:
    """Indexes of our strings that are unwanted or repeated, and every string present.

    Non-string elements and strings the lock does not record are the user's.
    """
    present: set[str] = set()
    delete: set[int] = set()
    for i, item in enumerate(current):
        if not isinstance(item, str):
            continue
        mine = compute_hash(canonical_json(item)) in ours
        if mine and (item not in wanted or item in present):
            delete.add(i)
        present.add(item)
    return frozenset(delete), present


def _string_array(doc: Mapping[str, Any], keys: tuple[str, ...]) -> list[Any]:
    """The array at ``keys``, ``[]`` when absent; raises for a parent or leaf of the wrong shape."""
    node: Any = doc
    for depth, key in enumerate(keys):
        if key not in node:
            return []
        node = node[key]
        dotted = ".".join(keys[: depth + 1])
        is_leaf = depth == len(keys) - 1
        if is_leaf and not isinstance(node, list):
            raise SettingsShapeError(
                keys, f"{dotted} must be an array of strings, got {_describe(node)}"
            )
        if not is_leaf and not isinstance(node, dict):
            raise SettingsShapeError(
                keys[: depth + 1], f"{dotted} must be an object, got {_describe(node)}"
            )
    result: list[Any] = node
    return result
