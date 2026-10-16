"""Config dataclass mirroring .coding-agent-playbook.toml (SPEC §7.1).

The FileSystemStateSource (sources/filesystem.py) is responsible for loading
and writing TOML files; this module defines the in-memory shape and the parsers
of its tables. The checks that turn a config the engine would misread into a
:class:`ConfigError` live in ``config_schema`` (re-exported here, with
:func:`check_config_file` running every per-file one); which entries ``Config``
owns, and carrying the others over when the committed file is rewritten, is
``config_entries``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.bundled_content import canonical_overlay_list
from coding_agent_playbook.config_schema import ConfigError as ConfigError
from coding_agent_playbook.config_schema import check_config_tables as check_config_tables
from coding_agent_playbook.config_schema import check_enabled_keys as check_enabled_keys
from coding_agent_playbook.config_schema import required_value

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.evaluators.types import MetricConfig
    from coding_agent_playbook.links import LinksConfig


def check_config_file(data: Mapping[str, object], *, source: str) -> None:
    """Every check one config file must pass on its own, before the SPEC §7.2 merge.

    The enabled lists, the tables ``Config`` reads, and ``[output] commit``; each
    error names ``source``. ``FileSystemStateSource`` runs it on the committed and
    the local file separately, so a local ``project = "x"`` or ``[output] commit
    = 1`` names ``.coding-agent-playbook.local.toml``, not the committed file.

    Example::

        >>> check_config_file({"output": {"commit": 1}}, source="c.toml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config_schema.ConfigError: c.toml: [output] commit must be ...
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
    # Derived in ``__post_init__``, never read or written: the deprecated
    # ``coding_agent_playbook.packs.*`` names ``overlays_enabled`` was given, kept
    # so ``SyncContext.from_repo`` can warn about them (SPEC v0.19).
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
        shape :func:`check_config_file` refuses (``FileSystemStateSource`` checks
        each file before merging them, so this re-check matters for other callers)
        or a missing required key (``schema_version``, ``[project] name``/``kind``,
        ``[engine] version``), which used to be a ``KeyError``.

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
        )

    def to_dict(self) -> dict[str, Any]:
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
        return result


_VALID_METRIC_MODES = ("regression", "absolute", "both")


def parse_metrics_config(data: dict[str, Any]) -> MetricConfig:
    """Parse a ``[metrics]`` table (already decoded from TOML) into a
    :class:`~coding_agent_playbook.evaluators.types.MetricConfig` (PR-M §E).

    The table shape mirrors the dataclass::

        [metrics]
        mode = "regression"          # regression | absolute | both
        fail_on_breach = true
        strict = false
        run_tests = false            # reserved for M4 (execution evaluators)
        test_cmd = ["python", "-m", "pytest"]

        [metrics.thresholds.cyclomatic_complexity]
        warn = 10
        fail = 20

        [metrics.regression.coverage]
        max_worsening = 0

        [metrics.weights]
        cyclomatic_complexity = 1.0

    Unknown keys are ignored; ``thresholds``/``regression``/``weights`` are
    per-evaluator-name dicts. The import is local to avoid a config→evaluators
    import cycle (``evaluators.types`` is a leaf the command layer imports).
    """
    from coding_agent_playbook.evaluators.types import (
        AbsoluteThreshold,
        MetricConfig,
        RegressionPolicy,
    )

    mode = data.get("mode", "regression")
    if mode not in _VALID_METRIC_MODES:
        raise ValueError(f"[metrics] mode must be one of {_VALID_METRIC_MODES!r}, got {mode!r}")

    thresholds: dict[str, AbsoluteThreshold] = {}
    for name, raw in (data.get("thresholds") or {}).items():
        thresholds[name] = AbsoluteThreshold(
            warn=_as_optional_float(raw.get("warn")),
            fail=_as_optional_float(raw.get("fail")),
        )

    regression: dict[str, RegressionPolicy] = {}
    for name, raw in (data.get("regression") or {}).items():
        regression[name] = RegressionPolicy(max_worsening=float(raw.get("max_worsening", 0.0)))

    weights: dict[str, float] = {
        name: float(value) for name, value in (data.get("weights") or {}).items()
    }

    test_cmd_raw = data.get("test_cmd")
    test_cmd = [str(part) for part in test_cmd_raw] if test_cmd_raw is not None else None

    return MetricConfig(
        mode=mode,
        fail_on_breach=bool(data.get("fail_on_breach", True)),
        strict=bool(data.get("strict", False)),
        run_tests=bool(data.get("run_tests", False)),
        test_cmd=test_cmd,
        thresholds=thresholds,
        regression=regression,
        weights=weights,
    )


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


def _as_optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
