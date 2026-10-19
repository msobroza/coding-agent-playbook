"""The quality companion's sync-time config (specs/prK-hook-pack.md §F.2.2).

Its codes and ``--config`` thresholds come from the committed
``[metrics.ruff_violations]``, read by ``compile_guard_config`` (``test_compile``
pins the read and its defaults); an override of a code the project selects is
left out.
"""

from __future__ import annotations

from coding_agent_playbook.hooks.guard_config._tables_quality import (
    QualityLint,
    quality_hook_config,
)
from coding_agent_playbook.hooks.guard_config._tables_ruff import RuffSelection


def test_quality_hook_config_drops_override_of_project_selected_code() -> None:
    quality = QualityLint(
        codes=("C901",),
        config={"lint.mccabe.max-complexity": 10, "lint.pylint.max-args": 5, "lint.x-y": 1},
    )

    on_defaults = quality_hook_config(quality, RuffSelection())
    selecting = quality_hook_config(quality, RuffSelection(("C",), (), False))

    assert on_defaults == {
        "lint_codes": {"warn": ["C901"]},
        "ruff_config": ["lint.mccabe.max-complexity=10", "lint.pylint.max-args=5", "lint.x-y=1"],
        "ruff_preview": False,
    }
    assert selecting["ruff_config"] == ["lint.pylint.max-args=5", "lint.x-y=1"]
