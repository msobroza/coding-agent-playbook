"""Tests for the Config dataclass (SPEC §7.1)."""

from __future__ import annotations

from coding_agent_playbook.config import Config, ProjectMeta, StorageConfig


def test_config_from_dict_minimal():
    data = {
        "schema_version": 1,
        "project": {
            "name": "my-app",
            "kind": "python-application",
        },
        "engine": {"version": "0.1.0a0"},
    }
    config = Config.from_dict(data)
    assert config.schema_version == 1
    assert config.project == ProjectMeta(name="my-app", kind="python-application")
    assert config.engine_version == "0.1.0a0"
    assert config.overlays_enabled == []
    assert config.adapters_enabled == []
    assert config.storage == StorageConfig()
    assert config.detector_cache == {}
    assert config.user_choices == {}


def test_config_roundtrip_full():
    data = {
        "schema_version": 1,
        "project": {
            "name": "my-app",
            "kind": "python-application",
            "description": "An example application",
        },
        "engine": {"version": "0.1.0a0"},
        "overlays_enabled": ["playbook-rules-bnp"],
        "adapters_enabled": ["continue", "claude_code", "agents_md"],
        "storage": {
            "artifact_source": "filesystem",
            "state_source": "filesystem",
        },
        "detector_cache": {
            "python_version": "3.12",
            "frameworks": {"fastapi": "0.110.0"},
        },
        "user_choices": {
            "banking_mode": True,
        },
    }
    config = Config.from_dict(data)
    assert config.to_dict() == data


def test_storage_section_absent_defaults_to_filesystem():
    data = {
        "schema_version": 1,
        "project": {"name": "x", "kind": "python-library"},
        "engine": {"version": "0.1.0a0"},
    }
    config = Config.from_dict(data)
    assert config.storage.artifact_source == "filesystem"
    assert config.storage.state_source == "filesystem"


def test_to_dict_omits_blank_description_and_empty_lists():
    config = Config(
        schema_version=1,
        project=ProjectMeta(name="x", kind="python-library"),
        engine_version="0.1.0a0",
    )
    result = config.to_dict()
    assert "description" not in result["project"]
    assert "overlays_enabled" not in result
    assert "adapters_enabled" not in result
    assert "detector_cache" not in result
    assert "user_choices" not in result
    assert result["storage"] == {
        "artifact_source": "filesystem",
        "state_source": "filesystem",
    }
