"""The consumer config files on disk: the StateSource ABC and its filesystem implementation.

``StateSource`` (SPEC §20.2) is where config and lockfile are read from and written
to; third-party sources register through the ``coding_agent_playbook.state_sources``
entry point declared in ``pyproject.toml``. ``FileSystemStateSource`` (SPEC §20.3)
reads and writes the three TOML files of a consumer repo. Split out of the
artifact source modules; the artifact side is ``catalog/source.py``.
"""

from __future__ import annotations

import tomllib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.config.model import Config, check_config_file
from coding_agent_playbook.config.schema import ConfigError
from coding_agent_playbook.config.tables.hooks import PolicyTables, policy_tables
from coding_agent_playbook.generated_output.atomic_io import atomic_write_bytes
from coding_agent_playbook.lockfile.model import Lockfile
from coding_agent_playbook.toml_writer import dump_toml

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


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
    a file ``tomllib`` cannot read (:func:`_decode_config_file`), an enabled-list
    shape, a table ``Config`` reads that is not one, or a malformed ``[output]``
    (``config.model.check_config_file``). Checked merged instead, a local
    ``project = "x"`` was reported against the committed file.
    """
    data = _decode_config_file(path)
    check_config_file(data, source=path.name)
    return data


def _decode_config_file(path: Path) -> dict[str, Any]:
    """``tomllib.load`` of ``path``, a file it cannot read raised as a ``ConfigError`` naming it.

    Bad syntax, a non-UTF-8 byte and values nested past Python's recursion limit
    (``tomllib`` recurses into inline arrays/tables) each ended every command
    with a traceback (exit 1); the CLI now prints ``error: <file>: …`` (exit 2).

    Example::

        >>> _decode_config_file(Path("broken.toml"))  # doctest: +SKIP
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.schema.ConfigError: broken.toml: invalid TOML: Invalid value (at end of document)
    """
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name}: invalid TOML: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(
            f"{path.name}: not UTF-8 text ({exc.reason} at byte {exc.start}); save it as UTF-8"
        ) from exc
    except RecursionError as exc:
        raise ConfigError(
            f"{path.name}: inline arrays/tables nested too deeply for Python's TOML reader "
            "(it hit the recursion limit); flatten them"
        ) from exc


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
        through ``config/committed``, which starts from
        ``FileSystemStateSource.read_committed_config_table``.

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
    """Reads + writes the three TOML files in the consumer repo:
    .coding-agent-playbook.toml, .coding-agent-playbook.local.toml,
    .coding-agent-playbook.lock (SPEC §7, §14.4, §20.3)."""

    name = "filesystem"

    _CONFIG_FILENAME = ".coding-agent-playbook.toml"
    _CONFIG_LOCAL_FILENAME = ".coding-agent-playbook.local.toml"
    _LOCKFILE_FILENAME = ".coding-agent-playbook.lock"

    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = repo_root

    def load_config(self) -> Config:
        """Read the committed config with the local overrides merged on top (SPEC §7.2).

        This is the *effective* config every command runs with, and it is never
        saved: writing it back would commit one engineer's personal overrides for
        the whole team (what ``init`` and ``check --refresh`` did before v0.18).
        Rewrites of the committed file go through ``config/committed``,
        which starts from the committed table alone (SPEC §7.2).

        Raises :class:`FileNotFoundError` without the committed file and
        :class:`~coding_agent_playbook.config.schema.ConfigError` for a shape ``Config``
        would misread — before anything else runs. Each file is checked on its
        own first, so the error names the file at fault; what only the merged
        table can lack (a required key missing from both files) names the
        committed file, where it belongs.
        """
        return self._merged_config(self.read_committed_config_table(), source=self._CONFIG_FILENAME)

    def preview_config(self, table: Mapping[str, Any]) -> Config:
        """What :meth:`load_config` will return once ``save_config_table(table)`` ran.

        ``table`` with the checked local file merged on top (SPEC §7.2), through
        ``Config.from_dict`` — and nothing written. ``init`` and ``check
        --refresh`` call it before writing, so their final guard is the config the
        next command will load. The local file's own shape is refused when it is
        read, naming it (``.coding-agent-playbook.local.toml: [project] must be a
        table …``); ``table`` is checked by the caller, so a ``ConfigError`` raised
        by the merge itself names the local file too.

        Example::

            >>> state.preview_config(rewrite.table).commit_output  # doctest: +SKIP
            False
        """
        return self._merged_config(dict(table), source=self._CONFIG_LOCAL_FILENAME)

    def _merged_config(self, committed: dict[str, Any], *, source: str) -> Config:
        """``Config`` of ``committed`` with the checked local file merged on top (SPEC §7.2)."""
        return Config.from_dict(_deep_merge(committed, self.load_local_overrides()), source=source)

    def read_committed_config_table(self) -> dict[str, Any]:
        """The checked, decoded ``.coding-agent-playbook.toml`` alone — no local overrides.

        Holds every top-level key, including those ``Config`` does not manage
        (``[links]``, ``[metrics]``, ``[hooks]``, …), so a rewrite of the committed
        file can carry them over (``config.entries.unmanaged_config_entries``).
        Raises :class:`FileNotFoundError` without the file and
        :class:`~coding_agent_playbook.config.schema.ConfigError` naming it for a shape
        ``Config`` would misread, like :meth:`load_config`.

        Example::

            >>> source = FileSystemStateSource(repo_root=Path("/no/such/repo"))
            >>> source.read_committed_config_table()  # doctest: +ELLIPSIS
            Traceback (most recent call last):
            ...
            FileNotFoundError: missing .coding-agent-playbook.toml; run `playbook init`
        """
        primary = self._repo_root / self._CONFIG_FILENAME
        if not primary.is_file():
            raise FileNotFoundError(f"missing {primary.name}; run `playbook init`")
        return _read_config_file(primary)

    def load_primary_config(self) -> Config:
        """The committed config alone, as a ``Config``: never merging ``.local.toml`` (P6).

        :meth:`read_committed_config_table` through ``Config.from_dict``, so its
        ``extra_tables`` hold the committed ``[hooks]``/``[guardrails]`` the hook
        policy reads (:meth:`StateSource.load_policy_tables`). Raises like
        :meth:`load_config` for a missing or misread committed file. Rewrites of
        the committed file go through ``config/committed``.

        Example::

            >>> FileSystemStateSource(repo_root=Path("/no/such/repo")).load_primary_config()
            Traceback (most recent call last):
            ...
            FileNotFoundError: missing .coding-agent-playbook.toml; run `playbook init`
        """
        return Config.from_dict(self.read_committed_config_table(), source=self._CONFIG_FILENAME)

    def has_committed_config(self) -> bool:
        """Whether ``.coding-agent-playbook.toml`` exists (a first ``init`` has none).

        Example::

            >>> FileSystemStateSource(repo_root=Path("/no/such/repo")).has_committed_config()
            False
        """
        return (self._repo_root / self._CONFIG_FILENAME).is_file()

    def load_local_overrides(self) -> dict[str, Any]:
        """The checked ``.coding-agent-playbook.local.toml`` table, ``{}`` when absent.

        ``playbook init`` calls it up front, before writing anything: to check the
        local file on its own and to read the overlays its final sync will use.

        Example::

            >>> FileSystemStateSource(repo_root=Path("/no/such/repo")).load_local_overrides()
            {}
        """
        local = self._repo_root / self._CONFIG_LOCAL_FILENAME
        return _read_config_file(local) if local.is_file() else {}

    def save_config(self, config: Config) -> None:
        """Atomically write ``config.to_dict()`` (``extra_tables`` included) to the committed file.

        The :class:`StateSource` contract. A ``Config`` from :meth:`load_config`
        has the local file merged in, so saving it would commit personal
        overrides: no command calls this. ``init`` and ``check --refresh`` write
        through :meth:`save_config_table`, from ``config/committed``.

        Example::

            >>> state.save_config(config)  # doctest: +SKIP
        """
        self.save_config_table(config.to_dict())

    def save_config_table(self, table: Mapping[str, Any]) -> None:
        """Atomically write the decoded ``table`` to the committed file, every entry as is.

        The committed file's only writer. Production code calls it only from
        ``config/committed.ConfigRewrite.save``, whose table is built
        from the committed file alone (pinned by
        ``tests/config/test_committed.py``): never write :meth:`load_config`'s
        merged config back (SPEC §7.2). Values survive; comments and layout do not.

        Example::

            >>> state.save_config_table({**state.read_committed_config_table(), "detector_cache": {}})  # doctest: +SKIP
        """
        _atomic_write_text(self._repo_root / self._CONFIG_FILENAME, dump_toml(table))

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
