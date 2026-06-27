"""Tests for the Config dataclass (SPEC §7.1)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.config import (
    Config,
    ProjectMeta,
    StorageConfig,
    parse_metrics_config,
)
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    RegressionPolicy,
)


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


# --------------------------------------------------------------------------- #
# parse_metrics_config (PR-M Track M3)
# --------------------------------------------------------------------------- #


def test_parse_metrics_config_empty_uses_defaults():
    cfg = parse_metrics_config({})
    assert cfg.mode == "regression"
    assert cfg.fail_on_breach is True
    assert cfg.strict is False
    assert cfg.run_tests is False
    assert cfg.test_cmd is None
    assert cfg.thresholds == {}
    assert cfg.regression == {}
    assert cfg.weights == {}


def test_parse_metrics_config_full_table():
    cfg = parse_metrics_config(
        {
            "mode": "both",
            "fail_on_breach": False,
            "strict": True,
            "run_tests": True,
            "test_cmd": ["python", "-m", "pytest", "-q"],
            "thresholds": {
                "cyclomatic_complexity": {"warn": 8, "fail": 16},
                # Only a fail floor (warn omitted -> None).
                "maintainability_index": {"fail": 70},
            },
            "regression": {"coverage": {"max_worsening": 0.5}},
            "weights": {"cyclomatic_complexity": 2.0},
        }
    )
    assert cfg.mode == "both"
    assert cfg.fail_on_breach is False
    assert cfg.strict is True
    assert cfg.run_tests is True
    assert cfg.test_cmd == ["python", "-m", "pytest", "-q"]
    assert cfg.thresholds["cyclomatic_complexity"] == AbsoluteThreshold(warn=8.0, fail=16.0)
    assert cfg.thresholds["maintainability_index"] == AbsoluteThreshold(warn=None, fail=70.0)
    assert cfg.regression["coverage"] == RegressionPolicy(max_worsening=0.5)
    assert cfg.weights["cyclomatic_complexity"] == 2.0


def test_parse_metrics_config_rejects_unknown_mode():
    with pytest.raises(ValueError, match="mode must be one of"):
        parse_metrics_config({"mode": "nonsense"})
