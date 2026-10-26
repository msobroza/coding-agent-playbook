"""``playbook eval <id> --run`` grades v1 unless ``--prompt-set`` names another set (D76).

The repo's ``prompts`` key selects what sync renders, never what an eval run
grades: the opt-in eval comparison (D37) passes the set it compares explicitly.
Hermetic: only the ``fake`` runner runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands import eval as _eval
from coding_agent_playbook.evals.prompting import render_prompt
from coding_agent_playbook.evals.run import harness_runner
from tests.conftest import _DEFAULT_CONFIG

if TYPE_CHECKING:
    from pathlib import Path

_SHIPPED_SAMPLE = "refactor/extract-helper"


@pytest.fixture
def rendered_sets(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The prompt set of every prompt the runner renders."""
    sets: list[str] = []

    def _spy(sample: Any, **kwargs: Any) -> str:
        sets.append(kwargs.get("prompt_set", "v1"))
        return render_prompt(sample, **kwargs)

    monkeypatch.setattr(harness_runner, "render_prompt", _spy)
    return sets


def _run(repo: Path, *flags: str) -> int:
    args = build_parser().parse_args(
        ["eval", _SHIPPED_SAMPLE, "--run", "--runner", "fake", "--repo-root", str(repo), *flags]
    )
    return _eval.run(args)


def test_an_eval_run_stays_on_v1_when_the_repo_selects_v2(
    tmp_path: Path, make_synthetic_repo: Any, rendered_sets: list[str]
) -> None:
    make_synthetic_repo(tmp_path, config_text='prompts = "v2"\n' + _DEFAULT_CONFIG)
    _run(tmp_path)
    assert rendered_sets == ["v1"]


def test_prompt_set_selects_the_set_an_eval_run_grades(
    tmp_path: Path, make_synthetic_repo: Any, rendered_sets: list[str]
) -> None:
    make_synthetic_repo(tmp_path)
    _run(tmp_path, "--prompt-set", "v2")
    assert rendered_sets == ["v2"]


def test_an_unknown_prompt_set_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["eval", _SHIPPED_SAMPLE, "--run", "--prompt-set", "v3"])
    assert excinfo.value.code == 2
    assert "--prompt-set" in capsys.readouterr().err
