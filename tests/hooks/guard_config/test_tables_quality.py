"""The quality companion's sync-time config (specs/prK-hook-pack.md §F.2.2).

Its codes and ``--config`` thresholds come from the committed
``[metrics.ruff_violations]``; an override of a code the project selects is
left out, and a bad table falls back to the defaults.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hooks.guard_config._tables_quality import (
    QualityLint,
    quality_hook_config,
    read_quality_lint,
)
from coding_agent_playbook.hooks.guard_config._tables_ruff import RuffSelection

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


@pytest.mark.parametrize(
    "committed",
    [
        b'[metrics]\nmode = "sideways"\n',
        b'metrics = "x"\n',
        b"[metrics]\nmode = \n",
        b"\xff",
    ],
    ids=["invalid-value", "not-a-table", "not-toml", "not-utf8"],
)
def test_read_quality_lint_keeps_the_defaults_for_an_invalid_metrics_value(
    tmp_path: Path, committed: bytes
) -> None:
    """Sync-time policy (spec B.14 question 2): sync reads ``[metrics]`` after its
    adapters wrote, so it keeps the defaults where ``playbook metrics`` exits 2.
    The follow-up makes ``playbook validate`` refuse the value; this pins today's
    behaviour until then."""
    (tmp_path / ".coding-agent-playbook.toml").write_bytes(committed)

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
