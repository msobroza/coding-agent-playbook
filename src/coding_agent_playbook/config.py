"""Config dataclass mirroring .coding-agent-playbook.toml (SPEC §7.1).

Pure data type. The FileSystemStateSource (sources/filesystem.py) is
responsible for loading and writing TOML files; this module only defines
the in-memory shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import MetricConfig
    from coding_agent_playbook.links import LinksConfig


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

    @property
    def commit_output(self) -> bool:
        """Effective ``[output] commit`` — an absent table means ``False``.

        Example::

            >>> Config(1, ProjectMeta("x", "python-library"), "0.1").commit_output
            False
        """
        return self.output.commit if self.output is not None else False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
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


def parse_output_config(data: object) -> OutputConfig:
    """Parse an ``[output]`` table (already decoded from TOML) into an
    :class:`OutputConfig` (SPEC §7.1).

    The table shape::

        [output]
        commit = false    # default: generated output is gitignored, local-only

    ``commit`` must be a real TOML boolean — a string like ``"false"`` is
    rejected rather than coerced (``bool("false")`` is ``True``). Unknown keys
    are ignored, mirroring the other config sections.

    Example::

        >>> parse_output_config({})
        OutputConfig(commit=False)
    """
    if not isinstance(data, dict):
        raise ValueError(f"[output] must be a table like {{commit = false}}, got {data!r}")
    commit = data.get("commit", False)
    if not isinstance(commit, bool):
        raise ValueError(f"[output] commit must be a boolean (true or false), got {commit!r}")
    return OutputConfig(commit=commit)


def _as_optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
