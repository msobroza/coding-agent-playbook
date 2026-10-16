"""The quality companion's sync-time config (specs/prK-hook-pack.md §F.2.2).

Its codes and ``--config`` thresholds come from the committed
``[metrics.ruff_violations]``; an override of a code the project selects is
left out, and a bad table falls back to the defaults.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook._guard_config_quality import (
    QualityLint,
    quality_hook_config,
    read_quality_lint,
)
from coding_agent_playbook._guard_config_ruff import RuffSelection

if TYPE_CHECKING:
    from pathlib import Path

_TABLE = """\
[metrics.ruff_violations]
families = { quality = ["C901", "PLR1702"] }
config = { "lint.mccabe.max-complexity" = 10, "lint.pylint.max-nested-blocks" = 3 }
preview = true
"""


def test_read_quality_lint_from_the_committed_table(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(_TABLE, encoding="utf-8")
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(
        "[metrics.ruff_violations]\npreview = false\n", encoding="utf-8"
    )

    quality = read_quality_lint(tmp_path)

    assert quality.codes == ("C901", "PLR1702")
    assert quality.preview is True  # .local.toml never applies to a tool table
    assert dict(quality.config) == {
        "lint.mccabe.max-complexity": 10,
        "lint.pylint.max-nested-blocks": 3,
    }


def test_read_quality_lint_defaults_on_absent_or_bad_table(tmp_path: Path) -> None:
    absent = read_quality_lint(tmp_path)
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        '[metrics.ruff_violations]\nfamilies = { quality = ["nope"] }\n', encoding="utf-8"
    )

    assert absent == QualityLint()
    assert read_quality_lint(tmp_path) == QualityLint()


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
