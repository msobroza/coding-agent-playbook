"""The setup digest of a release metrics file and its named parts (#329 ticket 04).

No runner and no CLI: the parts are built by hand, and the scoring digest reads
a package tree the test writes, except the guard that checks the engine's own.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import coding_agent_playbook
from coding_agent_playbook.evals.judge import GRADING_PROMPT
from coding_agent_playbook.evals.setup_digest import (
    SCORING_EXEMPT,
    SCORING_MODULES,
    SCORING_PACKAGES,
    SetupParts,
    differing_setup_parts,
    scoring_digest,
    unlisted_scoring_modules,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_BASE = SetupParts(
    harness="claude_code",
    harness_version="2.1.300",
    model="claude-opus-5-5",
    endpoint_fingerprint=None,
    small_model=None,
    runs=3,
    judge_model="claude-opus-5-5",
    judge_samples=1,
    judge_version="2.1.300",
    fail_fast=True,
    isolated=True,
    scoring_digest="a" * 64,
)

#: One changed value per part: the part's name and what it becomes.
_CHANGES: Mapping[str, object] = {
    "harness": "opencode",
    "harness_version": "2.1.301",
    "model": "claude-sonnet-9-9",
    "endpoint_fingerprint": "f" * 16,
    "small_model": "claude-haiku-9-9",
    "runs": 5,
    "judge_model": "claude-sonnet-9-9",
    "judge_samples": 3,
    "judge_version": "2.1.301",
    "fail_fast": False,
    "isolated": False,
    "scoring_digest": "b" * 64,
}


def test_every_part_has_a_change_case() -> None:
    assert set(_CHANGES) == {field.name for field in dataclasses.fields(SetupParts)}


@pytest.mark.parametrize(("part", "value"), sorted(_CHANGES.items()))
def test_changing_one_part_changes_the_digest_and_is_named(part: str, value: object) -> None:
    changed = dataclasses.replace(_BASE, **{part: value})
    assert changed.digest != _BASE.digest
    assert differing_setup_parts(_BASE.as_dict(), changed.as_dict()) == (part,)


def test_equal_parts_give_the_same_digest_and_no_difference() -> None:
    same = dataclasses.replace(_BASE)
    assert same.digest == _BASE.digest
    assert re.fullmatch(r"[0-9a-f]{64}", _BASE.digest)
    assert differing_setup_parts(_BASE.as_dict(), same.as_dict()) == ()


def test_a_baseline_without_parts_differs_in_every_part() -> None:
    # A file recorded before #329 ticket 04 has no setup parts to compare with.
    assert differing_setup_parts({}, _BASE.as_dict()) == tuple(sorted(_CHANGES))


def test_parts_are_json_ready_and_keep_their_names() -> None:
    parts = _BASE.as_dict()
    assert parts["judge_samples"] == 1
    assert parts["isolated"] is True
    assert list(parts) == [field.name for field in dataclasses.fields(SetupParts)]


def _package(root: Path, files: Mapping[str, str]) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_scoring_digest_moves_with_a_listed_module_and_the_judge_prompt(tmp_path: Path) -> None:
    root = _package(tmp_path, {"grading/check.py": "X = 1\n", "grading/other.py": "Y = 1\n"})
    modules = ("grading.check",)
    before = scoring_digest(root, modules=modules, judge_prompt="grade")
    (root / "grading/other.py").write_text("Y = 2\n", encoding="utf-8")
    assert scoring_digest(root, modules=modules, judge_prompt="grade") == before
    assert scoring_digest(root, modules=modules, judge_prompt="grade it") != before
    (root / "grading/check.py").write_text("X = 2\n", encoding="utf-8")
    assert scoring_digest(root, modules=modules, judge_prompt="grade") != before


def test_scoring_digest_ignores_line_endings(tmp_path: Path) -> None:
    root = _package(tmp_path, {"grading/check.py": "X = 1\n"})
    before = scoring_digest(root, modules=("grading.check",), judge_prompt="grade")
    (root / "grading/check.py").write_bytes(b"X = 1\r\n")
    assert scoring_digest(root, modules=("grading.check",), judge_prompt="grade") == before


def test_scoring_digest_names_a_listed_module_that_is_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"grading\.gone"):
        scoring_digest(tmp_path, modules=("grading.gone",), judge_prompt="grade")


def test_the_engine_scoring_digest_covers_the_judge_prompt() -> None:
    engine = Path(coding_agent_playbook.__file__).parent
    assert scoring_digest(engine) == scoring_digest(engine, judge_prompt=GRADING_PROMPT)
    assert scoring_digest(engine) != scoring_digest(engine, judge_prompt=GRADING_PROMPT + " ")


def test_unlisted_scoring_modules_finds_new_code(tmp_path: Path) -> None:
    root = _package(
        tmp_path,
        {"grading/check.py": "", "grading/new.py": "", "grading/sub/deep.py": "", "other/x.py": ""},
    )
    found = unlisted_scoring_modules(
        root, packages=("grading",), modules=("grading.check",), exempt={"grading.new": "why"}
    )
    assert found == ("grading.sub.deep",)


def test_every_engine_scoring_module_is_listed_or_exempted() -> None:
    # New scoring code must not fall outside the setup digest silently: list it in
    # SCORING_MODULES, or exempt it in SCORING_EXEMPT with the reason it decides no score.
    engine = Path(coding_agent_playbook.__file__).parent
    assert unlisted_scoring_modules(engine) == ()


def test_listed_and_exempted_modules_exist_and_do_not_overlap() -> None:
    engine = Path(coding_agent_playbook.__file__).parent
    assert not set(SCORING_MODULES) & set(SCORING_EXEMPT)
    for module in (*SCORING_MODULES, *SCORING_EXEMPT):
        assert (engine / (module.replace(".", "/") + ".py")).is_file(), module
        assert module.startswith(tuple(f"{package}." for package in SCORING_PACKAGES)), module
    assert all(reason.strip() for reason in SCORING_EXEMPT.values())
