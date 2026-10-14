"""Config dataclass mirroring .coding-agent-playbook.toml (SPEC §7.1).

The FileSystemStateSource (sources/filesystem.py) is responsible for loading
and writing TOML files; this module defines the in-memory shape plus the
schema checks that turn a config the engine would misread into a
:class:`ConfigError` (:func:`check_enabled_keys`, :func:`parse_output_config`).
Top-level keys ``Config`` does not model (``[hooks]``, ``[guardrails]``,
``[links]``, ``[metrics]``…) are kept verbatim in ``Config.extra_tables``.
:func:`parse_metrics_config` lives in ``metrics_config`` and is re-exported here.
"""

from __future__ import annotations

import copy
import difflib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeGuard

from coding_agent_playbook import _toml
from coding_agent_playbook.metrics_config import parse_metrics_config as parse_metrics_config

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from coding_agent_playbook.links import LinksConfig


class ConfigError(ValueError):
    """A config file the engine refuses to load (SPEC §7.1).

    Raised for content that parses as TOML in a shape the engine is known to
    misread: the enabled-list mistakes :func:`check_enabled_keys` catches and a
    malformed ``[output]`` table (:func:`parse_output_config`). Other unknown
    keys are still ignored. A ``ValueError`` subclass, so existing
    ``except ValueError`` callers still catch it; the CLI reports it as
    ``error: <message>``, exit 2.

    Example::

        >>> raise ConfigError("cfg.toml: the [overlays] table is not read")
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.ConfigError: cfg.toml: the [overlays] table is not read
    """


#: The top-level list keys ``Config`` reads, with the placeholder a fix-it hint
#: shows when there is no usable value to quote back.
_ENABLED_KEYS: dict[str, str] = {
    "overlays_enabled": "[<package names>]",
    "adapters_enabled": "[<adapter names>]",
}

#: Legacy names a user may write instead (``[overlays] enabled = [...]``, as the
#: docs once showed), mapped to the key that is actually read.
_LEGACY_NAMES: dict[str, str] = {
    "overlays": "overlays_enabled",
    "adapters": "adapters_enabled",
}

#: Where the enabled keys must go. Every fix-it hint says so: replacing a
#: ``[overlays]`` table with the key *in place* would nest it in the table above.
_PLACEMENT = "at the top of the file, above the first [table] header"

_NESTED_NOTE = "TOML puts every key written after a [table] header in that table"

#: How close a key must be to an enabled key to be refused as its misspelling.
_MISSPELLING_SIMILARITY = 0.8

#: A table path: ``()`` for the top level, ``("detector_cache", "frameworks")``…
_TablePath = tuple[str, ...]

#: The top-level keys ``Config`` reads into its own fields. Every other key goes
#: to ``Config.extra_tables`` (P6): before, a save silently deleted it.
_MODELLED_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "project",
        "engine",
        "overlays_enabled",
        "adapters_enabled",
        "storage",
        "detector_cache",
        "user_choices",
        "output",
    }
)


def check_enabled_keys(data: Mapping[str, object], *, source: str) -> None:
    """Refuse the enabled-list shapes ``Config`` would silently misread (SPEC §7.1).

    Only the top-level ``overlays_enabled`` / ``adapters_enabled`` lists of
    non-empty strings are read. Each of these was silently ignored before and is
    now refused: an ``[overlays]`` / ``[adapters]`` table (or the dotted
    ``overlays.enabled = …`` key), an enabled key written after a ``[table]``
    header (TOML nests it in that table, at any depth), and a close misspelling
    such as ``overlay_enabled``. Ignored, they read as empty lists, so
    ``playbook sync`` rendered with only ``agents_md`` and deleted the other
    adapters' earlier output as leftovers. A string value (which became a list
    of characters) and an empty name are refused too. ``source`` names the file
    in every message line; every problem found is reported in one error.

    Example::

        >>> check_enabled_keys({"adapters_enabled": ["claude_code"]}, source="cfg.toml")
        >>> check_enabled_keys({"adapters": {}}, source="cfg.toml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.ConfigError: cfg.toml: the [adapters] table is not read ...
    """
    problems = [
        problem
        for path, table in _iter_tables(data)
        for key, value in table.items()
        if (problem := _key_problem(path, key, value)) is not None
    ]
    if problems:
        raise ConfigError("\n".join(f"{source}: {problem}" for problem in problems))


