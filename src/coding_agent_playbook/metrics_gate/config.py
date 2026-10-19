"""The ``[metrics]`` table: ``MetricConfig`` and its parser (PR-M §E; prK §F.0.3).

Split out of ``config.py`` (now ``config/model.py``), so the table can grow its
keys without pushing that module past its size budget. ``MetricConfig`` joined it
from the grading kernel's ``types.py`` (N22): only the gate side reads it, so the
kernel no longer imports this module back. Importing it loads the kernel's
``types`` (and so the metric registry); ``config.model`` does not import it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

# The eval-fixture globs are defined once, for the hooks' ``eval_fixture`` path
# class, in the stdlib leaf ``artifacts.path_classes`` (it imports only ``re``).
from coding_agent_playbook.artifacts.path_classes import FIXTURE_GLOBS
from coding_agent_playbook.evaluators.types import (
    DEFAULT_GIT_TIMEOUT_S,
    DEFAULT_RUFF_FAMILIES,
    AbsoluteThreshold,
    RegressionPolicy,
    RuffSettings,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.evaluators.types import Mode

_VALID_METRIC_MODES = ("regression", "absolute", "both")
#: A ruff rule code: a linter prefix, then digits (``C901``, ``PLR0911``, ``D100``).
_RUFF_CODE: Final = re.compile(r"[A-Z]+[0-9]+")
#: A family name: also a scope-key suffix (``src/x.py::ruff:<family>``).
_FAMILY_NAME: Final = re.compile(r"[a-z][a-z0-9_]*")
#: A dotted ruff setting (``lint.mccabe.max-complexity``): never a flag or a TOML injection.
_RUFF_SETTING: Final = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")


@dataclass
class MetricConfig:
    """Parsed ``[metrics]`` config for the standalone gate; a ``GradePolicy``.

    ``mode`` selects the comparison strategy; ``fail_on_breach`` controls the
    process exit code; ``strict`` promotes warnings to gate failures. The three
    dicts are per-evaluator overrides keyed by evaluator ``name``.
    ``git_timeout_s`` bounds every git call a ``git:`` baseline makes (prK
    §F.0.3 item 7).

    ``select`` / ``extend_select`` / ``ignore`` are the ruff-shaped metric
    selection (metric or family names; ``select=None`` is the default set, see
    :func:`~coding_agent_playbook.metrics_gate.policy.resolve_metric_selection`).
    ``exclude`` lists repo-relative globs never measured; it defaults to the
    frozen eval fixtures. ``test_timeout_s`` bounds a suite run (``None``: no
    bound). ``ruff_families`` / ``ruff_config`` / ``ruff_preview`` are
    ``[metrics.ruff_violations]`` (``ruff_config`` keeps the TOML values;
    :attr:`ruff_settings` renders them as flags).
    """

    mode: Mode = "regression"
    fail_on_breach: bool = True
    strict: bool = False
    run_tests: bool = False
    test_cmd: list[str] | None = None
    thresholds: dict[str, AbsoluteThreshold] = field(default_factory=dict)
    regression: dict[str, RegressionPolicy] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    git_timeout_s: float = DEFAULT_GIT_TIMEOUT_S
    select: tuple[str, ...] | None = None
    extend_select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    exclude: tuple[str, ...] = FIXTURE_GLOBS
    test_timeout_s: float | None = None
    ruff_families: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(DEFAULT_RUFF_FAMILIES)
    )
    ruff_config: Mapping[str, Any] = field(default_factory=dict)
    ruff_preview: bool = False

    @property
    def ruff_settings(self) -> RuffSettings:
        """The ``ruff_violations`` settings: families, rendered ``--config`` flags, preview."""
        return RuffSettings(
            families=dict(self.ruff_families),
            config=tuple(ruff_config_flags(self.ruff_config)),
            preview=self.ruff_preview,
        )


def parse_metrics_config(data: dict[str, Any]) -> MetricConfig:
    """Parse a ``[metrics]`` table (already decoded from TOML) into a
    :class:`~coding_agent_playbook.metrics_gate.config.MetricConfig` (PR-M §E).

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

        [metrics.ruff_violations]    # the opt-in ruff_violations metric (prK §F.2.1)
        families = { quality = ["C901", "PLR0915"] }   # replaces the named families only
        config = { "lint.mccabe.max-complexity" = 10 } # per-invocation --config overrides
        preview = false                                # --preview on this call only

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
    mode = data.get("mode", "regression")
    if mode not in _VALID_METRIC_MODES:
        raise ValueError(f"[metrics] mode must be one of {_VALID_METRIC_MODES!r}, got {mode!r}")
    test_cmd_raw = data.get("test_cmd")
    defaults = MetricConfig()
    test_timeout = data.get("test_timeout_s")
    ruff = _table(data, "ruff_violations")
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
        ruff_families=_ruff_families(ruff.get("families")),
        ruff_config=_ruff_config(ruff.get("config")),
        ruff_preview=_boolean("ruff_violations.preview", ruff.get("preview", False)),
    )


