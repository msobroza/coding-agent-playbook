"""Append-only JSONL writers for the engine's local logs (specs/prK-lifecycle-hooks.md §D.6.2).

:func:`append_jsonl` is the one generic writer. The hook runtime's
guard-decision log, local-audit-log's activity lines and SPEC §17.4's
``playbook sync`` audit line all go through it. :func:`append_decision` is the
typed wrapper the decision log uses; :func:`append_activity` local-audit-log's
(specs/prK-hook-pack.md §E.5), with the optional ``prev`` hash chain that
:func:`verify_chain` checks and the ``retain_days`` cut :func:`prune_audit`
applies. The module is stdlib-only because the hook dispatcher imports it on
its hot path (§D.1).

Why a line needs no lock (§D.6.1):

- Claude runs parallel tool calls and subagents as concurrent processes, so
  several writers can append to one file at once. Each line is a single
  ``os.write`` on an ``O_APPEND`` descriptor and at most 4 KiB, so concurrent
  lines never interleave.
- ``O_NOFOLLOW`` refuses a log that was swapped for a symlink, so nobody can
  redirect the log onto another file. Guarding the parent directories is the
  state root's job (K2).

Only rotation needs mutual exclusion. It runs under a sidecar lock file, not a
lock on the log itself: Windows cannot rename a file this process holds open.
The lock wait is bounded (200 ms) and a busy lock skips rotation rather than
blocking, because the log must never stall a tool call.

The decision log never stores command text, paths, prompts, file contents,
reasons or env values (D-10). ``append_decision`` enforces the exact record
keys at run time, because a TypedDict is not checked at run time.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import time
from typing import TYPE_CHECKING, TypedDict

if sys.platform == "win32":  # pragma: no cover - CI is POSIX-only (Q-D6)
    import msvcrt
else:
    import fcntl

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

#: One line, newline included. Small enough that one ``O_APPEND`` write is atomic.
MAX_LINE_BYTES = 4096
#: A log at or over this size is rotated before the next append (§D.6.1).
ROTATE_BYTES = 5 * 1024 * 1024
#: The longest an append waits for the rotation lock (§D.6.1's 200 ms limit).
LOCK_TIMEOUT_S = 0.2

_LOCK_POLL_S = 0.005
_FILE_MODE = 0o600
#: Upper bound on ``<stem>.<n><suffix>`` probes, so a full namespace cannot spin.
_MAX_ROTATIONS = 9999
# O_BINARY stops Windows from turning "\n" into "\r\n"; O_NOFOLLOW is POSIX-only.
_OPEN_FLAGS: int = getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
_APPEND_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_APPEND | _OPEN_FLAGS
_LOCK_FLAGS = os.O_RDWR | os.O_CREAT | _OPEN_FLAGS
#: ``YYYY-MM`` of an ISO-8601 timestamp that starts ``YYYY-MM-DDT``.
_TS_MONTH = re.compile(r"([0-9]{4}-(?:0[1-9]|1[0-2]))-[0-9]{2}T")
#: The month-file prefixes of guard-decision-log and local-audit-log (§D.6.1's layout).
DECISION_LOG_PREFIX = "decisions"
ACTIVITY_LOG_PREFIX = "audit"
#: A month file of local-audit-log, rotated copies included.
_ACTIVITY_FILE = re.compile(
    r"audit-(?P<year>[0-9]{4})-(?P<month>0[1-9]|1[0-2])(?:\.[0-9]+)?\.jsonl"
)
_DAY_S = 86_400
#: At most this many state-root names are examined by one :func:`prune_audit`.
_PRUNE_MAX_NAMES = 500


class GuardDecisionRecord(TypedDict):
    """One guard-decision-log line (§D.6.2): static identifiers and flags, never content.

    ``decision`` is one of ``deny``, ``ask``, ``context``, ``ask→deny``,
    ``override``, ``degraded``, ``escape``, ``untrusted``,
    ``contract_violation`` or ``canary``; ``effective`` is what the harness was
    finally told. ``ts`` is ISO-8601 UTC and also names the month file.

    Example::

        >>> {"ts", "decision", "hook_id"} <= GuardDecisionRecord.__required_keys__
        True
    """

    v: int
    ts: str
    harness: str
    session_id: str
    event: str
    hook_id: str
    rule_id: str | None
    decision: str
    effective: str
    tool_name: str | None
    tool_class: str | None
    unattended: bool
    degraded: bool
    escape: str | None
    canary: bool
    latency_ms: int


#: Exactly the keys a decision line carries; anything else is refused (D-10).
DECISION_RECORD_KEYS: frozenset[str] = GuardDecisionRecord.__required_keys__

#: The keys a local-audit-log line may carry (specs/prK-hook-pack.md §E.5): structure
#: only. ``commands`` holds argv0 / subcommand / flag names, ``paths`` repo-relative
#: or masked paths, ``prompt`` a length, digest and category counts; ``command_text``
#: is the redacted text ``config.full_commands`` opts into; ``prev`` is the chain.
ACTIVITY_RECORD_KEYS: frozenset[str] = frozenset(
    {
        "v",
        "ts",
        "harness",
        "session_id",
        "event",
        "source",
        "tool_name",
        "tool_class",
        "ok",
        "exit_code",
        "interrupted",
        "duration_ms",
        "commands",
        "paths",
        "prompt",
        "command_text",
        "prev",
    }
)


def encode_jsonl_line(record: Mapping[str, object]) -> bytes:
    """``record`` as one compact, key-sorted ASCII JSON line, trailing newline included.

    Raises ``ValueError`` for NaN or infinity (not JSON) and for a line over
    :data:`MAX_LINE_BYTES`, naming its size.

    Example::

        >>> encode_jsonl_line({"b": 1, "a": None})
        b'{"a":null,"b":1}\\n'
    """
    text = json.dumps(dict(record), sort_keys=True, separators=(",", ":"), allow_nan=False)
    line = f"{text}\n".encode("ascii")
    if len(line) > MAX_LINE_BYTES:
        raise ValueError(
            f"JSONL line is {len(line)} bytes; the limit is {MAX_LINE_BYTES} bytes "
            "so that one O_APPEND write stays atomic"
        )
    return line


def append_jsonl(
    path: Path,
    record: Mapping[str, object],
    *,
    rotate_bytes: int = ROTATE_BYTES,
    lock_timeout_s: float = LOCK_TIMEOUT_S,
) -> None:
    """Append ``record`` to ``path`` as one line, rotating the file first once it is full.

    The parent directory must exist. A new file is created with mode 0600, and
    a symlinked ``path`` raises ``OSError``. A full log is renamed to
    :func:`rotated_log_path` under the sidecar :func:`rotation_lock_path`.

    Example::

        >>> append_jsonl(state_dir / "audit-2026-10.jsonl", {"event": "sync"})  # doctest: +SKIP
    """
    line = encode_jsonl_line(record)
    _rotate_if_full(path, rotate_bytes, lock_timeout_s)
    _write_line(path, line)


def decision_log_path(state_dir: Path, ts: str) -> Path:
    """The month file a decision stamped ``ts`` belongs in; the month comes from ``ts``, not a clock.

    Example::

        >>> decision_log_path(Path("/state"), "2026-10-14T10:30:00.123Z")
        PosixPath('/state/decisions-2026-10.jsonl')
    """
    return _month_path(state_dir, DECISION_LOG_PREFIX, ts, "decision")


def activity_log_path(state_dir: Path, ts: str) -> Path:
    """The ``audit-YYYY-MM.jsonl`` month file an activity line stamped ``ts`` belongs in.

    Example::

        >>> activity_log_path(Path("/state"), "2026-10-14T10:30:00.123Z")
        PosixPath('/state/audit-2026-10.jsonl')
    """
    return _month_path(state_dir, ACTIVITY_LOG_PREFIX, ts, "activity")


def _month_path(state_dir: Path, prefix: str, ts: str, what: str) -> Path:
    month = _TS_MONTH.match(ts)
    if month is None:
        raise ValueError(f"{what} ts {ts!r} does not start with an ISO-8601 'YYYY-MM-DDT' date")
    return state_dir / f"{prefix}-{month.group(1)}.jsonl"


def append_decision(state_dir: Path, record: GuardDecisionRecord) -> None:
    """Append one decision to ``<state_dir>/decisions-YYYY-MM.jsonl``.

    Refuses a record whose keys differ from :data:`DECISION_RECORD_KEYS`, so no
    content field can reach the log.

    Example::

        >>> append_decision(state_dir, record)  # doctest: +SKIP
    """
    _require_decision_keys(record)
    append_jsonl(decision_log_path(state_dir, record["ts"]), record)


def append_activity(
    state_dir: Path,
    record: Mapping[str, object],
    *,
    chain: bool = False,
    lock_timeout_s: float = LOCK_TIMEOUT_S,
) -> None:
    """Append one local-audit-log line to ``<state_dir>/audit-YYYY-MM.jsonl``.

    Refuses a key outside :data:`ACTIVITY_RECORD_KEYS` (structure only, never
    content) and a caller-set ``prev``. With ``chain``, ``prev`` is the sha256
    of the file's previous line (``null`` on its first), computed under the
    rotation lock; when the lock stays busy the line is still written, with
    ``prev: null``, so :func:`verify_chain` reports a break rather than the
    log stalling a tool call. The chain detects corruption, not tampering.

    Example::

        >>> append_activity(state_dir, {"v": 1, "ts": ts, "event": "session_start"})  # doctest: +SKIP
    """
    _require_activity_keys(record)
    ts = record.get("ts")
    path = activity_log_path(state_dir, ts if isinstance(ts, str) else "")
    if not chain:
        append_jsonl(path, record)
        return
    lock = os.open(rotation_lock_path(path), _LOCK_FLAGS, _FILE_MODE)
    try:
        if not acquire_lock(lock, lock_timeout_s):
            _write_line(path, encode_jsonl_line({**record, "prev": None}))
            return
        try:
            if _is_full(path, ROTATE_BYTES):
                _rotate(path)
            _write_line(path, encode_jsonl_line({**record, "prev": _last_line_digest(path)}))
        finally:
            release_lock(lock)
    finally:
        os.close(lock)


def verify_chain(path: Path) -> int | None:
    """The 1-based number of the first line that breaks ``path``'s hash chain, else ``None``.

    A line breaks it when it is not a JSON object, when its ``prev`` is not the
    sha256 of the line before it (``null`` for the first) or when it is cut
    off (no trailing newline): a deleted, edited or truncated line is caught.

    Example::

        >>> verify_chain(state_dir / "audit-2026-10.jsonl")  # doctest: +SKIP
        None
    """
    data = path.read_bytes()
    lines = data.split(b"\n")
    complete = data.endswith(b"\n") or not data
    if complete:
        lines.pop()
    previous: str | None = None
    for number, raw in enumerate(lines, start=1):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return number
        if not isinstance(parsed, dict) or parsed.get("prev") != previous:
            return number
        previous = hashlib.sha256(raw).hexdigest()
    return None if complete else len(lines)


def prune_audit(state_dir: Path, *, retain_days: int, now: float) -> list[Path]:
    """Delete local-audit-log month files whose every line is older than ``retain_days``.

    A file is old once its month ended before the month ``retain_days`` ago
    began, so a line is never deleted early. Rotated copies and their lock
    sidecars go too. At most 500 names are examined. Returns what was removed.

    Example::

        >>> prune_audit(state_dir, retain_days=90, now=time.time())  # doctest: +SKIP
        [PosixPath('/state/audit-2026-01.jsonl')]
    """
    cutoff = time.gmtime(now - retain_days * _DAY_S)
    cutoff_month = cutoff.tm_year * 12 + cutoff.tm_mon
    removed: list[Path] = []
    for name in sorted(os.listdir(state_dir))[:_PRUNE_MAX_NAMES]:
        match = _ACTIVITY_FILE.fullmatch(name)
        if match is None or int(match["year"]) * 12 + int(match["month"]) >= cutoff_month:
            continue
        path = state_dir / name
        try:
            os.unlink(path)
        except OSError:
            continue
        rotation_lock_path(path).unlink(missing_ok=True)
        removed.append(path)
    return removed


def _require_activity_keys(record: Mapping[str, object]) -> None:
    unexpected = sorted(set(record) - ACTIVITY_RECORD_KEYS)
    if unexpected:
        raise ValueError(
            f"activity record keys must be within ACTIVITY_RECORD_KEYS: unexpected {unexpected}"
        )
    if "prev" in record:
        raise ValueError(
            "activity record 'prev' is set by append_activity(chain=True), not callers"
        )


def _last_line_digest(path: Path) -> str | None:
    """sha256 of ``path``'s last line (its trailing newline excluded); ``None`` for an empty file."""
    try:
        descriptor = os.open(path, os.O_RDONLY | _OPEN_FLAGS)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        # A line is at most MAX_LINE_BYTES, so its start lies within this window.
        handle.seek(max(0, size - MAX_LINE_BYTES - 1))
        tail = handle.read()
    if not tail:
        return None
    last = tail[:-1] if tail.endswith(b"\n") else tail
    return hashlib.sha256(last.rsplit(b"\n", 1)[-1]).hexdigest()


