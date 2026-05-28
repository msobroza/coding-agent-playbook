"""Config dataclass mirroring .coding-agent-playbook.toml (SPEC §7.1).

Pure data type. The FileSystemStateSource (sources/filesystem.py) is
responsible for loading and writing TOML files; this module only defines
the in-memory shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectMeta:
    name: str
    kind: str
    description: str = ""


@dataclass
class StorageConfig:
    artifact_source: str = "filesystem"
    state_source: str = "filesystem"


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
        if self.detector_cache:
            result["detector_cache"] = dict(self.detector_cache)
        if self.user_choices:
            result["user_choices"] = dict(self.user_choices)
        return result
