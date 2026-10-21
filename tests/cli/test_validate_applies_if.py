"""``playbook validate`` checks each ``applies_if`` key of a rule or prompt on its own.

``evaluate_predicate`` returns at the first key that does not hold, so validating a
whole predicate hid a malformed key behind a false one; hooks and
``lint_codes.when`` were already checked key by key (SPEC §6.4, §12.6).
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.validation.checks import _applies_if_errors

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

_PIPENV_MESSAGE = (
    "applies_if: predicate 'package_manager' names unknown package manager(s) ['pipenv']; "
    "expected any of ['pip', 'pip-tools', 'poetry', 'uv']"
)
_FALSE_THEN_TYPO = "  has_framework: [not-installed]\n  package_manager: pipenv\n"


def _write_rule(repo: Path, rule_id: str, applies_if_yaml: str) -> Path:
    path = repo / "playbook" / "rules" / f"{rule_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {rule_id}\nname: R\ndescription: d\nscope: scoped\n"
        f"skill: python-coding\napplies_if:\n{applies_if_yaml}---\nBody\n",
        encoding="utf-8",
    )
    return path


def _write_prompt(repo: Path, prompt_id: str, applies_if_yaml: str) -> Path:
    path = repo / "playbook" / "prompts" / f"{prompt_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {prompt_id}\nname: P\ndescription: d\nslash: {prompt_id}\n"
        f"applies_if:\n{applies_if_yaml}---\nBody\n",
        encoding="utf-8",
    )
    return path


def _fail_lines(repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    rc = _validate.run(argparse.Namespace(repo_root=str(repo)))
    out = capsys.readouterr().out
    return rc, [line for line in out.splitlines() if line.startswith("FAIL")]


def test_validate_reports_unknown_package_manager_value(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    rule = _write_rule(repo, "pm-typo", "  package_manager: pipenv\n")

    rc, fail_lines = _fail_lines(repo, capsys)

    assert rc == 1
    assert fail_lines == [f"FAIL {rule}: {_PIPENV_MESSAGE}"]


def test_validate_checks_every_applies_if_key_after_a_false_one(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    # Regression: the whole predicate returned False at has_framework, hiding the typo.
    repo = make_synthetic_repo(tmp_path)
    rule = _write_rule(repo, "hidden-typo", _FALSE_THEN_TYPO)

    rc, fail_lines = _fail_lines(repo, capsys)

    assert rc == 1
    assert fail_lines == [f"FAIL {rule}: {_PIPENV_MESSAGE}"]


def test_validate_checks_prompt_applies_if_key_after_a_false_one(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    prompt = _write_prompt(repo, "hidden-typo-prompt", _FALSE_THEN_TYPO)

    rc, fail_lines = _fail_lines(repo, capsys)

    assert rc == 1
    assert fail_lines == [f"FAIL {prompt}: {_PIPENV_MESSAGE}"]


def test_validate_accepts_a_known_package_manager_list(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    _write_rule(repo, "pm-list", "  package_manager: [uv, poetry]\n")

    rc, fail_lines = _fail_lines(repo, capsys)

    assert (rc, fail_lines) == (0, [])


def test_applies_if_errors_reports_one_error_per_bad_key(tmp_path: Path) -> None:
    predicate = {"orm_version": ">=2", "has_framework": ["x"], "package_manager": "pipenv"}

    errors = _applies_if_errors("r.md", predicate, {}, tmp_path)

    assert [(error.path, error.message) for error in errors] == [
        ("r.md", "applies_if: unknown predicate key: 'orm_version'"),
        ("r.md", _PIPENV_MESSAGE),
    ]


def test_validate_rejects_any_dependency_given_a_string(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    rule = _write_rule(repo, "dep-string", "  any_dependency: pandera\n")

    rc, fail_lines = _fail_lines(repo, capsys)

    assert rc == 1
    assert fail_lines == [
        f"FAIL {rule}: applies_if: predicate 'any_dependency' must be a list of strings; "
        "got 'pandera'"
    ]


def test_validate_still_rejects_a_misspelled_dependency_key(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    rule = _write_rule(repo, "dep-typo", "  has_dependencies: [pandera]\n")

    rc, fail_lines = _fail_lines(repo, capsys)

    assert rc == 1
    assert fail_lines == [f"FAIL {rule}: applies_if: unknown predicate key: 'has_dependencies'"]


def test_validate_accepts_the_dependency_and_any_file_keys(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    _write_rule(
        repo,
        "dep-keys",
        "  has_dependency: [anyio]\n  any_dependency: [pandera, pyjwt]\n"
        "  any_file: [mkdocs.yml, docs/conf.py]\n",
    )

    rc, fail_lines = _fail_lines(repo, capsys)

    assert (rc, fail_lines) == (0, [])