def rotated_log_path(path: Path, index: int) -> Path:
    """The ``index``-th rotated copy of ``path``: ``<stem>.<index><suffix>``.

    Example::

        >>> rotated_log_path(Path("decisions-2026-10.jsonl"), 1).name
        'decisions-2026-10.1.jsonl'
    """
    return path.with_name(f"{path.stem}.{index}{path.suffix}")


def rotation_lock_path(path: Path) -> Path:
    """The sidecar lock file that serializes rotating ``path``.

    Example::

        >>> rotation_lock_path(Path("decisions-2026-10.jsonl")).name
        'decisions-2026-10.jsonl.lock'
    """
    return path.with_name(f"{path.name}.lock")


def _require_decision_keys(record: Mapping[str, object]) -> None:
    keys = set(record)
    if keys == DECISION_RECORD_KEYS:
        return
    unexpected, missing = sorted(keys - DECISION_RECORD_KEYS), sorted(DECISION_RECORD_KEYS - keys)
    raise ValueError(
        "decision record keys must be exactly GuardDecisionRecord's: "
        f"unexpected {unexpected}, missing {missing}"
    )


def _write_line(path: Path, line: bytes) -> None:
    descriptor = os.open(path, _APPEND_FLAGS, _FILE_MODE)
    try:
        written = os.write(descriptor, line)
    finally:
        os.close(descriptor)
    if written != len(line):
        raise OSError(f"short write to {path}: {written} of {len(line)} bytes")


