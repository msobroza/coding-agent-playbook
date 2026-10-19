"""Tests for the ``[metrics]`` table: ``MetricConfig`` and ``parse_metrics_config`` (PR-M §E)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    GradePolicy,
    RegressionPolicy,
)
from coding_agent_playbook.metrics_gate.config import MetricConfig, parse_metrics_config


def test_metric_config_defaults() -> None:
    cfg = MetricConfig()
    assert cfg.mode == "regression"
    assert cfg.fail_on_breach is True
    assert cfg.strict is False
    assert cfg.thresholds == {}
    assert cfg.regression == {}
    assert cfg.weights == {}


def test_metric_config_satisfies_grade_policy_protocol() -> None:
    cfg = MetricConfig()
    policy: GradePolicy = cfg  # structural check at type+runtime level
    assert policy.mode == "regression"


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
    from coding_agent_playbook.metrics_gate.config import MetricConfig

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