def ruff_config_flags(config: Mapping[str, Any]) -> list[str]:
    """``[metrics.ruff_violations] config`` as ruff ``--config`` values: ``key=<TOML literal>``.

    Keys are sorted, so the argv (and every memo keyed by it) is stable.

    Example::

        >>> ruff_config_flags({"lint.pylint.max-args": 5, "lint.mccabe.max-complexity": 10})
        ['lint.mccabe.max-complexity=10', 'lint.pylint.max-args=5']
    """
    from coding_agent_playbook.toml_writer import format_scalar

    return [f"{key}={format_scalar(config[key])}" for key in sorted(config)]


def _parse_thresholds(table: dict[str, Any]) -> dict[str, AbsoluteThreshold]:
    return {
        name: AbsoluteThreshold(
            warn=_as_optional_float(raw.get("warn")), fail=_as_optional_float(raw.get("fail"))
        )
        for name, raw in table.items()
    }


def _parse_regression(table: dict[str, Any]) -> dict[str, RegressionPolicy]:
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


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    raw = data.get(key, {})
    if not isinstance(raw, dict):
        raise ValueError(f"[metrics] {key} must be a table, got {raw!r}")
    return raw


def _boolean(key: str, raw: object) -> bool:
    if not isinstance(raw, bool):
        raise ValueError(f"[metrics] {key} must be true or false, got {raw!r}")
    return raw


def _ruff_families(raw: object) -> dict[str, tuple[str, ...]]:
    """The default families with each configured one replaced (``[]`` drops a family).

    Names and codes are checked: a family name becomes a scope key and a code
    reaches ruff's ``--select``.
    """
    families = dict(DEFAULT_RUFF_FAMILIES)
    if raw is None:
        return families
    if not isinstance(raw, dict):
        raise ValueError(f"[metrics] ruff_violations.families must be a table, got {raw!r}")
    for name, codes in raw.items():
        if not _FAMILY_NAME.fullmatch(name):
            raise ValueError(
                f"[metrics] ruff_violations.families: bad family name {name!r} "
                "(expected lowercase letters, digits and _)"
            )
        if not isinstance(codes, list) or not all(
            isinstance(code, str) and _RUFF_CODE.fullmatch(code) for code in codes
        ):
            raise ValueError(
                f"[metrics] ruff_violations.families.{name} must be a list of ruff codes "
                f"like 'C901', got {codes!r}"
            )
        families[name] = tuple(codes)
    return {name: codes for name, codes in families.items() if codes}


def _ruff_config(raw: object) -> dict[str, Any]:
    """``config``: dotted ruff settings to scalar or list values, rendered later as TOML."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"[metrics] ruff_violations.config must be a table, got {raw!r}")
    for key, value in raw.items():
        if not _RUFF_SETTING.fullmatch(key):
            raise ValueError(
                f"[metrics] ruff_violations.config: bad ruff setting {key!r} "
                "(expected a dotted name like 'lint.mccabe.max-complexity')"
            )
        if not _is_flag_value(value):
            raise ValueError(
                f"[metrics] ruff_violations.config.{key} must be a string, number, boolean "
                f"or a list of them, got {value!r}"
            )
    return dict(raw)


def _is_flag_value(value: object) -> bool:
    if isinstance(value, list):
        return all(_is_flag_value(item) and not isinstance(item, list) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, bool | int | str)


def _as_optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
