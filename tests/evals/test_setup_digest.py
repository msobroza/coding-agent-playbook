"""The setup digest of a release metrics file and its named parts (#329 ticket 04).

No runner and no CLI: the parts are built by hand, and the scoring digest reads
a package tree the test writes, except the guard that checks the engine's own.
"""

from __future__ import annotations

import ast
import dataclasses
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

import coding_agent_playbook
from coding_agent_playbook.evals.judge import GRADING_PROMPT
from coding_agent_playbook.evals.setup_digest import (
    SCORING_EXEMPT,
    SCORING_MODULES,
    SCORING_MODULES_OUTSIDE_PACKAGES,
    SCORING_PACKAGES,
    SCORING_TOP_LEVEL,
    UNKNOWN_VERSION,
    SetupParts,
    differing_setup_parts,
    scoring_digest,
    setups_match,
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
    judge_endpoint_fingerprint=None,
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
    "judge_endpoint_fingerprint": "e" * 16,
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
    changes: dict[str, Any] = {part: value}
    changed = dataclasses.replace(_BASE, **changes)
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


@pytest.mark.parametrize("part", ["harness_version", "judge_version"])
def test_an_unknown_version_never_matches(part: str) -> None:
    # A failed probe cannot prove the CLI unchanged (ADR 0013), even on both sides,
    # although the two digests are then equal.
    changes: dict[str, Any] = {part: UNKNOWN_VERSION}
    unknown = dataclasses.replace(_BASE, **changes)
    assert differing_setup_parts(unknown.as_dict(), unknown.as_dict()) == (part,)
    assert not setups_match(unknown.as_dict(), unknown.as_dict())
    assert unknown.digest == dataclasses.replace(unknown).digest


def test_null_versions_without_a_cli_still_match() -> None:
    no_cli = dataclasses.replace(_BASE, harness_version=None, judge_version=None)
    assert setups_match(no_cli.as_dict(), dataclasses.replace(no_cli).as_dict())


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
        root,
        packages=("grading",),
        top_level=(),
        modules=("grading.check",),
        exempt={"grading.new": "why"},
    )
    assert found == ("grading.sub.deep",)


def test_unlisted_scoring_modules_scans_top_level_modules_without_recursing(
    tmp_path: Path,
) -> None:
    # evals/judge.py once fell outside the digest: only subpackages were scanned.
    root = _package(
        tmp_path,
        {"evals/judge.py": "", "evals/new_helper.py": "", "evals/run/new_runner.py": ""},
    )
    found = unlisted_scoring_modules(
        root, packages=("evals.run",), top_level=("evals",), modules=("evals.judge",), exempt={}
    )
    assert found == ("evals.new_helper", "evals.run.new_runner")
    assert unlisted_scoring_modules(
        root, packages=(), top_level=("evals",), modules=("evals.judge",), exempt={}
    ) == ("evals.new_helper",)


def _engine_copy(tmp_path: Path, *modules: str) -> Path:
    engine = Path(coding_agent_playbook.__file__).parent
    for module in modules:
        relative = module.replace(".", "/") + ".py"
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(engine / relative, tmp_path / relative)
    return tmp_path


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_editing_the_judge_or_the_sample_model_moves_the_scoring_digest(tmp_path: Path) -> None:
    # Regression: the judge's sample averaging and the default verdict decide scores
    # but sat outside SCORING_PACKAGES, so editing them left the digest unchanged.
    assert {"evals.judge", "evals.sample"} <= set(SCORING_MODULES)
    modules = ("evals.judge", "evals.sample")
    root = _engine_copy(tmp_path, *modules)
    before = scoring_digest(root, modules=modules)
    _edit(
        root / "evals/sample.py",
        '_DEFAULT_VERDICT = "gate and rubric"',
        '_DEFAULT_VERDICT = "gate"',
    )
    after_sample = scoring_digest(root, modules=modules)
    assert after_sample != before
    _edit(
        root / "evals/judge.py",
        "total = sum(self._grade_once(criterion, artifact) for _ in range(samples))",
        "total = max(self._grade_once(criterion, artifact) for _ in range(samples))",
    )
    assert scoring_digest(root, modules=modules) not in (before, after_sample)


def test_editing_the_release_metrics_fold_moves_the_engine_scoring_digest(tmp_path: Path) -> None:
    root = _engine_copy(tmp_path, *SCORING_MODULES)
    before = scoring_digest(root)
    _edit(
        root / "evals/release_metrics.py", "statistics.pstdev(scores)", "statistics.stdev(scores)"
    )
    assert scoring_digest(root) != before


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
        assert _in_scanned_package(module), module
    assert all(reason.strip() for reason in SCORING_EXEMPT.values())
    packaged = tuple(f"{package}." for package in SCORING_PACKAGES)
    outside = {module for module in SCORING_MODULES if not module.startswith(packaged)}
    assert outside == set(SCORING_MODULES_OUTSIDE_PACKAGES)


def _in_scanned_package(module: str) -> bool:
    if module.startswith(tuple(f"{package}." for package in SCORING_PACKAGES)):
        return True
    return module.rpartition(".")[0] in SCORING_TOP_LEVEL


def _is_docstring_only(source: str) -> bool:
    body = ast.parse(source).body
    if not body or not isinstance(body[0], ast.Expr) or not isinstance(body[0].value, ast.Constant):
        return False
    rest = body[1:]
    return all(isinstance(node, ast.ImportFrom) and node.module == "__future__" for node in rest)


def test_modules_exempted_as_docstring_only_hold_only_a_docstring() -> None:
    # Code added to an exempted __init__ must not stay silently outside the digest.
    engine = Path(coding_agent_playbook.__file__).parent
    docstring_only = SCORING_EXEMPT["grading.__init__"]
    for module, reason in SCORING_EXEMPT.items():
        if reason != docstring_only:
            continue
        source = (engine / (module.replace(".", "/") + ".py")).read_text(encoding="utf-8")
        assert _is_docstring_only(source), module


def test_is_docstring_only_rejects_code() -> None:
    assert _is_docstring_only('"""Doc."""\nfrom __future__ import annotations\n')
    assert not _is_docstring_only('"""Doc."""\nX = 1\n')
    assert not _is_docstring_only("X = 1\n")
