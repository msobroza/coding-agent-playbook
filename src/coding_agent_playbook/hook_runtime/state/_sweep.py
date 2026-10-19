"""The bounded TTL sweep of the state root (specs/prK-lifecycle-hooks.md §D.6.1).

It runs at ``session_start`` and lazily from ``stop`` once a day. SessionEnd
is not relied on: it is not portable and never fires on a crash. Each run
examines at most 500 entries in 20 ms and records a cursor, so a huge backlog
is cleared over several sessions without ever slowing one hook down. It
removes:

- ``sessions/*`` untouched for ``ttl_days`` (``[hooks] state_ttl_days``);
- ``tmp/*`` older than a day;
- ``stop/lint-baseline-<tree>.json`` for a tree other than ``HEAD^{tree}``,
  older than 7 days;
- ``decisions-YYYY-MM[.n].jsonl`` more than ``retain_months`` months old;
- ``checkpoints/*`` (precompact-checkpoint) untouched for ``ttl_days``, like
  the sessions they belong to.
"""

from __future__ import annotations

import os
import re
import stat
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

    from coding_agent_playbook.hook_runtime.state.store import StateStore

__all__ = ["SWEEP_DOC", "SweepReport", "sweep_due", "sweep_state"]

SWEEP_DOC: Final = "sweep.json"
SWEEP_MAX_ENTRIES: Final = 500
SWEEP_MAX_SECONDS: Final = 0.02
_DAY_S: Final = 86_400.0
_TMP_TTL_S: Final = _DAY_S
_BASELINE_TTL_S: Final = 7 * _DAY_S
_BASELINE = re.compile(r"lint-baseline-(?P<tree>[0-9a-f]+)\.json")
_DECISION_LOG = re.compile(r"decisions-(?P<year>[0-9]{4})-(?P<month>[0-9]{2})(?:\.[0-9]+)?\.jsonl")
#: The files whose mtime says a session is still in use.
_SESSION_FILES: Final = ("session.json", "ledger.jsonl", "stop.json")

type Position = tuple[int, str]


@dataclass(frozen=True, slots=True)
class SweepReport:
    """What one sweep did; ``complete`` is False when a bound stopped it early.

    Example: ``SweepReport(examined=500, removed=500, complete=False)``.
    """

    examined: int
    removed: int
    complete: bool


@dataclass(frozen=True, slots=True)
class _Limits:
    now: float
    ttl_s: float
    retain_months: int
    head_tree: str | None


def sweep_state(
    store: StateStore,
    *,
    ttl_days: int,
    retain_months: int = 6,
    head_tree: str | None = None,
    max_entries: int = SWEEP_MAX_ENTRIES,
    max_seconds: float = SWEEP_MAX_SECONDS,
) -> SweepReport:
    """Remove expired entries, resuming after the cursor the previous run left.

    Raises ``StateUnavailable`` when the store is stateless.

    Example::

        >>> store.sweep(ttl_days=7, head_tree=git.head_tree())  # doctest: +SKIP
        SweepReport(examined=12, removed=3, complete=True)
    """
    clock = store.clock
    limits = _Limits(clock.time(), ttl_days * _DAY_S, retain_months, head_tree)
    previous = store.read_json(SWEEP_DOC)
    start = clock.monotonic()
    examined = removed = 0
    last: Position | None = None
    complete = True
    for position, path, expired in _candidates(store, limits, _cursor(previous)):
        if examined >= max_entries or clock.monotonic() - start >= max_seconds:
            complete = False
            break
        examined += 1
        last = position
        if expired and _remove(path):
            removed += 1
    store.write_json(SWEEP_DOC, _record(previous, limits.now, complete, last))
    return SweepReport(examined, removed, complete)


def sweep_due(store: StateStore) -> bool:
    """Whether no sweep has run in the last 24 hours (or ever).

    Example::

        >>> sweep_due(store)  # doctest: +SKIP
        True
    """
    last = store.read_json(SWEEP_DOC).get("last_run")
    return not isinstance(last, int | float) or store.clock.time() - last >= _DAY_S


def _cursor(previous: dict[str, object]) -> Position | None:
    cursor = previous.get("cursor")
    if isinstance(cursor, list) and len(cursor) == 2:
        index, name = cursor
        if isinstance(index, int) and isinstance(name, str):
            return index, name
    return None


def _record(
    previous: dict[str, object], now: float, complete: bool, last: Position | None
) -> dict[str, object]:
    return {
        "last_run": now,
        "last_complete": now if complete else previous.get("last_complete"),
        "cursor": None if complete or last is None else list(last),
    }


def _candidates(
    store: StateStore, limits: _Limits, after: Position | None
) -> Iterator[tuple[Position, str, bool]]:
    """Every sweepable entry in a fixed order, starting after ``after``."""
    categories = (
        ("sessions", _session_expired),
        ("tmp", _tmp_expired),
        ("stop", _baseline_expired),
        ("", _decision_log_expired),
        ("checkpoints", _checkpoint_expired),  # last: a saved cursor keeps its category index
    )
    for index, (subdir, expired) in enumerate(categories):
        directory = str(store.path(subdir)) if subdir else str(store.root)
        for name in _sorted_names(directory):
            if after is not None and (index, name) <= after:
                continue
            path = os.path.join(directory, name)
            yield (index, name), path, expired(path, name, limits)


def _sorted_names(directory: str) -> list[str]:
    try:
        return sorted(os.listdir(directory))
    except OSError:
        return []


def _mtime(path: str) -> float | None:
    try:
        return os.lstat(path).st_mtime
    except OSError:
        return None


def _session_expired(path: str, _name: str, limits: _Limits) -> bool:
    stamps = [_mtime(path), *(_mtime(os.path.join(path, f)) for f in _SESSION_FILES)]
    newest = max((s for s in stamps if s is not None), default=None)
    return newest is not None and limits.now - newest > limits.ttl_s


def _tmp_expired(path: str, _name: str, limits: _Limits) -> bool:
    mtime = _mtime(path)
    return mtime is not None and limits.now - mtime > _TMP_TTL_S


def _checkpoint_expired(path: str, _name: str, limits: _Limits) -> bool:
    mtime = _mtime(path)
    return mtime is not None and limits.now - mtime > limits.ttl_s


def _baseline_expired(path: str, name: str, limits: _Limits) -> bool:
    match = _BASELINE.fullmatch(name)
    if match is None or match["tree"] == limits.head_tree:
        return False
    mtime = _mtime(path)
    return mtime is not None and limits.now - mtime > _BASELINE_TTL_S


def _decision_log_expired(_path: str, name: str, limits: _Limits) -> bool:
    match = _DECISION_LOG.fullmatch(name)
    if match is None:
        return False
    now = time.gmtime(limits.now)
    age = (now.tm_year * 12 + now.tm_mon) - (int(match["year"]) * 12 + int(match["month"]))
    return age > limits.retain_months


def _remove(path: str) -> bool:
    """Delete one entry; a directory only when it is a real one, never through a link."""
    try:
        info = os.lstat(path)
        if stat.S_ISDIR(info.st_mode):
            import shutil  # lazy: only a sweep that found an expired session pays for it

            shutil.rmtree(path)
        else:
            os.unlink(path)
    except OSError:
        return False
    return True
