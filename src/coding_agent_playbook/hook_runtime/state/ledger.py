"""The session ledger: which paths a session touched and which checks it ran (specs/prK-lifecycle-hooks.md §D.6.3).

``post_tool_use`` and ``post_tool_use_failure`` append one line each to
``sessions/<key>/ledger.jsonl``; the Stop stages, ``subagent_stop`` and the
source-changed branch read it back. The ledger never stores what it must not:

- paths are repo-relative; a path outside the repository is ``"<outside>"``
  and a secret path is ``"<secret-path>"``, so neither an absolute path nor a
  credential file name is ever written;
- ``cats`` are the ``guard_config.path_classes`` a path falls in, plus
  ``secret``; stage planning reads them instead of re-matching globs;
- verify lines carry the ``stop_gate.verify_commands`` id, never the command.

A session keeps at most 2,000 lines. Past that, the ledger compacts to one
summary line (the union of paths, writes and categories) followed by the
verify lines that came after the last touch, which is all verify-claim needs.
"""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.dispatch.paths import fold_key
from coding_agent_playbook.hook_runtime.state.audit_log import encode_jsonl_line
from coding_agent_playbook.hook_runtime.state.store import StateUnavailable, iso_utc, session_key

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.dispatch.event import EventName, ToolClass
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.globs import GlobSet
    from coding_agent_playbook.hook_runtime.state.store import StateStore

__all__ = ["LEDGER_MAX_LINES", "OUTSIDE", "SECRET_PATH", "Ledger", "mask_path", "path_categories"]

LEDGER_MAX_LINES: Final = 2000
OUTSIDE: Final = "<outside>"
SECRET_PATH: Final = "<secret-path>"
SECRET_CATEGORY: Final = "secret"
#: The shortest line the ledger writes: below this many bytes the cap cannot be reached.
_MIN_LINE_BYTES: Final = 40
#: The line cap bounds the file, so the audit writer's 5 MiB rotation must never move it.
_NO_ROTATION: Final = 1 << 62


def is_secret(path: NormalizedPath, secret: GlobSet, *, platform: str = sys.platform) -> bool:
    """Whether ``path`` is a secret path by its resolved key or by its spelling.

    The spelling matters for a symlink: ``notes.txt -> .env`` resolves to an
    innocent name, but ``.env -> notes.txt`` must still be masked.

    Example::

        >>> is_secret(normalize_path(".env", ...), compile_globs([".env*"]))  # doctest: +SKIP
        True
    """
    return secret.matches(path.key) or secret.matches(fold_key(path.path, platform))


def mask_path(path: NormalizedPath, secret: GlobSet, *, platform: str = sys.platform) -> str:
    """What the ledger may record for ``path``: its repo-relative form or a mask.

    Example::

        >>> mask_path(normalize_path("/etc/passwd", ...), secret)  # doctest: +SKIP
        '<outside>'
    """
    if is_secret(path, secret, platform=platform):
        return SECRET_PATH
    return OUTSIDE if path.repo_rel is None else path.repo_rel


def path_categories(
    path: NormalizedPath,
    classes: Mapping[str, GlobSet],
    secret: GlobSet,
    *,
    platform: str = sys.platform,
) -> tuple[str, ...]:
    """The ``path_classes`` names an in-repo ``path`` matches, plus ``secret``; sorted.

    Example::

        >>> path_categories(normalize_path("src/x.py", ...), {"py": py_globs}, secret)  # doctest: +SKIP
        ('py',)
    """
    names = {SECRET_CATEGORY} if is_secret(path, secret, platform=platform) else set()
    if path.repo_rel is not None:
        names.update(name for name, globs in classes.items() if globs.matches(path.key))
    return tuple(sorted(names))


