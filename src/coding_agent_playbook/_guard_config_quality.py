"""Sync-time config of clean-code-metrics-nonregression's post-edit companion (specs/prK-hook-pack.md §F.2.2).

The companion is the ``quality`` bucket of the §E.3 shared D1 ruff call. Its
codes are the committed ``[metrics.ruff_violations] families.quality`` and its
thresholds are ``[metrics.ruff_violations] config``, rendered as per-invocation
``--config`` overrides: one source for the post-edit bucket, the Stop stage and
the twins. An override is left out when the project's own ruff config selects
the code it tunes, because it would also move the threshold of the project's
CI-failing rule. ``[metrics]`` is team policy, so only the committed file is
read (never ``.local.toml``); a bad table falls back to the defaults, which
``playbook validate`` and ``playbook metrics`` report.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime._ruff import selector_matches

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from coding_agent_playbook._guard_config_ruff import RuffSelection

__all__ = [
    "QUALITY_HOOK_ID",
    "THRESHOLD_CODES",
    "QualityLint",
    "quality_hook_config",
    "read_quality_lint",
]

QUALITY_HOOK_ID: Final = "clean-code-metrics-nonregression"
_CONFIG_FILE: Final = ".coding-agent-playbook.toml"
_DEFAULT_CODES: Final = ("C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915")
#: ruff setting -> the rule whose threshold it sets (ruff 0.15 settings reference).
THRESHOLD_CODES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "lint.mccabe.max-complexity": "C901",
        "lint.pylint.max-returns": "PLR0911",
        "lint.pylint.max-branches": "PLR0912",
        "lint.pylint.max-args": "PLR0913",
        "lint.pylint.max-statements": "PLR0915",
        "lint.pylint.max-positional-args": "PLR0917",
        "lint.pylint.max-nested-blocks": "PLR1702",
    }
)


@dataclass(frozen=True)
class QualityLint:
    """The ``quality`` family's codes, its ``config`` thresholds and ``preview``.

    Example: ``QualityLint().codes == ("C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915")``.
    """

    codes: tuple[str, ...] = _DEFAULT_CODES
    config: Mapping[str, Any] = field(default_factory=dict)
    preview: bool = False


def read_quality_lint(repo_root: Path) -> QualityLint:
    """The committed ``[metrics.ruff_violations]`` of ``repo_root``; defaults when absent or bad.

    Example::

        >>> read_quality_lint(Path("/no/such/repo"))
        QualityLint(codes=('C901', 'PLR0911', 'PLR0912', 'PLR0913', 'PLR0915'), config={}, preview=False)
    """
    from coding_agent_playbook.metrics_gate.config import parse_metrics_config

    try:
        with (repo_root / _CONFIG_FILE).open("rb") as handle:
            table = tomllib.load(handle).get("metrics", {})
        config = parse_metrics_config(table if isinstance(table, dict) else {})
    except (OSError, tomllib.TOMLDecodeError, ValueError):
        return QualityLint()
    return QualityLint(
        codes=tuple(config.ruff_families.get("quality", ())),
        config=dict(config.ruff_config),
        preview=config.ruff_preview,
    )


def quality_hook_config(quality: QualityLint, selection: RuffSelection) -> dict[str, Any]:
    """The keys sync adds to the companion's config: its codes, ``--config`` flags, preview.

    Example::

        >>> quality_hook_config(QualityLint(config={"lint.pylint.max-args": 5}),
        ...                     RuffSelection())["ruff_config"]
        ['lint.pylint.max-args=5']
    """
    from coding_agent_playbook.metrics_gate.config import ruff_config_flags

    kept = {
        key: value
        for key, value in quality.config.items()
        if not _project_selects(selection, THRESHOLD_CODES.get(key))
    }
    return {
        "lint_codes": {"warn": list(quality.codes)},
        "ruff_config": ruff_config_flags(kept),
        "ruff_preview": quality.preview,
    }


def _project_selects(selection: RuffSelection, code: str | None) -> bool:
    """Whether the project's explicit selection takes ``code`` (and its ignore does not)."""
    if code is None:
        return False
    chosen = any(selector_matches(s, code) for s in selection.select)
    return chosen and not any(selector_matches(i, code) for i in selection.ignore)
