"""Tests for ``playbook validate`` (PR 10 Task 6).

Covers each error class documented in SPEC §12.6 plus the happy path.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import validate as _validate

if TYPE_CHECKING:
    from pathlib import Path


def _ns(repo: Path) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo))


def test_validate_clean_repo_returns_zero(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("clean-rule", "Clean body\n")],
        prompts=[("clean-prompt", {"slash": "clean", "body": "Clean prompt\n"})],
    )
    rc = _validate.run(_ns(repo))
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_validate_flags_applies_if_unknown_fact(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path)
    rules_dir = repo / "playbook" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "bad-applies-if.md").write_text(
        "---\n"
        "id: bad-applies-if\n"
        "name: Bad\n"
        "description: bad\n"
        "scope: scoped\n"
        "applies_if:\n"
        "  orm_version: '>=2'\n"
        "---\n"
        "Body\n",
        encoding="utf-8",
    )
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "applies_if" in out
    assert "orm_version" in out


def test_validate_flags_prompt_rule_call_not_in_includes_rules(
    tmp_path, make_synthetic_repo, capsys
):
    repo = make_synthetic_repo(tmp_path)
    prompts_dir = repo / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "bad-prompt.md").write_text(
        "---\n"
        "id: bad-prompt\n"
        "name: Bad\n"
        "description: Bad\n"
        "slash: bad\n"
        "---\n"
        'Some text {{ rule("python-style") }} more text.\n',
        encoding="utf-8",
    )
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "python-style" in out
    assert "includes_rules" in out


def test_validate_flags_rule_calling_rule_helper(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path)
    rules_dir = repo / "playbook" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "tries-include.md").write_text(
        "---\n"
        "id: tries-include\n"
        "name: Tries Include\n"
        "description: bad\n"
        "scope: always\n"
        "---\n"
        'Body with {{ rule("other") }} inside.\n',
        encoding="utf-8",
    )
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "rules cannot include other rules" in out


def test_validate_flags_jinja_syntax_error(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path)
    rules_dir = repo / "playbook" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "broken.md.j2").write_text(
        "---\n"
        "id: broken\n"
        "name: Broken\n"
        "description: broken\n"
        "scope: always\n"
        "---\n"
        "{% if foo %}unterminated\n",
        encoding="utf-8",
    )
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "Jinja syntax error" in out


def test_validate_flags_orphan_eval_task(tmp_path, make_synthetic_repo, capsys):
    """An on-disk task.toml referencing a non-existent prompt."""
    repo = make_synthetic_repo(tmp_path)
    task_dir = repo / "playbook" / "eval_tasks" / "orphan-task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(
        'id = "orphan-task"\n'
        'prompt_id = "deleted-prompt"\n'
        'description = "An orphan that points at a deleted prompt"\n',
        encoding="utf-8",
    )
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "deleted-prompt" in out


def test_validate_flags_missing_eval_task_for_prompt(tmp_path, make_synthetic_repo, capsys):
    """A prompt declares eval_tasks: [...] but the task dir doesn't exist."""
    repo = make_synthetic_repo(tmp_path)
    prompts_dir = repo / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "claims-task.md").write_text(
        "---\n"
        "id: claims-task\n"
        "name: Claims\n"
        "description: claims a task that does not exist\n"
        "slash: claims\n"
        "eval_tasks:\n"
        "  - foo-bar\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "foo-bar" in out
    assert "not found" in out