def _iter_tables(
    table: Mapping[str, object], path: _TablePath = ()
) -> Iterator[tuple[_TablePath, Mapping[str, object]]]:
    """Yield ``table`` and, depth first, every table nested in it, with its path.

    Arrays of tables (``[[x]]``) are walked too, under the array's own name.
    """
    yield path, table
    for key, value in table.items():
        children = value if isinstance(value, list) else [value]
        for child in children:
            if isinstance(child, dict):
                yield from _iter_tables(child, (*path, key))


def _key_problem(path: _TablePath, key: str, value: object) -> str | None:
    """Why ``key`` (in the table at ``path``) is misread, or ``None`` when it is fine."""
    if not path and key in _ENABLED_KEYS:
        return _list_value_problem(key, value)
    target = _intended_enabled_key(path, key, value)
    return None if target is None else _misplaced_key_problem(path, key, value, target)


def _intended_enabled_key(path: _TablePath, key: str, value: object) -> str | None:
    """The enabled key ``key`` was meant as although it is not read there, else ``None``.

    A legacy name only counts nested when it holds an ``enabled`` table, so a
    framework called ``adapters`` in ``[detector_cache.frameworks]`` still loads.
    """
    if key in _ENABLED_KEYS:
        return key  # only reached nested: the top level is read as written
    if key in _LEGACY_NAMES:
        legacy = not path or (isinstance(value, dict) and "enabled" in value)
        return _LEGACY_NAMES[key] if legacy else None
    return _misspelled_enabled_key(key)


def _misspelled_enabled_key(key: str) -> str | None:
    """The enabled key ``key`` is a close misspelling of, else ``None``.

    Compared case-insensitively with ``-`` as ``_`` and the words sorted, so
    ``Overlays-Enabled`` and ``enabled_adapters`` match as well as ``overlay_enabled``.
    """
    normalized = {_normalized_key(name): name for name in _ENABLED_KEYS}
    close = difflib.get_close_matches(
        _normalized_key(key), normalized, n=1, cutoff=_MISSPELLING_SIMILARITY
    )
    return normalized[close[0]] if close else None


def _normalized_key(key: str) -> str:
    """``key`` lowercased, split on ``_``/``-``, its words sorted and rejoined with ``_``."""
    return "_".join(sorted(key.lower().replace("-", "_").split("_")))


def _misplaced_key_problem(path: _TablePath, key: str, value: object, target: str) -> str:
    """Say where ``key`` is and why it is not read, then the exact top-level line to write."""
    notes = [_NESTED_NOTE] if path else []
    if key not in _ENABLED_KEYS and key not in _LEGACY_NAMES:
        notes.append(f"did you mean {target}?")
    why = f" ({'; '.join(notes)})" if notes else ""
    listed = value.get("enabled") if isinstance(value, dict) else value
    return (
        f"{_describe_key(path, key, value)} is not read (found {value!r}){why}; "
        f"use the top-level key instead, {_PLACEMENT}: {target} = {_replacement(target, listed)}"
    )


def _describe_key(path: _TablePath, key: str, value: object) -> str:
    """``the [overlays] table``, ``the top-level key 'x'``, or ``'x' in the [engine] table``."""
    if isinstance(value, dict) and key in _LEGACY_NAMES:
        return f"the [{'.'.join((*path, key))}] table"
    if not path:
        return f"the top-level key {key!r}"
    return f"{key!r} in the [{'.'.join(path)}] table"


def _list_value_problem(key: str, value: object) -> str | None:
    """Say why ``value`` is not a usable ``key`` list, or ``None`` when it is one."""
    if not _is_str_list(value):
        replacement = _replacement(key, value)
        return f"{key} must be a list of strings, got {value!r}; write {key} = {replacement}"
    if any(not item.strip() for item in value):
        # An empty name reached importlib and crashed every command with a traceback.
        return f"{key} lists an empty name, got {value!r}; remove the empty entry"
    return None


