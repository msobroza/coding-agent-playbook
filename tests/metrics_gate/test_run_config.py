"""``load_metrics_config``: the gate's ``[metrics]`` table, read through ``ConfigFiles`` (spec B.5.5).

Only the committed file is read, decoded with the words every command prints
(``<file>: invalid TOML: …``), and none of the whole-file checks runs: a broken
``[output]`` must not stop ``playbook metrics``. Split out of ``test_run.py``,
which was past the 500-line budget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.metrics_gate.config import MetricConfig
from coding_agent_playbook.metrics_gate.run import MetricsGateUsageError, load_metrics_config

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("toml", "prefix"),
    [
        (b"[metrics]\nmode = \n", f"{CONFIG_FILENAME}: invalid TOML: "),
        (b"\xff", f"{CONFIG_FILENAME}: not UTF-8 text ("),
        (
            b"x = " + b"[" * 3000 + b"1" + b"]" * 3000 + b"\n",
            f"{CONFIG_FILENAME}: inline arrays/tables nested too deeply",
        ),
        (b'metrics = "x"\n', f"{CONFIG_FILENAME}: [metrics] must be a table, got 'x'"),
        (b'[metrics]\nmode = "sideways"\n', f"invalid [metrics] config in {CONFIG_FILENAME}: "),
    ],
    ids=["malformed", "not_utf8", "too_deep", "not_a_table", "invalid"],
)
def test_load_metrics_config_usage_errors_keep_cli_messages(
    tmp_path: Path, toml: bytes, prefix: str
) -> None:
    """A file that does not decode reads as every command prints it (spec B.5.5)."""
    (tmp_path / CONFIG_FILENAME).write_bytes(toml)

    with pytest.raises(MetricsGateUsageError) as excinfo:
        load_metrics_config(tmp_path)

    assert str(excinfo.value).startswith(prefix)


def test_load_metrics_config_never_runs_the_whole_file_checks(tmp_path: Path) -> None:
    """A broken ``[output]`` or a missing ``[project]`` must not stop ``playbook metrics``."""
    (tmp_path / CONFIG_FILENAME).write_text(
        '[output]\ncommit = "yes"\n\n[metrics]\nmode = "both"\n', encoding="utf-8"
    )

    assert load_metrics_config(tmp_path) == MetricConfig(mode="both")


def test_load_metrics_config_defaults_without_a_config_file(tmp_path: Path) -> None:
    assert load_metrics_config(tmp_path) == MetricConfig()


def test_load_metrics_config_reads_the_metrics_table(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(
        '[metrics]\nmode = "both"\nrun_tests = true\n', encoding="utf-8"
    )

    assert load_metrics_config(tmp_path) == MetricConfig(mode="both", run_tests=True)
