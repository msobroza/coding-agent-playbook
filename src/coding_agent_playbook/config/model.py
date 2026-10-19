"""Config dataclass mirroring .coding-agent-playbook.toml (SPEC §7.1).

``ConfigFiles`` (config/files.py) is responsible for loading
and writing TOML files; this module defines the in-memory shape and the parsers
of its tables. The checks that turn a config the engine would misread into a
:class:`ConfigError` live in ``config.schema`` (:func:`check_config_file` here
runs every per-file one); which entries ``Config`` owns, and carrying the others
over when the committed file is rewritten, is ``config.entries``: those entries
(``[hooks]``, ``[guardrails]``, ``[links]``, ``[metrics]``…) ride along verbatim
in ``Config.extra_tables``. :func:`parse_metrics_config` lives in
``metrics_gate.config``, the ``[hooks]`` / ``[guardrails]`` parsers in
``config.tables.hooks`` and the ``[links]`` parser in ``config.tables.links``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.catalog.roots import canonical_overlay_list
from coding_agent_playbook.config.entries import (
    copy_toml_value,
    unmanaged_config_entries,
    with_unmanaged_entries,
)
from coding_agent_playbook.config.schema import (
    ConfigError,
    check_config_tables,
    check_enabled_keys,
    required_value,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def check_config_file(data: Mapping[str, object], *, source: str) -> None:
    """Every check one config file must pass on its own, before the SPEC §7.2 merge.

    The enabled lists, the tables ``Config`` reads, and ``[output] commit``; each
    error names ``source``. ``ConfigFiles`` runs it on the committed and
    the local file separately, so a local ``project = "x"`` or ``[output] commit
    = 1`` names ``.coding-agent-playbook.local.toml``, not the committed file.

    Example::

        >>> check_config_file({"output": {"commit": 1}}, source="c.toml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.schema.ConfigError: c.toml: [output] commit must be ...
    """
    check_enabled_keys(data, source=source)
    check_config_tables(data, source=source)
    if "output" in data:
        parse_output_config(data["output"], source=source)


@dataclass
class ProjectMeta:
    name: str
    kind: str
    description: str = ""


@dataclass
class StorageConfig:
    artifact_source: str = "filesystem"
    state_source: str = "filesystem"


@dataclass(frozen=True)
class OutputConfig:
    """The ``[output]`` table (SPEC §7.1): is generated output committed?

    ``commit = false`` (the default) keeps everything ``playbook sync`` renders
    local-only — gitignored through a managed ``.gitignore`` block and guarded
    by ``playbook sync --check-staged``. ``commit = true`` is the legacy policy:
    output is committed and ``playbook sync --check`` fails a commit on drift.

    Example::

        >>> parse_output_config({"commit": True})
        OutputConfig(commit=True)
    """

    commit: bool = False


@dataclass
class Config:
    """``.coding-agent-playbook.toml`` in memory (SPEC §7.1).

    ``extra_tables`` holds, deep copied, everything the file has that ``Config``
    does not own (``config.entries.unmanaged_config_entries``): every other
    top-level key — ``[hooks]``, ``[guardrails]``, ``[links]``, ``[metrics]``… —
    and, under the table's name, the unknown keys of ``[project]``/``[engine]``/
    ``[storage]``/``[output]``. ``to_dict`` writes them back, so a rewrite of the
    committed file keeps them (P6, SPEC §7.2).
    """

    schema_version: int
    project: ProjectMeta
    engine_version: str
    overlays_enabled: list[str] = field(default_factory=list)
    adapters_enabled: list[str] = field(default_factory=list)
    storage: StorageConfig = field(default_factory=StorageConfig)
    detector_cache: dict[str, Any] = field(default_factory=dict)
    user_choices: dict[str, Any] = field(default_factory=dict)
    # ``None`` = no ``[output]`` table in the TOML. Kept distinct from an
    # explicit ``OutputConfig()`` so ``to_dict`` round-trips sparsely while
    # ``playbook init`` can still write ``commit = false`` for discoverability.
    output: OutputConfig | None = None
    extra_tables: dict[str, Any] = field(default_factory=dict)
    # The deprecated ``coding_agent_playbook.packs.*`` names ``overlays_enabled``
    # was given (SPEC v0.19). Derived in ``__post_init__``; read only by
    # ``SyncContext.from_repo``'s deprecation warning; never written by ``to_dict``.
    deprecated_overlay_names: tuple[str, ...] = field(
        default=(), init=False, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        """Rewrite deprecated ``packs`` names in ``overlays_enabled`` to ``plugins``.

        Runs for ``from_dict``, direct construction and ``dataclasses.replace``
        alike, so ``deprecated_overlay_names`` always matches the list it came
        from. ``Config`` never prints; the warning is ``SyncContext.from_repo``'s.

        Example::

            >>> c = Config(1, ProjectMeta("x", "python-library"), "0.1",
            ...            overlays_enabled=["coding_agent_playbook.packs.superpowers"])
            >>> c.overlays_enabled, c.deprecated_overlay_names
            (['coding_agent_playbook.plugins.superpowers'], ('coding_agent_playbook.packs.superpowers',))
        """
        canonical, deprecated = canonical_overlay_list(self.overlays_enabled)
        self.overlays_enabled = canonical
        self.deprecated_overlay_names = deprecated

    @property
    def commit_output(self) -> bool:
        """Effective ``[output] commit`` — an absent table means ``False``.

        Example::

            >>> Config(1, ProjectMeta("x", "python-library"), "0.1").commit_output
            False
        """
        return self.output.commit if self.output is not None else False

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "config") -> Config:
        """Build a :class:`Config` from decoded TOML, refusing misread shapes.

        ``source`` names where ``data`` came from in a :class:`ConfigError`: a
        shape :func:`check_config_file` refuses (``ConfigFiles`` checks
        each file before merging them, so this re-check matters for other callers)
        or a missing required key (``schema_version``, ``[project] name``/``kind``,
        ``[engine] version``), which used to be a ``KeyError``. What ``Config``
        does not own is deep-copied into ``extra_tables``.

        Example::

            >>> Config.from_dict({"schema_version": 1, "engine": {"version": "0.1"},
            ...                   "project": {"name": "x", "kind": "python-library"}}).project.name
            'x'
        """
        check_config_file(data, source=source)
        storage = data.get("storage", {})
        return cls(
            schema_version=required_value(data, ("schema_version",), source=source),
            project=ProjectMeta(
                name=required_value(data, ("project", "name"), source=source),
                kind=required_value(data, ("project", "kind"), source=source),
                description=data["project"].get("description", ""),
            ),
            engine_version=required_value(data, ("engine", "version"), source=source),
            overlays_enabled=list(data.get("overlays_enabled", [])),
            adapters_enabled=list(data.get("adapters_enabled", [])),
            storage=StorageConfig(
                artifact_source=storage.get("artifact_source", "filesystem"),
                state_source=storage.get("state_source", "filesystem"),
            ),
            detector_cache=dict(data.get("detector_cache", {})),
            user_choices=dict(data.get("user_choices", {})),
            output=parse_output_config(data["output"], source=source) if "output" in data else None,
            extra_tables=copy_toml_value(unmanaged_config_entries(data)),
        )

    def to_dict(self) -> dict[str, Any]:
        """The TOML table to save: the owned keys (empty optional ones omitted),
        then ``extra_tables`` (``config.entries.with_unmanaged_entries``).

        An owned field always wins over an extra of the same name: only what
        ``unmanaged_config_entries`` keeps of ``extra_tables`` is written back, so
        ``extra_tables={"project": {"name": "x"}}`` cannot rename the project.

        Example::

            >>> Config(1, ProjectMeta("x", "python-library"), "0.1").to_dict()["engine"]
            {'version': '0.1'}
        """
        project: dict[str, Any] = {
            "name": self.project.name,
            "kind": self.project.kind,
            "description": self.project.description,
        }
        if not project["description"]:
            project.pop("description")
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "project": project,
            "engine": {"version": self.engine_version},
        }
        if self.overlays_enabled:
            result["overlays_enabled"] = list(self.overlays_enabled)
        if self.adapters_enabled:
            result["adapters_enabled"] = list(self.adapters_enabled)
        result["storage"] = {
            "artifact_source": self.storage.artifact_source,
            "state_source": self.storage.state_source,
        }
        if self.output is not None:
            result["output"] = {"commit": self.output.commit}
        if self.detector_cache:
            result["detector_cache"] = dict(self.detector_cache)
        if self.user_choices:
            result["user_choices"] = dict(self.user_choices)
        extras = unmanaged_config_entries(self.extra_tables)
        return with_unmanaged_entries(result, copy_toml_value(extras))


def parse_output_config(data: object, *, source: str | None = None) -> OutputConfig:
    """Parse an ``[output]`` table (already decoded from TOML) into an
    :class:`OutputConfig` (SPEC §7.1).

    The table shape::

        [output]
        commit = false    # default: generated output is gitignored, local-only

    ``commit`` must be a real TOML boolean — a string like ``"false"`` is
    rejected with a :class:`ConfigError` rather than coerced (``bool("false")``
    is ``True``). Unknown keys are ignored, mirroring the other config sections.
    ``source``, when given, prefixes the error with the file it came from, like
    every other config error.

    Example::

        >>> parse_output_config({})
        OutputConfig(commit=False)
    """
    where = f"{source}: " if source else ""
    if not isinstance(data, dict):
        raise ConfigError(f"{where}[output] must be a table like {{commit = false}}, got {data!r}")
    commit = data.get("commit", False)
    if not isinstance(commit, bool):
        raise ConfigError(
            f"{where}[output] commit must be a boolean (true or false), got {commit!r}"
        )
    return OutputConfig(commit=commit)