def _replacement(key: str, listed: object) -> str:
    """The value to show in ``key = …``: ``listed`` itself when usable, else a placeholder.

    A lone string is the common slip, so it is quoted back as the one-element list.
    """
    if _is_str_list(listed):
        return _toml.format_scalar(listed)
    if isinstance(listed, str):
        return _toml.format_scalar([listed])
    return _ENABLED_KEYS[key]


def _is_str_list(value: object) -> TypeGuard[list[str]]:
    """True for a list whose every item is a ``str`` (an empty list included)."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


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

    ``extra_tables`` holds every top-level key the engine does not model, deep
    copied, so a save writes ``[hooks]``, ``[links]``, ``[metrics]``… back (P6).
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

        ``source`` names where ``data`` came from in a :class:`ConfigError`
        (:func:`check_enabled_keys`). ``FileSystemStateSource`` checks each file
        before merging them, so this re-check matters for other callers. Every
        top-level key outside ``_MODELLED_KEYS`` is deep-copied into ``extra_tables``.

        Example::

            >>> Config.from_dict({"schema_version": 1, "engine": {"version": "0.1"},
            ...                   "project": {"name": "x", "kind": "python-library"}}).project.name
            'x'
        """
        check_enabled_keys(data, source=source)
        project_data = data["project"]
        engine_data = data.get("engine", {})
        storage_data = data.get("storage")
        return cls(
            schema_version=data["schema_version"],
            project=ProjectMeta(
                name=project_data["name"],
                kind=project_data["kind"],
                description=project_data.get("description", ""),
            ),
            engine_version=engine_data["version"],
            overlays_enabled=list(data.get("overlays_enabled", [])),
            adapters_enabled=list(data.get("adapters_enabled", [])),
            storage=(
                StorageConfig(
                    artifact_source=storage_data.get("artifact_source", "filesystem"),
                    state_source=storage_data.get("state_source", "filesystem"),
                )
                if storage_data is not None
                else StorageConfig()
            ),
            detector_cache=dict(data.get("detector_cache", {})),
            user_choices=dict(data.get("user_choices", {})),
            output=parse_output_config(data["output"]) if "output" in data else None,
            extra_tables={
                key: copy.deepcopy(value)
                for key, value in data.items()
                if key not in _MODELLED_KEYS
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """The TOML table to save: modelled keys (empty optional ones omitted),
        then ``extra_tables`` — a modelled field wins over an extra of its name.

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
        for key, value in self.extra_tables.items():
            if key not in _MODELLED_KEYS:
                result[key] = copy.deepcopy(value)
        return result


def parse_links_config(data: dict[str, Any]) -> LinksConfig:
    """Parse a ``[links]`` table (already decoded from TOML) into a
    :class:`~coding_agent_playbook.links.LinksConfig` (SPEC §7.1, PR L).

    The table shape::

        [links]
        allowed_domains = ["agentharnesses.io"]   # default: [] (fully strict)

    Domains are lowercased; subdomain matching happens at check time
    (:func:`coding_agent_playbook.links.classify_link`). The import is local to
    mirror :func:`parse_metrics_config` — this module stays a pure data shape.
    """
    from coding_agent_playbook.links import LinksConfig

    raw = data.get("allowed_domains", [])
    if not isinstance(raw, list) or not all(isinstance(entry, str) for entry in raw):
        raise ValueError(f"[links] allowed_domains must be a list of strings, got {raw!r}")
    return LinksConfig(allowed_domains=tuple(entry.lower() for entry in raw))


def parse_output_config(data: object) -> OutputConfig:
    """Parse an ``[output]`` table (already decoded from TOML) into an
    :class:`OutputConfig` (SPEC §7.1).

    The table shape::

        [output]
        commit = false    # default: generated output is gitignored, local-only

    ``commit`` must be a real TOML boolean — a string like ``"false"`` is
    rejected with a :class:`ConfigError` rather than coerced (``bool("false")``
    is ``True``). Unknown keys are ignored, mirroring the other config sections.

    Example::

        >>> parse_output_config({})
        OutputConfig(commit=False)
    """
    if not isinstance(data, dict):
        raise ConfigError(f"[output] must be a table like {{commit = false}}, got {data!r}")
    commit = data.get("commit", False)
    if not isinstance(commit, bool):
        raise ConfigError(f"[output] commit must be a boolean (true or false), got {commit!r}")
    return OutputConfig(commit=commit)
