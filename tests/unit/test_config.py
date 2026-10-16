"""Tests for the Config dataclass (SPEC §7.1)."""

from __future__ import annotations

import copy
import dataclasses
import re
import sys
import tomllib
from typing import Any

import pytest

from coding_agent_playbook.config import (
    Config,
    ConfigError,
    OutputConfig,
    ProjectMeta,
    StorageConfig,
    parse_metrics_config,
    parse_output_config,
)
from coding_agent_playbook.config_entries import (
    CONFIG_MANAGED_KEYS,
    CONFIG_MANAGED_TABLE_KEYS,
    copy_toml_value,
    unmanaged_config_entries,
    with_unmanaged_entries,
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


def test_parse_ruff_violations_subtable_defaults_and_overrides():
    """prK §F.2.1: ``[metrics.ruff_violations]`` families (per-family replace), config, preview."""
    from coding_agent_playbook.evaluators.types import DEFAULT_RUFF_FAMILIES

    defaults = parse_metrics_config({})
    cfg = parse_metrics_config(
        {
            "ruff_violations": {
                "families": {"quality": ["C901", "PLR1702"], "docstrings": []},
                "config": {"lint.mccabe.max-complexity": 10, "lint.pylint.max-args": 5},
                "preview": True,
            }
        }
    )

    assert defaults.ruff_families == dict(DEFAULT_RUFF_FAMILIES)
    assert (defaults.ruff_config, defaults.ruff_preview) == ({}, False)
    assert cfg.ruff_families == {"quality": ("C901", "PLR1702")}
    assert cfg.ruff_settings.config == (
        "lint.mccabe.max-complexity=10",
        "lint.pylint.max-args=5",
    )
    assert cfg.ruff_settings.preview is True


@pytest.mark.parametrize(
    ("table", "message"),
    [
        (
            {"families": {"quality": ["C901", "c9x"]}},
            "[metrics] ruff_violations.families.quality must be a list of ruff codes like "
            "'C901', got ['C901', 'c9x']",
        ),
        (
            {"families": {"Bad Name": ["C901"]}},
            "[metrics] ruff_violations.families: bad family name 'Bad Name' "
            "(expected lowercase letters, digits and _)",
        ),
        (
            {"config": {"--select": "ALL"}},
            "[metrics] ruff_violations.config: bad ruff setting '--select' "
            "(expected a dotted name like 'lint.mccabe.max-complexity')",
        ),
        (
            {"config": {"lint.x": {"a": 1}}},
            "[metrics] ruff_violations.config.lint.x must be a string, number, boolean "
            "or a list of them, got {'a': 1}",
        ),
        ({"preview": "yes"}, "[metrics] ruff_violations.preview must be true or false, got 'yes'"),
    ],
    ids=["code", "family", "setting", "value", "preview"],
)
def test_ruff_violations_rejects_bad_codes_naming_value(table, message):
    with pytest.raises(ValueError) as excinfo:
        parse_metrics_config({"ruff_violations": table})

    assert str(excinfo.value) == message


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


def test_copy_toml_value_is_deep_and_iterative() -> None:
    """``extra_tables`` never alias the decoded file, and a header nested past the
    recursion limit (``tomllib`` accepts one) copies without ``RecursionError``."""
    source: dict[str, Any] = {"hooks": {"disable": ["x"], "rows": [{"k": 1.5}]}}
    copied = copy_toml_value(source)
    assert copied == source
    assert copied["hooks"] is not source["hooks"]
    assert copied["hooks"]["rows"][0] is not source["hooks"]["rows"][0]
    deep: dict[str, Any] = {}
    node = deep
    for _ in range(sys.getrecursionlimit() + 100):
        node["d"] = {}
        node = node["d"]
    node["leaf"] = 1
    walk = copy_toml_value(deep)
    while "d" in walk:
        walk = walk["d"]
    assert walk == {"leaf": 1}


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
    ``Config.to_dict`` → ``dump_toml`` → ``tomllib`` unchanged."""
    from coding_agent_playbook._toml import dump_toml

    config = Config.from_dict({**_MINIMAL, "metrics": copy.deepcopy(_METRICS_TABLE)})
    reread = tomllib.loads(dump_toml(config.to_dict()))
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


# --------------------------------------------------------------------------- #
# CONFIG_MANAGED_KEYS / unmanaged_config_entries — what `playbook init` rewrites
# from the Config and what it writes back verbatim (SPEC §12.1)
# --------------------------------------------------------------------------- #

_FULL: dict[str, Any] = {
    "schema_version": 1,
    "project": {"name": "x", "kind": "python-library", "description": "d"},
    "engine": {"version": "0.1.0a0"},
    "overlays_enabled": ["pkg"],
    "adapters_enabled": ["continue"],
    # Not the defaults, so dropping the table changes the Config.
    "storage": {"artifact_source": "custom", "state_source": "custom"},
    "output": {"commit": True},
    "detector_cache": {"python_version": "3.12"},
    "user_choices": {"docstring_style": "numpy"},
}


#: The managed keys ``Config.from_dict`` has no default for.
_REQUIRED_TOP_LEVEL = frozenset({"schema_version", "project", "engine"})


def _fields_left_at_default(obj: Any, prefix: str = "") -> list[str]:
    """Dotted names of ``obj``'s dataclass fields (nested ones too) still at their default.

    Required fields (no default) never count: ``from_dict`` cannot leave them out.
    """
    left: list[str] = []
    for spec in dataclasses.fields(obj):
        value = getattr(obj, spec.name)
        name = f"{prefix}{spec.name}"
        if dataclasses.is_dataclass(value):
            left += _fields_left_at_default(value, f"{name}.")
        factory: Any = spec.default_factory
        default = factory() if factory is not dataclasses.MISSING else spec.default
        if default is not dataclasses.MISSING and value == default:
            left.append(name)
    return left


def test_full_fixture_sets_every_config_field_off_its_default() -> None:
    """Derives completeness from the dataclasses, not from ``_FULL`` itself.

    A new ``Config`` (or ``ProjectMeta``/``StorageConfig``/``OutputConfig``) field
    fails here until ``_FULL`` sets it, and the key it is written under must then
    be in ``CONFIG_MANAGED_KEYS``/``CONFIG_MANAGED_TABLE_KEYS`` (tests below) —
    else ``init`` would carry the committed value over as unmanaged and override,
    or resurrect, what it computed. ``extra_tables`` is the one field no managed
    key fills: it carries the unmanaged entries (P6), so ``_FULL`` leaves it empty.
    """
    assert _fields_left_at_default(Config.from_dict(dict(_FULL))) == ["extra_tables"]


def test_config_managed_keys_are_exactly_what_to_dict_writes() -> None:
    """``to_dict`` of a fully populated Config writes every managed key, and no other,
    and reads back the same Config: every field travels under a managed key."""
    full = Config.from_dict(dict(_FULL))
    assert set(_FULL) == CONFIG_MANAGED_KEYS
    assert set(full.to_dict()) == CONFIG_MANAGED_KEYS
    assert Config.from_dict(full.to_dict()) == full


def test_managed_table_keys_are_exactly_what_to_dict_writes_in_each_table() -> None:
    written = Config.from_dict(dict(_FULL)).to_dict()
    assert set(CONFIG_MANAGED_TABLE_KEYS) <= CONFIG_MANAGED_KEYS
    for table, owned in CONFIG_MANAGED_TABLE_KEYS.items():
        assert set(written[table]) == owned, table
    nested = {"project": ProjectMeta, "storage": StorageConfig, "output": OutputConfig}
    for table, dataclass_type in nested.items():
        fields = {spec.name for spec in dataclasses.fields(dataclass_type)}
        assert CONFIG_MANAGED_TABLE_KEYS[table] == fields, table


@pytest.mark.parametrize("key", sorted(CONFIG_MANAGED_KEYS))
def test_every_managed_key_is_read_by_from_dict(key: str) -> None:
    """Dropping a managed key changes the Config, or is refused: none is dead weight."""
    without = {name: value for name, value in _FULL.items() if name != key}
    if key in _REQUIRED_TOP_LEVEL:
        with pytest.raises(ConfigError, match=rf"^c\.toml: the required key {key}\b"):
            Config.from_dict(without, source="c.toml")
        return
    assert Config.from_dict(without) != Config.from_dict(dict(_FULL))


@pytest.mark.parametrize(
    ("table", "key", "line"),
    [
        (None, "schema_version", "schema_version = 1 at the top of the file"),
        ("project", "name", 'name = "<project name>" under the [project] header'),
        ("project", "kind", 'kind = "<project kind>" under the [project] header'),
        ("engine", "version", 'version = "<engine version>" under the [engine] header'),
    ],
)
def test_a_missing_required_key_is_a_config_error_naming_file_key_and_line(
    table: str | None, key: str, line: str
) -> None:
    """Regression: was a bare ``KeyError`` traceback (exit 1) naming neither the
    file nor what to write — e.g. on an ``init`` re-run when only the local file
    supplied ``[engine] version``. Now the CLI's ``error:`` + exit 2 path."""
    data = copy.deepcopy(_FULL)
    holder: Any = data if table is None else data[table]
    del holder[key]
    dotted = key if table is None else f"{table}.{key}"
    expected = f"c.toml: the required key {dotted} is missing; write {line}"
    with pytest.raises(ConfigError, match=f"^{re.escape(expected)}$"):
        Config.from_dict(data, source="c.toml")


def test_a_non_table_project_is_a_config_error_not_a_type_error() -> None:
    with pytest.raises(ConfigError, match=r"^c\.toml: \[project\] must be a table, got 'x'; "):
        Config.from_dict({**_FULL, "project": "x"}, source="c.toml")


def test_from_dict_keeps_every_unmanaged_key_out_of_the_owned_fields() -> None:
    """Unmanaged keys change no owned field; they ride along in ``extra_tables`` (P6)."""
    extra = {"links": {"allowed_domains": ["a.com"]}, "metrics": {"mode": "both"}, "future": 1}
    config = Config.from_dict({**_FULL, **extra})
    assert dataclasses.replace(config, extra_tables={}) == Config.from_dict(dict(_FULL))
    assert config.extra_tables == extra


def test_unmanaged_config_entries_keeps_top_level_keys_config_ignores() -> None:
    links = {"allowed_domains": ["a.com"]}
    metrics = {"mode": "both", "thresholds": {"cc": {"warn": 1.5}}}
    data = {**_FULL, "links": links, "metrics": metrics, "future_scalar": 3}
    entries = unmanaged_config_entries(data)
    assert entries == {"links": links, "metrics": metrics, "future_scalar": 3}
    assert list(entries) == ["links", "metrics", "future_scalar"]  # file order kept


def test_unmanaged_config_entries_of_a_config_only_table_is_empty() -> None:
    assert unmanaged_config_entries(dict(_FULL)) == {}


#: ``_FULL`` plus a key ``Config`` does not read in each managed table.
_FULL_WITH_UNKNOWN_SUB_KEYS: dict[str, Any] = {
    **_FULL,
    "project": {**_FULL["project"], "homepage": "https://x.example"},
    "engine": {"version": "0.1.0a0", "channel": "beta"},
    "storage": {**_FULL["storage"], "cache_dir": ".cache"},
    "output": {"commit": True, "note": {"why": "legacy"}},
    "detector_cache": {"python_version": "3.12", "stale": True},
    "user_choices": {"docstring_style": "numpy", "house": "x"},
}


def test_unmanaged_config_entries_keeps_unknown_keys_of_the_managed_tables() -> None:
    """Only the four tables ``Config`` reads key by key give up their unknown keys:
    ``[detector_cache]`` is regenerated whole and ``[user_choices]`` travels in Config."""
    assert unmanaged_config_entries(_FULL_WITH_UNKNOWN_SUB_KEYS) == {
        "project": {"homepage": "https://x.example"},
        "engine": {"channel": "beta"},
        "storage": {"cache_dir": ".cache"},
        "output": {"note": {"why": "legacy"}},
    }


def test_with_unmanaged_entries_rebuilds_the_file_from_config_plus_its_entries() -> None:
    data = {**_FULL_WITH_UNKNOWN_SUB_KEYS, "links": {"allowed_domains": []}}
    data["detector_cache"] = {"python_version": "3.12"}  # regenerated whole: no stale key
    rebuilt = with_unmanaged_entries(
        dataclasses.replace(Config.from_dict(data), extra_tables={}).to_dict(),
        unmanaged_config_entries(data),
    )
    assert rebuilt == data
    assert list(rebuilt["project"]) == ["name", "kind", "description", "homepage"]
    # Config carries the same entries itself, so its own round trip is lossless too.
    assert Config.from_dict(data).to_dict() == rebuilt


def test_with_unmanaged_entries_never_brings_back_a_dropped_owned_key() -> None:
    """A description the Config dropped stays dropped; the unknown key is kept."""
    table = Config(1, ProjectMeta("x", "python-library"), "0.1").to_dict()
    entries = unmanaged_config_entries({"project": {"description": "old", "homepage": "h"}})
    assert with_unmanaged_entries(table, entries)["project"] == {
        "name": "x",
        "kind": "python-library",
        "homepage": "h",
    }


@pytest.mark.parametrize(
    ("preserved", "named"),
    [
        ({"adapters_enabled": ["x"]}, "adapters_enabled"),
        ({"user_choices": {"a": 1}}, "user_choices"),
        ({"detector_cache": {"stale": 1}}, "detector_cache"),
        ({"project": {"description": "old", "homepage": "h"}}, "project.description"),
        ({"output": {"commit": True}}, "output.commit"),
        ({"engine": "x"}, "engine"),
    ],
)
def test_with_unmanaged_entries_refuses_a_key_config_owns(
    preserved: dict[str, Any], named: str
) -> None:
    table = Config(1, ProjectMeta("x", "python-library"), "0.1").to_dict()
    with pytest.raises(
        ValueError, match=rf"^preserved entries \['{re.escape(named)}'\] are managed"
    ):
        with_unmanaged_entries(table, preserved)
