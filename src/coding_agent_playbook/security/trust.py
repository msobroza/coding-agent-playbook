"""The user-local trust store: approvals of repo- and overlay-controlled code (prK §B.4).

Hooks run with the user's full permissions, so no external-command handler and
no execution stage (pytest + ``conftest.py``, mypy + plugins) may run without a
trust entry the user approved on this machine. This module is the one reader
**and** writer of those approvals:

- ``handlers[<hook-id>] = {source, launcher, args_sha256, script_sha256,
  approved_at}``: any change to the source package, the launcher, the args or
  the script bytes invalidates it. Never the interpreter path, which is per machine.
- ``execution = {stages_sha256, approved_at}``: any change to the
  machine-independent stage list invalidates it.

The store lives outside the repository (:func:`default_trust_store_path`), so
a clone can never carry approvals; a path resolving inside the repo is refused.
Approvals are keyed by :func:`repo_key`, the git common dir, so every worktree
of a clone shares them. The store holds approvals only: the interpreter pin is
not trust (K-14). A store that cannot be read, or that another user could have
written, grants nothing and is never overwritten.

Stdlib-only and import-light: the hook dispatcher reads it on its hot path
(§D.1). No subprocess either: the common dir comes from the on-disk ``.git``
layout, which is what ``git rev-parse --git-common-dir`` reads.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

#: Bump on an incompatible document change; a store with another version grants nothing.
TRUST_STORE_SCHEMA: Final = 1

_APP_DIR: Final = "coding-agent-playbook"
_FILE_NAME: Final = "trust.json"
_DIR_MODE: Final = 0o700
_FILE_MODE: Final = 0o600
#: A store group or others could write may hold approvals the user never gave.
_FOREIGN_WRITE_BITS: Final = stat.S_IWGRP | stat.S_IWOTH
_TEMP_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)


class TrustStoreError(Exception):
    """The store cannot be used as asked: it sits inside the repo, or cannot be read or written."""


@dataclass(frozen=True)
class HandlerApproval:
    """What an external handler runs, as approved: the code identity plus when.

    ``approved_at`` is ISO-8601 UTC; it never counts as a change.

    Example::

        >>> HandlerApproval("acme_rules", "python", "a" * 64, "b" * 64).approved_at
        ''
    """

    source: str
    launcher: str
    args_sha256: str
    script_sha256: str
    approved_at: str = ""

    def same_code(self, other: HandlerApproval) -> bool:
        """True when ``other`` runs the same code (every field but ``approved_at`` equal)."""
        return (self.source, self.launcher, self.args_sha256, self.script_sha256) == (
            other.source,
            other.launcher,
            other.args_sha256,
            other.script_sha256,
        )


@dataclass(frozen=True)
class ExecutionApproval:
    """The approved execution-stage list, by its sha256, plus when (ISO-8601 UTC).

    Example::

        >>> ExecutionApproval("c" * 64).approved_at
        ''
    """

    stages_sha256: str
    approved_at: str = ""


def default_trust_store_path(
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """``$XDG_STATE_HOME/coding-agent-playbook/trust.json`` (Windows: ``%LOCALAPPDATA%``).

    Without the variable (or with a relative ``XDG_STATE_HOME``, which the XDG
    spec says to ignore) it falls back to ``~/.local/state`` (Windows:
    ``~/AppData/Local``). Every input defaults to this process's own.

    Example::

        >>> default_trust_store_path(environ={}, platform="linux", home=Path("/home/dev"))
        PosixPath('/home/dev/.local/state/coding-agent-playbook/trust.json')
    """
    env = os.environ if environ is None else environ
    user_home = Path(os.path.expanduser("~")) if home is None else home
    if (sys.platform if platform is None else platform) == "win32":
        local = env.get("LOCALAPPDATA", "")
        root = Path(local) if local else user_home / "AppData" / "Local"
    else:
        state = env.get("XDG_STATE_HOME", "")
        root = Path(state) if os.path.isabs(state) else user_home / ".local" / "state"
    return root / _APP_DIR / _FILE_NAME


def git_common_dir(repo_root: Path) -> Path | None:
    """The resolved git common dir of the checkout holding ``repo_root``, or None outside git.

    Walks up like git does, to the nearest ``.git``: a directory is itself the
    git dir; a ``gitdir: <path>`` file (a linked worktree, a submodule) points
    at it. A ``commondir`` file inside the git dir names the shared one.

    Example::

        >>> git_common_dir(Path("/no/such/dir")) is None
        True
    """
    start = repo_root.resolve()
    for directory in (start, *start.parents):
        dot_git = directory / ".git"
        if dot_git.is_dir():
            return _common_of(dot_git)
        if dot_git.is_file():
            git_dir = _gitdir_of(dot_git)
            return None if git_dir is None else _common_of(git_dir)
    return None


def _gitdir_of(dot_git_file: Path) -> Path | None:
    """The git dir a ``.git`` file names (``gitdir: <path>``), or None when it names none."""
    first_line = _read_first_line(dot_git_file)
    if first_line is None or not first_line.startswith("gitdir:"):
        return None
    target = Path(first_line.removeprefix("gitdir:").strip())
    return target if target.is_absolute() else dot_git_file.parent / target


def _common_of(git_dir: Path) -> Path:
    """``git_dir``'s shared common dir (its ``commondir`` file), else ``git_dir`` itself."""
    relative = _read_first_line(git_dir / "commondir")
    if not relative:
        return git_dir.resolve()
    target = Path(relative.strip())
    return (target if target.is_absolute() else git_dir / target).resolve()


