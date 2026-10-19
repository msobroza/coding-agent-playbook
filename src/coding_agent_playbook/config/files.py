"""The consumer config files on disk: ``ConfigFiles``, the StateSource ABC and its filesystem source.

:class:`ConfigFiles` is the one interface to the committed config and the local
overrides (SPEC §7.1, §7.2): the per-file reads and checks, the merge, the atomic
write and the one spelling of the two filenames. :class:`CommittedDocument` also
decodes a git blob, so the guard twins read policy as committed at their base.
``StateSource`` (SPEC §20.2) is where config and lockfile live; third-party sources
register through the ``coding_agent_playbook.state_sources`` entry point, and
``FileSystemStateSource`` (SPEC §20.3) is the engine's: its config half delegates to
``ConfigFiles``. The artifact side is ``catalog/source.py``.
"""

from __future__ import annotations

import tomllib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.config.model import Config, check_config_file
from coding_agent_playbook.config.schema import ConfigError
from coding_agent_playbook.config.tables.hooks import PolicyTables, policy_tables
from coding_agent_playbook.generated_output.atomic_io import atomic_write_bytes
from coding_agent_playbook.lockfile.model import Lockfile
from coding_agent_playbook.toml_writer import dump_toml

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

#: The committed consumer config: team policy, read by every command (SPEC §7.1).
CONFIG_FILENAME: Final = ".coding-agent-playbook.toml"
#: The gitignored personal overrides, merged on top and never written back (SPEC §7.2).
CONFIG_LOCAL_FILENAME: Final = ".coding-agent-playbook.local.toml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` on top of ``base``.

    Override wins on scalars/lists; nested dicts merge key-by-key. Used to
    let ``.coding-agent-playbook.local.toml`` layer over the committed
    ``.coding-agent-playbook.toml`` per SPEC §7.2.

    On type mismatch (one side dict, the other a scalar/list), override
    wins silently. For the tables ``Config`` reads that cannot happen: each file
    is checked on its own first (``config.model.check_config_file``), so a
    ``user_choices = "x"`` in either file is refused, naming that file, before
    any merge. Other unknown keys may still be replaced whole.
    """
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _atomic_write_text(target: Path, content: str) -> None:
    """Write ``content`` to ``target`` atomically, as UTF-8 bytes.

    A SIGKILL or power loss mid-write leaves either the old file intact or the
    new file fully written — never a half-written one. Used for both
    ``.coding-agent-playbook.toml`` and ``.coding-agent-playbook.lock`` so a
    crashed ``playbook sync`` can be safely retried. It delegates to the byte
    writer because ``Path.write_text`` translates ``\\n`` on Windows.
    """
    atomic_write_bytes(target, content.encode("utf-8"))


def _read_config_file(path: Path) -> dict[str, Any]:
    """Parse one config file, refusing every shape ``Config`` would misread (SPEC §7.1).

    Each file is checked on its own, before the SPEC §7.2 deep merge, so a
    :class:`~coding_agent_playbook.config.schema.ConfigError` names the file that holds
    the mistake (``.coding-agent-playbook.local.toml: [project] must be a table …``):
    a file ``tomllib`` cannot read (:func:`_decode_toml`), an enabled-list
    shape, a table ``Config`` reads that is not one, or a malformed ``[output]``
    (``config.model.check_config_file``). Checked merged instead, a local
    ``project = "x"`` was reported against the committed file.
    """
    data = _decode_toml(path.read_bytes(), where=path.name)
    check_config_file(data, source=path.name)
    return data


def _decode_toml(raw: bytes, *, where: str) -> dict[str, Any]:
    """``raw`` decoded as TOML; bytes ``tomllib`` cannot read raise a ``ConfigError`` naming ``where``.

    Bad syntax, a non-UTF-8 byte and values nested past Python's recursion limit
    (``tomllib`` recurses into inline arrays/tables) each ended every command
    with a traceback (exit 1); the CLI now prints ``error: <where>: …`` (exit 2).
    One decoder for the worktree file and a git blob, so both say the same.

    Example::

        >>> _decode_toml(b"broken = [", where="c.toml")
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.schema.ConfigError: c.toml: invalid TOML: Invalid value (at end of document)
    """
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{where}: invalid TOML: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(
            f"{where}: not UTF-8 text ({exc.reason} at byte {exc.start}); save it as UTF-8"
        ) from exc
    except RecursionError as exc:
        raise ConfigError(
            f"{where}: inline arrays/tables nested too deeply for Python's TOML reader "
            "(it hit the recursion limit); flatten them"
        ) from exc


@dataclass(frozen=True, slots=True)
class CommittedDocument:
    """The decoded committed config, read from the worktree or from a git blob at a revision.

    Decode only: no whole-file check runs, so a policy reader never fails on a
    table it does not read. The guard twins decode the blob at the base
    revision (``git show <base>:<file>``), so a change cannot loosen the policy
    it is judged by.

    Example::

        >>> doc = CommittedDocument.decode(b"[hooks.x]\\nk = 1\\n", where="c.toml at abc123")
        >>> doc.table("hooks", "x")
        {'k': 1}
    """

    where: str
    data: Mapping[str, object]

    @classmethod
    def decode(cls, raw: bytes | None, *, where: str) -> CommittedDocument:
        """``raw`` decoded; ``None`` (no such file at that revision) is the empty document.

        Raises ``ConfigError`` naming ``where`` for bad TOML syntax, non-UTF-8 bytes
        or values nested past Python's recursion limit (``<where>: invalid TOML: …``,
        ``<where>: not UTF-8 text (…)``).

        Example::

            >>> CommittedDocument.decode(None, where="c.toml at abc123").data
            {}
        """
        return cls(where, {} if raw is None else _decode_toml(raw, where=where))

    def table(self, *path: str) -> Mapping[str, object]:
        """The table at ``path`` (``{}`` when a segment is absent).

        Raises ``ConfigError`` naming ``where`` and the path when a segment is
        present but not a table.

        Example::

            >>> CommittedDocument.decode(b"hooks = 'on'", where="c.toml").table("hooks", "x")
            Traceback (most recent call last):
            ...
            coding_agent_playbook.config.schema.ConfigError: c.toml: [hooks] must be a table, got 'on'
        """
        found: Mapping[str, object] = self.data
        for depth, key in enumerate(path, start=1):
            value = found.get(key, {})
            if not isinstance(value, dict):
                label = ".".join(path[:depth])
                raise ConfigError(f"{self.where}: [{label}] must be a table, got {value!r}")
            found = value
        return found


class ConfigFiles:
    """The committed config and the personal local overrides of one consumer repo (SPEC §7.2).

    The two files' one reader and the committed file's one writer: each file is
    checked on its own before the deep merge, so an error names the file at
    fault, and the local file is read, never written back.

    Example::

        >>> ConfigFiles(Path("/no/such/repo")).committed_table("metrics")
        {}
    """

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    @property
    def committed_path(self) -> Path:
        """``<repo_root>/.coding-agent-playbook.toml``, whether or not it exists.

        Example::

            >>> ConfigFiles(Path("/repo")).committed_path.name
            '.coding-agent-playbook.toml'
        """
        return self._repo_root / CONFIG_FILENAME

    @property
    def local_path(self) -> Path:
        """``<repo_root>/.coding-agent-playbook.local.toml``, whether or not it exists.

        Example::

            >>> ConfigFiles(Path("/repo")).local_path.name
            '.coding-agent-playbook.local.toml'
        """
        return self._repo_root / CONFIG_LOCAL_FILENAME

    def has_committed(self) -> bool:
        """Whether the committed file exists (a first ``init`` has none).

        Example::

            >>> ConfigFiles(Path("/no/such/repo")).has_committed()
            False
        """
        return self.committed_path.is_file()

    def committed(self) -> CommittedDocument:
        """The checked, decoded committed file alone: every key, the local file never read.

        Runs every per-file check (``config.model.check_config_file``), because its
        callers build a ``Config`` from it, and holds the keys ``Config`` does not
        manage (``[links]``, ``[metrics]``, ``[hooks]``…), so a rewrite carries
        them over. Raises ``FileNotFoundError`` without the file and ``ConfigError``
        naming it for one ``Config`` would misread.

        Example::

            >>> ConfigFiles(Path("/no/such/repo")).committed()
            Traceback (most recent call last):
            ...
            FileNotFoundError: missing .coding-agent-playbook.toml; run `playbook init`
        """
        if not self.has_committed():
            raise FileNotFoundError(f"missing {CONFIG_FILENAME}; run `playbook init`")
        document = self._decoded_committed()
        check_config_file(document.data, source=CONFIG_FILENAME)
        return document

    def committed_table(self, *path: str) -> Mapping[str, object]:
        """The committed table at ``path``, decoded only; ``{}`` without the file (the defaults).

        A policy reader must not fail on a table it does not read, so the
        whole-file checks of :meth:`committed` do not run: a broken ``[output]``
        never stops a ``[metrics]`` read. Raises ``ConfigError`` naming the file
        when it does not decode, or when a segment of ``path`` is not a table.

        Example::

            >>> ConfigFiles(Path("/no/such/repo")).committed_table("hooks", "commit_convention")
            {}
        """
        if not self.has_committed():
            return {}
        return self._decoded_committed().table(*path)

    def local_overrides(self) -> dict[str, Any]:
        """The checked local file, ``{}`` when it is absent.

        ``playbook init`` reads it up front, before writing anything: to check the
        local file on its own and to read the overlays its final sync will use.

        Example::

            >>> ConfigFiles(Path("/no/such/repo")).local_overrides()
            {}
        """
        return _read_config_file(self.local_path) if self.local_path.is_file() else {}

    def load(self) -> Config:
        """The effective config: the committed file with the local file merged on top (SPEC §7.2).

        What every command runs with, and never saved: writing it back would
        commit one engineer's personal overrides for the whole team. Each file is
        checked on its own first, so an error names the file at fault; what only
        the merged table can lack (a required key missing from both) names the
        committed file, where it belongs. Raises ``FileNotFoundError`` without the
        committed file.

        Example::

            >>> ConfigFiles(Path("/no/such/repo")).load()
            Traceback (most recent call last):
            ...
            FileNotFoundError: missing .coding-agent-playbook.toml; run `playbook init`
        """
        return self._merged(dict(self.committed().data), source=CONFIG_FILENAME)

    def load_committed(self) -> Config:
        """The committed file alone as a ``Config``, never merged with the local file (P6).

        Its ``extra_tables`` hold the committed ``[hooks]``/``[guardrails]`` the
        hook policy reads, so committed output never depends on a gitignored
        file. Raises like :meth:`load` for a missing or misread committed file.

        Example::

            >>> ConfigFiles(Path("/no/such/repo")).load_committed()
            Traceback (most recent call last):
            ...
            FileNotFoundError: missing .coding-agent-playbook.toml; run `playbook init`
        """
        return Config.from_dict(dict(self.committed().data), source=CONFIG_FILENAME)

    def preview(self, document: Mapping[str, Any]) -> Config:
        """What :meth:`load` will return once ``write_committed(document)`` ran; nothing written.

        ``document`` with the checked local file merged on top, through
        ``Config.from_dict``. ``init`` and ``check --refresh`` call it before
        writing, so their final guard is the config the next command will load.
        ``document`` is checked by the caller, so a ``ConfigError`` raised by the
        merge itself names the local file.

        Example::

            >>> ConfigFiles(repo).preview(rewrite.table).commit_output  # doctest: +SKIP
            False
        """
        return self._merged(dict(document), source=CONFIG_LOCAL_FILENAME)

    def write_committed(self, document: Mapping[str, Any]) -> None:
        """Atomically write ``document`` to the committed file, every entry as is.

        The committed file's only writer. Production code calls it only from
        ``config/committed.ConfigRewrite.save``, whose document is built from the
        committed file alone (pinned by ``tests/config/test_committed.py``): the
        merged :meth:`load` is never written back (SPEC §7.2). Values survive;
        comments and layout do not.

        Example::

            >>> files.write_committed({**files.committed().data, "detector_cache": {}})  # doctest: +SKIP
        """
        _atomic_write_text(self.committed_path, dump_toml(document))

    def _merged(self, committed: dict[str, Any], *, source: str) -> Config:
        """``Config`` of ``committed`` with the checked local file merged on top (SPEC §7.2)."""
        return Config.from_dict(_deep_merge(committed, self.local_overrides()), source=source)

    def _decoded_committed(self) -> CommittedDocument:
        """The committed file decoded, naming it as every command does (``CONFIG_FILENAME``)."""
        raw = self.committed_path.read_bytes()
        return CommittedDocument.decode(raw, where=CONFIG_FILENAME)


class StateSource(ABC):
    """Where config and lockfile are read from and written to."""

    name: str

    @abstractmethod
    def load_config(self) -> Config: ...

    def load_primary_config(self) -> Config:
        """The committed config alone, never merged with personal local overrides (P6).

        What :meth:`load_policy_tables` reads ``[hooks]``/``[guardrails]`` from
        (its ``extra_tables``), so committed output never depends on a gitignored
        file. Concrete, defaulting to :meth:`load_config`, so a third-party source
        that predates it still instantiates. Rewrites of the committed file go
        through ``config/committed``, which starts from ``ConfigFiles.committed``.

        Example::

            hooks_table = state_source.load_primary_config().extra_tables.get("hooks", {})
        """
        return self.load_config()

    def load_local_overrides(self) -> dict[str, Any]:
        """The per-developer table layered over the committed config; ``{}`` here.

        ``FileSystemStateSource`` returns ``.coding-agent-playbook.local.toml``.
        Concrete, so a third-party source that has no such file still instantiates.

        Example::

            >>> state_source.load_local_overrides()  # doctest: +SKIP
            {}
        """
        return {}

    def load_policy_tables(self) -> PolicyTables:
        """The ``[hooks]`` / ``[guardrails]`` tables of the committed config, kept raw.

        Never from the local overrides (specs/prK-lifecycle-hooks.md §B.1):
        committed output must not depend on a gitignored file CI never sees, so
        the local keys are only recorded, for the sync warning and validate (H21).

        Example::

            >>> state_source.load_policy_tables().hooks_config().enabled  # doctest: +SKIP
            True
        """
        return policy_tables(self.load_primary_config().extra_tables, self.load_local_overrides())

    @abstractmethod
    def save_config(self, config: Config) -> None: ...

    @abstractmethod
    def load_lockfile(self) -> Lockfile | None: ...

    @abstractmethod
    def save_lockfile(self, lockfile: Lockfile) -> None: ...


class FileSystemStateSource(StateSource):
    """Reads + writes the three TOML files in the consumer repo (SPEC §7, §14.4, §20.3).

    The ``state_sources`` entry point (L2). Every config method delegates to the
    :class:`ConfigFiles` it builds, the two config files' one reader and writer,
    so code calling them keeps working (spec B.5.3). The lockfile half
    (``.coding-agent-playbook.lock``) is its own.
    """

    name = "filesystem"

    # orchestrator.py reads the two config names off the state source (spec B.5.3);
    # the one spelling stays the module constants.
    _CONFIG_FILENAME = CONFIG_FILENAME
    _CONFIG_LOCAL_FILENAME = CONFIG_LOCAL_FILENAME
    _LOCKFILE_FILENAME = ".coding-agent-playbook.lock"

    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._files = ConfigFiles(repo_root)

    def load_config(self) -> Config:
        """The effective config, local file merged on top, never saved (:meth:`ConfigFiles.load`).

        Example: ``FileSystemStateSource(repo_root=repo).load_config().adapters_enabled``.
        """
        return self._files.load()

    def load_primary_config(self) -> Config:
        """The committed file alone as a ``Config`` (P6; :meth:`ConfigFiles.load_committed`).

        Example: ``FileSystemStateSource(repo_root=repo).load_primary_config().extra_tables``.
        """
        return self._files.load_committed()

    def load_local_overrides(self) -> dict[str, Any]:
        """The checked local file, ``{}`` when absent (:meth:`ConfigFiles.local_overrides`).

        Example: ``FileSystemStateSource(repo_root=Path("/no/repo")).load_local_overrides()`` is ``{}``.
        """
        return self._files.local_overrides()

    def has_committed_config(self) -> bool:
        """Whether the committed file exists (:meth:`ConfigFiles.has_committed`).

        Example: ``FileSystemStateSource(repo_root=Path("/no/repo")).has_committed_config()`` is False.
        """
        return self._files.has_committed()

    def read_committed_config_table(self) -> dict[str, Any]:
        """The checked committed file alone, every key, in a new dict (:meth:`ConfigFiles.committed`).

        Example: ``FileSystemStateSource(repo_root=repo).read_committed_config_table().get("links")``.
        """
        return dict(self._files.committed().data)

    def preview_config(self, table: Mapping[str, Any]) -> Config:
        """:meth:`load_config` once ``table`` is saved, nothing written (:meth:`ConfigFiles.preview`).

        Example: ``state.preview_config(rewrite.table).commit_output``.
        """
        return self._files.preview(table)

    def save_config(self, config: Config) -> None:
        """The :class:`StateSource` contract: ``config.to_dict()`` through ``write_committed``.

        A ``Config`` from :meth:`load_config` has the local file merged in, so
        saving it would commit personal overrides: no command calls this.
        ``init`` and ``check --refresh`` rewrite the committed file through
        ``config/committed`` (SPEC §7.2).

        Example: ``state.save_config(config)``.
        """
        self._files.write_committed(config.to_dict())

    def save_config_table(self, table: Mapping[str, Any]) -> None:
        """Atomically write ``table`` to the committed file as is (:meth:`ConfigFiles.write_committed`).

        Never hand it :meth:`load_config`'s merged config (SPEC §7.2); no command calls it.

        Example: ``state.save_config_table({**state.read_committed_config_table(), "x": {}})``.
        """
        self._files.write_committed(table)

    def load_lockfile(self) -> Lockfile | None:
        """Read the lockfile. Returns ``None`` if no lockfile exists (= first
        sync, no drift baseline yet). ``playbook sync --check`` treats ``None`` as
        'no comparison possible — emit a baseline'."""
        target = self._repo_root / self._LOCKFILE_FILENAME
        if not target.is_file():
            return None
        with target.open("rb") as f:
            data = tomllib.load(f)
        return Lockfile.from_dict(data)

    def save_lockfile(self, lockfile: Lockfile) -> None:
        _atomic_write_text(
            self._repo_root / self._LOCKFILE_FILENAME,
            dump_toml(lockfile.to_dict()),
        )
