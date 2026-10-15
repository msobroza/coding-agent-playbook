"""Parse the ``[metrics]`` table into a ``MetricConfig`` (PR-M §E; prK §F.0.3).

Split out of ``config.py``, which re-exports :func:`parse_metrics_config`, so the
table can grow its keys without pushing ``config.py`` past its size budget. The
``evaluators`` imports stay inside the functions: every command imports
``config``, and importing ``coding_agent_playbook.evaluators`` loads the whole
metric registry.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import (
        AbsoluteThreshold,
        MetricConfig,
        RegressionPolicy,
    )

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
        git_timeout_s = 10           # bound on every git call of a git: baseline
        test_timeout_s = 300         # bound on a suite run (absent: unbounded)
        select = ["quality"]         # metric or family names (absent: the default set)
        extend_select = ["file_sloc"]
        ignore = ["lcom4"]
        exclude = ["**/eval_tasks/*/setup/**"]   # the default; a list replaces it

        [metrics.thresholds.cyclomatic_complexity]
        warn = 10
        fail = 20

        [metrics.regression.coverage]
        max_worsening = 0

        [metrics.weights]
        cyclomatic_complexity = 1.0

    Unknown keys are ignored; ``thresholds``/``regression``/``weights`` are
    per-evaluator-name dicts. Selection names are checked by the gate, which
    knows the registered metrics. Raises :class:`ValueError` naming the bad
    key and value.

    Example::

        >>> parse_metrics_config({"mode": "absolute"}).mode
        'absolute'
    """
    from coding_agent_playbook.evaluators.types import DEFAULT_GIT_TIMEOUT_S, MetricConfig

    mode = data.get("mode", "regression")
    if mode not in _VALID_METRIC_MODES:
        raise ValueError(f"[metrics] mode must be one of {_VALID_METRIC_MODES!r}, got {mode!r}")
    test_cmd_raw = data.get("test_cmd")
    defaults = MetricConfig()
    test_timeout = data.get("test_timeout_s")
    return MetricConfig(
        mode=mode,
        fail_on_breach=bool(data.get("fail_on_breach", True)),
        strict=bool(data.get("strict", False)),
        run_tests=bool(data.get("run_tests", False)),
        test_cmd=[str(part) for part in test_cmd_raw] if test_cmd_raw is not None else None,
        thresholds=_parse_thresholds(data.get("thresholds") or {}),
        regression=_parse_regression(data.get("regression") or {}),
        weights={name: float(value) for name, value in (data.get("weights") or {}).items()},
        git_timeout_s=_positive_seconds(
            "git_timeout_s", data.get("git_timeout_s", DEFAULT_GIT_TIMEOUT_S)
        ),
        select=_string_list(data, "select") if "select" in data else None,
        extend_select=_string_list(data, "extend_select", defaults.extend_select),
        ignore=_string_list(data, "ignore", defaults.ignore),
        exclude=_string_list(data, "exclude", defaults.exclude),
        test_timeout_s=None
        if test_timeout is None
        else _positive_seconds("test_timeout_s", test_timeout),
    )


def _parse_thresholds(table: dict[str, Any]) -> dict[str, AbsoluteThreshold]:
    from coding_agent_playbook.evaluators.types import AbsoluteThreshold

    return {
        name: AbsoluteThreshold(
            warn=_as_optional_float(raw.get("warn")), fail=_as_optional_float(raw.get("fail"))
        )
        for name, raw in table.items()
    }


def _parse_regression(table: dict[str, Any]) -> dict[str, RegressionPolicy]:
    from coding_agent_playbook.evaluators.types import RegressionPolicy

    return {
        name: RegressionPolicy(max_worsening=float(raw.get("max_worsening", 0.0)))
        for name, raw in table.items()
    }


def _positive_seconds(key: str, raw: object) -> float:
    """A positive, finite number of seconds: ``subprocess`` cannot wait forever.

    ``bool`` is rejected although it is an ``int``: ``git_timeout_s = true`` is a typo.
    """
    if (
        isinstance(raw, bool)
        or not isinstance(raw, int | float)
        or not (math.isfinite(raw) and raw > 0)
    ):
        raise ValueError(f"[metrics] {key} must be a positive number of seconds, got {raw!r}")
    return float(raw)


def _string_list(data: dict[str, Any], key: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    """``data[key]`` as a tuple of strings, ``default`` when the key is absent.

    A present key must be a list of strings: a bare ``select = "quality"`` would
    otherwise iterate into one-letter names.
    """
    if key not in data:
        return default
    raw = data[key]
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"[metrics] {key} must be a list of strings, got {raw!r}")
    return tuple(raw)


def _as_optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