def _is_full(path: Path, rotate_bytes: int) -> bool:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    # A symlink is never rotated: the append's O_NOFOLLOW open refuses it instead.
    return stat.S_ISREG(info.st_mode) and info.st_size >= rotate_bytes


def _rotate_if_full(path: Path, rotate_bytes: int, lock_timeout_s: float) -> None:
    if not _is_full(path, rotate_bytes):
        return
    lock = os.open(rotation_lock_path(path), _LOCK_FLAGS, _FILE_MODE)
    try:
        if not acquire_lock(lock, lock_timeout_s):
            return  # busy: append to the current file; a later append rotates
        try:
            # Re-check under the lock: a concurrent writer may have rotated already.
            if _is_full(path, rotate_bytes):
                _rotate(path)
        finally:
            release_lock(lock)
    finally:
        os.close(lock)


def _rotate(path: Path) -> None:
    target = _free_rotation_target(path)
    if target is None:
        return  # every name is taken: keep appending rather than lose a line
    try:
        os.rename(path, target)
    except PermissionError:
        # Windows refuses to rename a file another process holds open; a later append retries.
        return


def _free_rotation_target(path: Path) -> Path | None:
    for index in range(1, _MAX_ROTATIONS + 1):
        target = rotated_log_path(path, index)
        if not os.path.lexists(target):
            return target
    return None


def acquire_lock(descriptor: int, timeout_s: float) -> bool:
    """Take an exclusive lock on the open ``descriptor``, waiting at most ``timeout_s``.

    Returns False when the lock stays busy: a hook must never stall a tool
    call on a lock (§D.6.1), so the caller skips the locked step instead. The
    hook runtime's state store shares this one lock implementation.

    Example::

        >>> acquire_lock(os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600), 0.2)  # doctest: +SKIP
        True
    """
    deadline = time.monotonic() + timeout_s
    while not _try_lock(descriptor):
        if time.monotonic() >= deadline:
            return False
        time.sleep(_LOCK_POLL_S)
    return True


def _try_lock(descriptor: int) -> bool:
    if sys.platform == "win32":  # pragma: no cover - CI is POSIX-only (Q-D6)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def release_lock(descriptor: int) -> None:
    """Release a lock :func:`acquire_lock` took on ``descriptor``.

    Example::

        >>> release_lock(descriptor)  # doctest: +SKIP
    """
    if sys.platform == "win32":  # pragma: no cover - CI is POSIX-only (Q-D6)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        return
    fcntl.flock(descriptor, fcntl.LOCK_UN)
