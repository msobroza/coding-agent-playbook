"""Tests for ``coding_agent_playbook.evals.loader``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.loader import load_eval_sample_from_dir
from coding_agent_playbook.evals.sample import EvalSample, Verdict

if TYPE_CHECKING:
    from pathlib import Path

_FULL_SAMPLE_TOML = """\
id = "generate-tests/happy-path"
description = "Generate tests for a simple pure function with no edge cases"

[setup]
files = ["src/calculator.py"]
project_kind = "python-application"

[invocation]
prompt_args = "for the add function in src/calculator.py"
input_variables = { target = "src/calculator.py::add" }

[gate]
expr = "created and contains and unchanged"

[gate.bind]
created = { check = "file_exists", path = "tests/test_calculator.py" }
contains = { check = "file_contains", path = "tests/test_calculator.py", pattern = "def test_add" }
unchanged = { check = "file_unchanged", path = "src/calculator.py" }

[rubric]
expr = "quality"

[rubric.bind]
quality = { fail = 0.5, rubric = [
  { judge = "Tests use pytest.parametrize for table-driven cases", weight = 0.2 },
  { judge = "Test file lives at tests/test_calculator.py (mirror layout)", weight = 0.2 },
  { judge = "All public branches of `add` are covered", weight = 0.4 },
  { judge = "No mocking is used (function is pure)", weight = 0.2 },
] }

[verdict]
trial = "gate and rubric"
"""


_ENGINE = "coding_agent_playbook"


def _load(sample_dir: Path) -> EvalSample:
    return load_eval_sample_from_dir(sample_dir, task="generate-tests", source_package=_ENGINE)


def test_load_eval_sample_from_dir_parses_well_formed_sample(tmp_path: Path) -> None:
    sample_dir = tmp_path / "generate-tests" / "happy-path"
    sample_dir.mkdir(parents=True)
    (sample_dir / "sample.toml").write_text(_FULL_SAMPLE_TOML, encoding="utf-8")

    sample = _load(sample_dir)
    assert isinstance(sample, EvalSample)
    assert sample.id == "generate-tests/happy-path"
    assert sample.prompt_id == "generate-tests"
    assert sample.source_path == sample_dir / "sample.toml"
    assert sample.source_package == "coding_agent_playbook"
    assert sample.gate is not None
    assert sample.rubric is not None
    assert set(sample.gate.bind) == {"created", "contains", "unchanged"}
    assert sample.verdict == Verdict(mode="boolean", trial="gate and rubric")
    # The loaded sample compiles cleanly into the two named layer checks.
    compiled = sample.compiled()
    assert [c.id for c in compiled.per_trial.checks] == ["gate", "rubric"]


def test_load_eval_sample_from_dir_raises_when_sample_toml_missing(tmp_path: Path) -> None:
    empty = tmp_path / "no-toml-here"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match=r"sample\.toml"):
        _load(empty)


def test_load_eval_sample_from_dir_raises_on_malformed_toml(tmp_path: Path) -> None:
    sample_dir = tmp_path / "broken-sample"
    sample_dir.mkdir()
    (sample_dir / "sample.toml").write_text("not = valid = toml = at = all\n", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        _load(sample_dir)
    assert "sample.toml" in str(excinfo.value)
    assert str(sample_dir) in str(excinfo.value)


def test_load_eval_sample_from_dir_raises_with_path_on_schema_violation(tmp_path: Path) -> None:
    sample_dir = tmp_path / "missing-fields"
    sample_dir.mkdir()
    (sample_dir / "sample.toml").write_text('description = "no id"\n', encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        _load(sample_dir)
    assert str(sample_dir / "sample.toml") in str(excinfo.value)


def test_an_id_that_does_not_match_the_directory_names_the_expected_id(tmp_path: Path) -> None:
    sample_dir = tmp_path / "generate-tests" / "other-name"
    sample_dir.mkdir(parents=True)
    (sample_dir / "sample.toml").write_text(_FULL_SAMPLE_TOML, encoding="utf-8")
    with pytest.raises(ValueError, match="has id 'generate-tests/other-name'"):
        _load(sample_dir)