def _read_first_line(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text.splitlines()[0] if text else ""


def repo_key(repo_root: Path, *, common_dir: Callable[[Path], Path | None] = git_common_dir) -> str:
    """sha256 of the realpath of ``repo_root``'s git common dir (of ``repo_root`` outside git).

    Every worktree of a clone shares the common dir, so they share approvals,
    as Claude Code shares ``settings.local.json``.

    Example::

        >>> len(repo_key(Path("/no/such/repo"), common_dir=lambda _root: None))
        64
    """
    anchor = common_dir(repo_root) or repo_root
    return hashlib.sha256(os.fsencode(os.path.realpath(anchor))).hexdigest()


def sha256_of_json(value: object) -> str:
    """sha256 of ``value`` as canonical JSON (sorted keys, no whitespace).

    How a handler's ``args`` and the execution-stage list are hashed for the store.

    Example::

        >>> sha256_of_json({"a": 1}) == sha256_of_json({"a": 1})
        True
    """
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TrustStore:
    """The approvals of one repository in the user-local trust store file at ``path``.

    ``now`` (epoch seconds) stamps ``approved_at``; ``git_common_dir`` finds the
    repo's common dir for :func:`repo_key`. Raises :class:`TrustStoreError`
    when ``path`` resolves inside ``repo_root``. Approving is a write: only an
    interactive ``playbook sync`` does it (§B.4).

    Example::

        >>> store = TrustStore(default_trust_store_path(), repo_root=Path("."))  # doctest: +SKIP
        >>> store.allows_handler("bnp-sql-pii-columns", wanted)  # doctest: +SKIP
        False
    """

    def __init__(
        self,
        path: Path,
        *,
        repo_root: Path,
        now: Callable[[], float] = time.time,
        git_common_dir: Callable[[Path], Path | None] = git_common_dir,
    ) -> None:
        if path.resolve().is_relative_to(repo_root.resolve()):
            raise TrustStoreError(
                f"trust store {str(path)!r} resolves inside the repository {str(repo_root)!r}; "
                "it must live outside it, or a clone could ship its own approvals"
            )
        self._path = path
        self._now = now
        self._key = repo_key(repo_root, common_dir=git_common_dir)

    @property
    def path(self) -> Path:
        """The store file (shared by every repository of this user)."""
        return self._path

    @property
    def repo_key(self) -> str:
        """This repository's key in the store."""
        return self._key

    def handler(self, hook_id: str) -> HandlerApproval | None:
        """The approval recorded for hook ``hook_id``'s external handler, if readable."""
        handlers = self._repo_record().get("handlers")
        return _record_of(HandlerApproval, _table(handlers).get(hook_id))

    def allows_handler(self, hook_id: str, wanted: HandlerApproval) -> bool:
        """True when ``hook_id`` was approved for exactly ``wanted``'s code."""
        approved = self.handler(hook_id)
        return approved is not None and approved.same_code(wanted)

    def approve_handler(self, hook_id: str, wanted: HandlerApproval) -> HandlerApproval:
        """Record ``wanted`` as approved now for ``hook_id``; return the stored record."""
        approved = HandlerApproval(**{**asdict(wanted), "approved_at": self._timestamp()})

        def record_handler(record: dict[str, Any]) -> None:
            record["handlers"] = {**_table(record.get("handlers")), hook_id: asdict(approved)}

        self._update(record_handler)
        return approved

    def execution(self) -> ExecutionApproval | None:
        """The approved execution-stage list, if any is recorded and readable."""
        return _record_of(ExecutionApproval, self._repo_record().get("execution"))

    def allows_execution(self, stages_sha256: str) -> bool:
        """True when the stage list hashing to ``stages_sha256`` is the approved one."""
        approved = self.execution()
        return approved is not None and approved.stages_sha256 == stages_sha256

    def approve_execution(self, stages_sha256: str) -> ExecutionApproval:
        """Record the stage list ``stages_sha256`` as approved now; return the stored record."""
        approved = ExecutionApproval(stages_sha256, self._timestamp())

        def record_execution(record: dict[str, Any]) -> None:
            record["execution"] = asdict(approved)

        self._update(record_execution)
        return approved

    def _timestamp(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._now()))

    def _repo_record(self) -> dict[str, Any]:
        """This repo's record; ``{}`` when absent or the store is unusable (grants nothing)."""
        return _table(_table((self._load() or {}).get("repos")).get(self._key))

    def _update(self, change: Callable[[dict[str, Any]], None]) -> None:
        """Apply ``change`` to this repo's record and write the whole store back atomically."""
        document = self._load()
        if document is None:
            raise TrustStoreError(
                f"trust store {str(self._path)!r} cannot be read (corrupt, a link, or writable "
                "by others); refusing to overwrite it — inspect or delete it, then sync again"
            )
        document = document or {"schema_version": TRUST_STORE_SCHEMA, "repos": {}}
        record = dict(_table(document["repos"].get(self._key)))
        change(record)
        document["repos"][self._key] = record
        _write_atomically(self._path, json.dumps(document, indent=2, sort_keys=True) + "\n")

    def _load(self) -> dict[str, Any] | None:
        """The store document: ``{}`` when absent, None when present but not trustworthy."""
        try:
            info = self._path.lstat()
        except FileNotFoundError:
            return {}
        except OSError:
            return None
        if not _owned_regular_file(info):
            return None
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            return None
        valid = isinstance(document, dict) and document.get("schema_version") == TRUST_STORE_SCHEMA
        return document if valid and isinstance(document.get("repos"), dict) else None


