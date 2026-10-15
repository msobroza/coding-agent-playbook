"""The per-worktree state root ``<git_dir>/playbook-hooks`` (specs/prK-lifecycle-hooks.md §D.6.1).

Everything the runtime remembers between hook processes lives here: session
flags, the ledger, the Stop chain, the config-digest cache, the interpreter
pin. The root sits under the git dir, so it is per worktree, never committed,
outside the working tree and survives ``git clean -x``. It is found without a
subprocess: ``RepoInfo.git_dir`` already is ``git rev-parse --git-dir`` (D-9).

The store is defensive because the agent runs as the same user:

- directories are 0700 and files 0600; a symlinked or foreign-owned root (or
  a symlink planted below it) is refused, so state never lands somewhere the
  agent chose;
- JSON documents are read-modify-written under a ``locks/<name>.lock`` flock
  whose wait is bounded to 200 ms, and written through a temp file plus
  ``os.replace``; JSONL lines are single ``O_APPEND`` writes (``security.audit``);
- nothing here may fail a tool call: an unusable root makes the store
  *stateless* and a busy lock makes that one operation stateless. Both raise
  :class:`StateUnavailable`, which every caller turns into its stateless
  default (dedupe and budgets off, so a Stop gate can only report).
"""

from __future__ import annotations

import hashlib
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime._state_files import (
    DIR_MODE,
    FILE_MODE,
    MAX_DOCUMENT_BYTES,
    StateUnavailable,
    as_document,
    encode,
    ensure_private_dir,
    parts,
    read_regular,
    root_problem,
    write_new,
)
from coding_agent_playbook.hook_runtime.deps import SystemClock
from coding_agent_playbook.security.audit import (
    ROTATE_BYTES,
    acquire_lock,
    append_jsonl,
    release_lock,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from coding_agent_playbook.hook_runtime._state_sweep import SweepReport
    from coding_agent_playbook.hook_runtime.deps import Clock
    from coding_agent_playbook.hook_runtime.event import RepoInfo

__all__ = [
    "DIR_MODE",
    "FILE_MODE",
    "LOCK_TIMEOUT_S",
    "MAX_DOCUMENT_BYTES",
    "STATE_DIR_NAME",
    "StateStore",
    "StateUnavailable",
    "iso_utc",
    "session_key",
]

#: The root's name under the git dir; ``git rev-parse --git-path playbook-hooks``.
STATE_DIR_NAME: Final = "playbook-hooks"
#: The longest a read-modify-write waits for its lock (§D.6.1).
LOCK_TIMEOUT_S: Final = 0.2
_LOCK_FLAGS: Final = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)


def session_key(session_id: str) -> str:
    """The directory name of a session: ``sha256(session_id)[:16]``, never the raw id.

    Example::

        >>> session_key("abc")
        'ba7816bf8f01cfea'
    """
    return hashlib.sha256(session_id.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def iso_utc(epoch: float) -> str:
    """``epoch`` as the ISO-8601 UTC millisecond timestamp every state line carries.

    Example::

        >>> iso_utc(1791973800.123)
        '2026-10-14T10:30:00.123Z'
    """
    whole = int(epoch)
    millis = min(999, round((epoch - whole) * 1000))
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(whole)) + f".{millis:03d}Z"