class Ledger:
    """The ledger of one session; ``now`` (epoch seconds) stamps each line.

    Example::

        >>> ledger = Ledger(store, ev.session_id, path_classes=cfg.path_classes,
        ...                 secret_paths=cfg.secret_paths, now=clock.time)  # doctest: +SKIP
        >>> ledger.record_verify(event=EventName.POST_TOOL_USE, verify="lint", ok=True)
        True
    """

    def __init__(
        self,
        store: StateStore,
        session_id: str,
        *,
        path_classes: Mapping[str, GlobSet],
        secret_paths: GlobSet,
        now: Callable[[], float],
        platform: str = sys.platform,
    ) -> None:
        self._store = store
        self._rel = f"sessions/{session_key(session_id)}/ledger.jsonl"
        self._classes = path_classes
        self._secret = secret_paths
        self._now = now
        self._platform = platform

    @property
    def path(self) -> Path:
        """The ledger file."""
        return self._store.path(self._rel)

    def record_touch(
        self,
        *,
        event: EventName,
        tool_class: ToolClass,
        tool: str,
        paths: Sequence[NormalizedPath] = (),
        writes: Sequence[NormalizedPath] = (),
    ) -> bool:
        """Record the paths a tool call read or edited and the files a command wrote."""
        record = self._header(event, tool_class) | {"tool": tool}
        for key, group in (("paths", paths), ("writes", writes)):
            if group:
                record[key] = self._masked(group)
        cats = {c for p in (*paths, *writes) for c in self._categories(p)}
        record["cats"] = sorted(cats)
        return self._append(record)

    def record_verify(
        self, *, event: EventName, verify: str, ok: bool, exit_code: int | None = None
    ) -> bool:
        """Record one run of the verify command ``verify`` and whether it passed."""
        record = self._header(event, None) | {"tc": "shell", "verify": verify, "ok": ok}
        if exit_code is not None:
            record["exit"] = exit_code
        return self._append(record)

    def read(self) -> list[dict[str, Any]]:
        """Every readable line, oldest first; ``[]`` when stateless or absent."""
        try:
            data = self._store.read_bytes(self._rel)
        except StateUnavailable:
            return []
        return _parse_lines(data or b"")

    def _header(self, event: EventName, tool_class: ToolClass | None) -> dict[str, Any]:
        header: dict[str, Any] = {"v": 1, "ts": iso_utc(self._now()), "ev": event.value}
        if tool_class is not None:
            header["tc"] = tool_class.value
        return header

    def _masked(self, group: Iterable[NormalizedPath]) -> list[str]:
        masked = (mask_path(p, self._secret, platform=self._platform) for p in group)
        return list(dict.fromkeys(masked))

    def _categories(self, path: NormalizedPath) -> tuple[str, ...]:
        return path_categories(path, self._classes, self._secret, platform=self._platform)

    def _append(self, record: dict[str, Any]) -> bool:
        try:
            self._compact_if_full()
            self._store.append_jsonl(self._rel, _fitted(record), rotate_bytes=_NO_ROTATION)
        except StateUnavailable:
            return False
        return True

    def _compact_if_full(self) -> None:
        """Fold the ledger into a summary once the next line would pass the cap."""
        try:
            size = os.lstat(self.path).st_size
        except OSError:
            return
        if size < LEDGER_MAX_LINES * _MIN_LINE_BYTES:
            return
        with self._store.lock(self._rel):
            data = self._store.read_bytes(self._rel) or b""
            if data.count(b"\n") < LEDGER_MAX_LINES - 1:
                return
            records = _parse_lines(data)
            compacted = [_summary(records, iso_utc(self._now())), *_verifies_after_touch(records)]
            text = "".join(
                json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in compacted
            )
            self._store.replace_bytes(self._rel, text.encode("utf-8"))


def _fitted(record: dict[str, Any]) -> dict[str, Any]:
    """``record`` with its path lists halved until it fits one atomic JSONL line."""
    while True:
        try:
            encode_jsonl_line(record)
        except ValueError:
            lists = [k for k in ("paths", "writes") if record.get(k)]
            if not lists:
                raise
            for key in lists:
                record[key] = record[key][: len(record[key]) // 2]
            record["truncated"] = True
            continue
        return record


def _parse_lines(data: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in data.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue  # a torn or hand-edited line is skipped, never fatal
        if isinstance(record, dict):
            records.append(record)
    return records


def _union(records: Iterable[dict[str, Any]], key: str) -> list[str]:
    return sorted({item for r in records for item in r.get(key, ()) if isinstance(item, str)})


def _summary(records: list[dict[str, Any]], ts: str) -> dict[str, Any]:
    count = sum(_line_weight(r) for r in records)
    summary: dict[str, Any] = {"v": 1, "ts": ts, "ev": "summary", "n": count}
    for key in ("paths", "writes", "cats"):
        summary[key] = _union(records, key)
    return summary


def _line_weight(record: dict[str, Any]) -> int:
    """How many original lines ``record`` stands for (a summary counts its ``n``)."""
    folded = record.get("n")
    return folded if record.get("ev") == "summary" and isinstance(folded, int) else 1


def _verifies_after_touch(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The verify lines after the last line that touched a path (verify-claim's evidence)."""
    last_touch = max(
        (i for i, r in enumerate(records) if "paths" in r or "writes" in r), default=-1
    )
    return [r for r in records[last_touch + 1 :] if "verify" in r]