def _owned_regular_file(info: os.stat_result) -> bool:
    """A regular file (not a link) only this user could have written; POSIX checks only."""
    if not stat.S_ISREG(info.st_mode):
        return False
    if sys.platform == "win32":  # pragma: no cover - CI is POSIX-only (Q-D6)
        return True
    return info.st_uid == os.getuid() and not info.st_mode & _FOREIGN_WRITE_BITS


def _table(value: object) -> dict[str, Any]:
    """``value`` when it is a JSON object, else ``{}``: a mistyped entry grants nothing."""
    return value if isinstance(value, dict) else {}


def _record_of[T: (HandlerApproval, ExecutionApproval)](kind: type[T], raw: object) -> T | None:
    """``raw`` as a ``kind`` when it holds exactly its fields, all strings; else None."""
    names = {spec.name for spec in fields(kind)}
    if not isinstance(raw, dict) or set(raw) != names:
        return None
    if not all(isinstance(value, str) for value in raw.values()):
        return None
    return kind(**raw)


def _write_atomically(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` through a 0600 temp file and ``os.replace``; dir made 0700."""
    directory = path.parent
    temp = directory / f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp"
    try:
        directory.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
        directory.chmod(_DIR_MODE)  # mkdir's mode is masked by the umask
        descriptor = os.open(temp, _TEMP_FLAGS, _FILE_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(_FILE_MODE)
        os.replace(temp, path)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise TrustStoreError(f"cannot write trust store {str(path)!r}: {exc}") from exc