class StateStore:
    """One state root and the only code that touches files below it.

    ``rel`` arguments are ``/``-separated paths relative to the root (no
    ``..``, no absolute paths). ``clock`` dates the TTL sweep; ``uid`` is the
    owner the root must have (default: this process's user).

    Example::

        >>> store = StateStore.for_repo(repo)  # doctest: +SKIP
        >>> store.update_json("sessions/ab/session.json", lambda doc: doc.setdefault("v", 1))
        1
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        clock: Clock | None = None,
        lock_timeout_s: float = LOCK_TIMEOUT_S,
        uid: int | None = None,
    ) -> None:
        self._root = Path(root)
        self._clock: Clock = clock or SystemClock()
        self._lock_timeout_s = lock_timeout_s
        self._uid = uid
        self._problem: str | None = None
        self._checked = False

    @classmethod
    def for_repo(cls, repo: RepoInfo, **kwargs: Any) -> StateStore:
        """The store of ``repo``'s worktree: ``<git_dir>/playbook-hooks``."""
        return cls(Path(repo.git_dir) / STATE_DIR_NAME, **kwargs)

    @property
    def root(self) -> Path:
        """The state root, whether or not it is usable."""
        return self._root

    @property
    def clock(self) -> Clock:
        """The clock that dates sweeps and timestamps."""
        return self._clock

    @property
    def usable(self) -> bool:
        """Whether the root is a private directory this user owns (checked once)."""
        return self.stateless_reason is None

    @property
    def stateless_reason(self) -> str | None:
        """Why the store runs stateless, or ``None`` when it is usable."""
        if not self._checked:
            self._problem = root_problem(self._root, self._uid)
            self._checked = True
        return self._problem

    # --- paths ---------------------------------------------------------------------------

    def path(self, rel: str) -> Path:
        """``rel`` below the root; raises ``ValueError`` for a path that could leave it."""
        return self._root.joinpath(*parts(rel))

    def private_dir(self, rel: str) -> Path:
        """Create ``rel`` (``""`` is the root) as 0700 directories, refusing any symlink."""
        self._require_usable()
        current = self._root
        for part in parts(rel) if rel else ():
            current = current / part
            ensure_private_dir(current)
        return current

    def _parent_dir(self, rel: str) -> Path:
        return self.private_dir(rel.rpartition("/")[0])

    def lock_path(self, rel: str) -> Path:
        """The lock file serializing writes of document ``rel``."""
        return self.private_dir("locks") / (rel.replace("/", "__") + ".lock")

    # --- documents -----------------------------------------------------------------------

    def read_json(self, rel: str) -> dict[str, Any]:
        """Document ``rel``; ``{}`` when it is absent, corrupt or not a JSON object."""
        self._require_usable()
        data = read_regular(self.path(rel), MAX_DOCUMENT_BYTES)
        return as_document(data)

    def read_bytes(self, rel: str, limit: int = MAX_DOCUMENT_BYTES) -> bytes | None:
        """The bytes of ``rel``, or ``None`` when it is absent or larger than ``limit``."""
        self._require_usable()
        return read_regular(self.path(rel), limit)

    def write_json(self, rel: str, document: Mapping[str, Any]) -> None:
        """Replace document ``rel`` atomically (no lock: last writer wins)."""
        self.replace_bytes(rel, encode(document))

    def replace_bytes(self, rel: str, data: bytes) -> None:
        """Replace ``rel`` with ``data`` through a 0600 temp file and ``os.replace``."""
        target = self.path(rel)
        self._parent_dir(rel)
        temp = self.private_dir("tmp") / f"{target.name}.{os.getpid()}.{os.urandom(4).hex()}"
        try:
            write_new(temp, data)
            os.replace(temp, target)
        except OSError as exc:
            temp.unlink(missing_ok=True)
            raise StateUnavailable(f"cannot write state file {rel!r}: {exc.strerror}") from exc

    def remove(self, rel: str) -> None:
        """Delete ``rel`` if it exists; an absent file is no error.

        A document whose absence is its meaning (the active-prompt record)
        is removed rather than emptied, so readers decide on one ``stat``.
        """
        self._require_usable()
        try:
            self.path(rel).unlink(missing_ok=True)
        except OSError as exc:
            raise StateUnavailable(f"cannot remove state file {rel!r}: {exc.strerror}") from exc

    def update_json[T](self, rel: str, change: Callable[[dict[str, Any]], T]) -> T:
        """Run ``change`` on document ``rel`` under its lock and persist what it did.

        ``change`` mutates the document in place and returns the caller's
        answer; an unchanged document is not rewritten. Raises
        :class:`StateUnavailable` when stateless or when the lock stays busy.
        """
        with self.lock(rel):
            document = self.read_json(rel)
            before = encode(document)
            result = change(document)
            after = encode(document)
            if after != before:
                self.replace_bytes(rel, after)
            return result

    def append_jsonl(
        self, rel: str, record: Mapping[str, object], *, rotate_bytes: int = ROTATE_BYTES
    ) -> None:
        """Append ``record`` to ``rel`` as one atomic ``O_APPEND`` line (``security.audit``)."""
        target = self.path(rel)
        self._parent_dir(rel)
        try:
            append_jsonl(target, record, rotate_bytes=rotate_bytes)
        except OSError as exc:
            raise StateUnavailable(f"cannot append to {rel!r}: {exc.strerror}") from exc

    @contextmanager
    def lock(self, rel: str, *, timeout_s: float | None = None) -> Iterator[None]:
        """Hold the lock of document ``rel``; :class:`StateUnavailable` after the bounded wait.

        ``timeout_s`` replaces the 200 ms document wait, for a lock that
        serializes long work (``locks/exec-stage.lock``, §D.5.6).
        """
        wait = self._lock_timeout_s if timeout_s is None else timeout_s
        lock_file = self.lock_path(rel)
        try:
            descriptor = os.open(lock_file, _LOCK_FLAGS, FILE_MODE)
        except OSError as exc:
            raise StateUnavailable(f"cannot open lock {lock_file.name}: {exc.strerror}") from exc
        try:
            if not acquire_lock(descriptor, wait):
                raise StateUnavailable(
                    f"state lock for {rel!r} busy for {wait} s; running this operation stateless"
                )
            try:
                yield
            finally:
                release_lock(descriptor)
        finally:
            os.close(descriptor)

    # --- maintenance ---------------------------------------------------------------------

    def sweep(
        self, *, ttl_days: int, retain_months: int = 6, head_tree: str | None = None
    ) -> SweepReport:
        """Run one bounded TTL sweep (see ``_state_sweep``); ``StateUnavailable`` when stateless."""
        from coding_agent_playbook.hook_runtime._state_sweep import sweep_state

        return sweep_state(
            self, ttl_days=ttl_days, retain_months=retain_months, head_tree=head_tree
        )

    def sweep_due(self) -> bool:
        """Whether the last sweep ran more than 24 h ago (Stop sweeps lazily, §D.6.1)."""
        from coding_agent_playbook.hook_runtime._state_sweep import sweep_due

        return sweep_due(self)

    # --- root checks ---------------------------------------------------------------------

    def _require_usable(self) -> None:
        reason = self.stateless_reason
        if reason is not None:
            raise StateUnavailable(reason)
