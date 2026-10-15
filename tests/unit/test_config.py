"""Tests for the Config dataclass (SPEC §7.1)."""

from __future__ import annotations

import copy
import tomllib
from typing import Any

import pytest

from coding_agent_playbook.config import (
    Config,
    OutputConfig,
    ProjectMeta,
    StorageConfig,
    parse_metrics_config,
    parse_output_config,
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


def test_parse_metrics_config_git_timeout():
    assert parse_metrics_config({}).git_timeout_s == 10.0
    assert parse_metrics_config({"git_timeout_s": 3}).git_timeout_s == 3.0
    assert parse_metrics_config({"git_timeout_s": 0.5}).git_timeout_s == 0.5


@pytest.mark.parametrize(
    "raw", [0, -1, 0.0, float("inf"), float("nan"), "10", True, None], ids=repr
)
def test_parse_metrics_config_rejects_non_positive_git_timeout(raw):
    with pytest.raises(ValueError) as excinfo:
        parse_metrics_config({"git_timeout_s": raw})

    assert str(excinfo.value) == (
        f"[metrics] git_timeout_s must be a positive number of seconds, got {raw!r}"
    )


def test_parse_metrics_config_selection_lists():
    """prK §F.0.3 item 2: ruff-shaped selection keys; names are validated by the gate."""
    cfg = parse_metrics_config(
        {"select": ["quality"], "extend_select": ["ruff_violations"], "ignore": ["lcom4"]}
    )

    assert cfg.select == ("quality",)
    assert cfg.extend_select == ("ruff_violations",)
    assert cfg.ignore == ("lcom4",)
    defaults = parse_metrics_config({})
    assert (defaults.select, defaults.extend_select, defaults.ignore) == (None, (), ())


@pytest.mark.parametrize("key", ["select", "extend_select", "ignore", "exclude"])
@pytest.mark.parametrize("raw", ["quality", ["wmc", 3], {"a": 1}, None], ids=repr)
def test_parse_metrics_config_rejects_non_string_list_naming_value(key, raw):
    with pytest.raises(ValueError) as excinfo:
        parse_metrics_config({key: raw})

    assert str(excinfo.value) == f"[metrics] {key} must be a list of strings, got {raw!r}"


def test_exclude_defaults_to_eval_fixture_globs():
    """prK §F.0.3 item 5: intentionally bad eval needle code never gates a commit."""
    from coding_agent_playbook.evaluators.paths import EVAL_FIXTURE_GLOBS
    from coding_agent_playbook.evaluators.types import MetricConfig

    assert parse_metrics_config({}).exclude == EVAL_FIXTURE_GLOBS
    assert MetricConfig().exclude == EVAL_FIXTURE_GLOBS
    assert parse_metrics_config({"exclude": []}).exclude == ()
    assert parse_metrics_config({"exclude": ["gen/**"]}).exclude == ("gen/**",)


def test_parse_metrics_config_timeouts_positive():
    assert parse_metrics_config({}).test_timeout_s is None
    assert parse_metrics_config({"test_timeout_s": 300}).test_timeout_s == 300.0
    with pytest.raises(ValueError) as excinfo:
        parse_metrics_config({"test_timeout_s": -5})

    assert str(excinfo.value) == (
        "[metrics] test_timeout_s must be a positive number of seconds, got -5"
    )


def test_parse_links_config_empty_uses_strict_default():
    from coding_agent_playbook.config import parse_links_config

    cfg = parse_links_config({})
    assert cfg.allowed_domains == ()


def test_parse_links_config_lowercases_domains():
    from coding_agent_playbook.config import parse_links_config

    cfg = parse_links_config({"allowed_domains": ["AgentHarnesses.IO", "example.com"]})
    assert cfg.allowed_domains == ("agentharnesses.io", "example.com")


def test_parse_links_config_rejects_non_list():
    from coding_agent_playbook.config import parse_links_config

    with pytest.raises(ValueError, match="allowed_domains must be a list of strings"):
        parse_links_config({"allowed_domains": "example.com"})


def test_parse_links_config_rejects_non_string_entry():
    from coding_agent_playbook.config import parse_links_config

    with pytest.raises(ValueError, match="allowed_domains must be a list of strings"):
        parse_links_config({"allowed_domains": ["ok.com", 42]})


# --------------------------------------------------------------------------- #
# [output] commit (generated output is gitignored by default)
# --------------------------------------------------------------------------- #

_MINIMAL = {
    "schema_version": 1,
    "project": {"name": "x", "kind": "python-library"},
    "engine": {"version": "0.1.0a0"},
}


def test_output_absent_defaults_to_local_only():
    config = Config.from_dict(dict(_MINIMAL))
    assert config.output is None
    assert config.commit_output is False
    assert "output" not in config.to_dict()


@pytest.mark.parametrize("commit", [True, False])
def test_output_commit_round_trips(commit):
    data = {**_MINIMAL, "output": {"commit": commit}}
    config = Config.from_dict(data)
    assert config.output == OutputConfig(commit=commit)
    assert config.commit_output is commit
    assert config.to_dict()["output"] == {"commit": commit}


def test_output_table_without_commit_key_defaults_false():
    config = Config.from_dict({**_MINIMAL, "output": {}})
    assert config.output == OutputConfig(commit=False)
    assert config.to_dict()["output"] == {"commit": False}


@pytest.mark.parametrize("bad", ["false", "no", 0, 1, None, ["true"]])
def test_output_commit_rejects_non_bool_with_value(bad):
    with pytest.raises(ValueError, match="commit must be a boolean") as exc:
        parse_output_config({"commit": bad})
    assert repr(bad) in str(exc.value)


def test_output_rejects_non_table():
    with pytest.raises(ValueError, match="must be a table") as exc:
        Config.from_dict({**_MINIMAL, "output": True})
    assert "True" in str(exc.value)


def test_output_round_trips_through_toml_dump(tmp_path):
    import tomllib

    from coding_agent_playbook.sources.filesystem import FileSystemStateSource

    config = Config(
        schema_version=1,
        project=ProjectMeta(name="x", kind="python-library"),
        engine_version="0.1.0a0",
        output=OutputConfig(commit=False),
    )
    state = FileSystemStateSource(repo_root=tmp_path)
    state.save_config(config)
    text = (tmp_path / ".coding-agent-playbook.toml").read_text()
    assert "[output]\ncommit = false" in text
    assert tomllib.loads(text)["output"] == {"commit": False}
    assert state.load_config().output == OutputConfig(commit=False)


# --------------------------------------------------------------------------- #
# extra_tables: unmodelled top-level keys survive a save (P6)
# --------------------------------------------------------------------------- #

_EXTRA_TABLES: dict[str, Any] = {
    "hooks": {
        "disabled": ["stop-ci-parity-gate"],
        "some-hook": {"enabled": False, "timeout": 2.5, "config": {"paths": ["src/"]}},
    },
    "guardrails": {"secrets": {"extra_globs": ["*.vault"]}, "unattended_ask": "deny"},
    "links": {"allowed_domains": ["agentharnesses.io"]},
    "team_note": "kept verbatim",
}


def test_extra_tables_roundtrip():
    storage = {"artifact_source": "filesystem", "state_source": "filesystem"}
    data = {**_MINIMAL, "storage": storage, **copy.deepcopy(_EXTRA_TABLES)}
    config = Config.from_dict(data)
    assert config.extra_tables == _EXTRA_TABLES
    assert config.to_dict() == data
    # Deep copies in and out: neither side aliases the other's nested tables.
    data["hooks"]["some-hook"]["enabled"] = True
    assert config.extra_tables["hooks"]["some-hook"]["enabled"] is False
    config.to_dict()["hooks"]["disabled"].append("x")
    assert config.extra_tables["hooks"]["disabled"] == ["stop-ci-parity-gate"]


def test_extra_tables_follow_the_modelled_keys():
    data = {"team_note": "n", **_MINIMAL, "hooks": {"x": {}}, "user_choices": {"a": 1}}
    keys = list(Config.from_dict(data).to_dict())
    assert keys[-2:] == ["team_note", "hooks"]


_METRICS_TABLE: dict[str, Any] = {
    "mode": "both",
    "fail_on_breach": True,
    "test_cmd": ["python", "-m", "pytest", "-q"],
    "thresholds": {
        "cyclomatic_complexity": {"warn": 10, "fail": 20},
        "maintainability_index": {"warn": 0.65, "fail": 0.5},
    },
    "regression": {"coverage": {"max_worsening": 0.5}},
    "weights": {"x": 1.0, "cyclomatic_complexity": 2.25},
}


def test_metrics_table_roundtrip():
    """A realistic ``[metrics]`` (floats, per-metric tables) survives
    ``Config.to_dict`` → ``_dump_toml`` → ``tomllib`` unchanged."""
    from coding_agent_playbook.sources.filesystem import _dump_toml

    config = Config.from_dict({**_MINIMAL, "metrics": copy.deepcopy(_METRICS_TABLE)})
    reread = tomllib.loads(_dump_toml(config.to_dict()))
    assert reread["metrics"] == _METRICS_TABLE
    assert isinstance(reread["metrics"]["weights"]["x"], float)
    assert parse_metrics_config(reread["metrics"]) == parse_metrics_config(_METRICS_TABLE)


def test_extra_tables_never_shadow_modelled_keys():
    data = {**_MINIMAL, "hooks": {"a": 1}}
    assert set(Config.from_dict(data).extra_tables) == {"hooks"}
    config = Config(
        schema_version=1,
        project=ProjectMeta(name="x", kind="python-library"),
        engine_version="0.1.0a0",
        extra_tables={"project": {"name": "evil"}, "engine": {}, "hooks": {"a": 1}},
    )
    result = config.to_dict()
    assert result["project"] == {"name": "x", "kind": "python-library"}
    assert result["engine"] == {"version": "0.1.0a0"}
    assert result["hooks"] == {"a": 1}
