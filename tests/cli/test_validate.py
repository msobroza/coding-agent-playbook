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


def _write_skill(repo: Path, dirname: str, frontmatter: str) -> None:
    skill_dir = repo / "playbook" / "skills" / dirname
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}---\nSkill body\n", encoding="utf-8")


def test_validate_accepts_valid_agent_skill(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path)
    _write_skill(repo, "query-db", "id: query-db\ndescription: Run a query\n")
    rc = _validate.run(_ns(repo))
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_validate_flags_skill_id_breaking_agent_skills_name_rule(
    tmp_path, make_synthetic_repo, capsys
):
    """OpenCode silently drops a skill whose name (= its id) fails
    ``^[a-z0-9]+(-[a-z0-9]+)*$``; validate surfaces it first."""
    repo = make_synthetic_repo(tmp_path)
    _write_skill(repo, "bad", "id: My_Skill\ndescription: Bad name\n")
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "skills/My_Skill (<repo-local>)" in out
    assert "'My_Skill' is not a valid Agent Skills name" in out


def test_validate_flags_skill_without_description(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path)
    _write_skill(repo, "no-desc", "id: no-desc\n")
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "skills/no-desc" in out
    assert "no 'description'" in out


def test_validate_flags_every_id_less_skill(tmp_path, make_synthetic_repo, capsys):
    """Id-less skills all merge under ``skill`` (all but one silently dropped, the
    survivor renamed); validate must name each one, not print ``OK``."""
    repo = make_synthetic_repo(tmp_path)
    _write_skill(repo, "pdf-tools", "name: pdf-tools\ndescription: PDF helpers\n")
    _write_skill(repo, "xlsx-tools", "name: xlsx-tools\ndescription: XLSX helpers\n")
    (repo / "playbook" / "skills" / "xlsx-tools" / "scripts").mkdir()

    rc = _validate.run(_ns(repo))

    assert rc == 1
    out = capsys.readouterr().out
    fail_lines = [line for line in out.splitlines() if line.startswith("FAIL")]
    assert len(fail_lines) == 2
    assert all("has no 'id'" in line for line in fail_lines)
    assert any("name 'pdf-tools'" in line for line in fail_lines)
    xlsx_dir = repo / "playbook" / "skills" / "xlsx-tools"
    assert any(f"name 'xlsx-tools', at {xlsx_dir}" in line for line in fail_lines)


def test_validate_flags_non_string_skill_id(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path)
    _write_skill(repo, "numeric", "id: 123\ndescription: Numeric id\n")
    rc = _validate.run(_ns(repo))
    assert rc == 1
    assert "skill 'id' must be a string, got int 123" in capsys.readouterr().out


def test_validate_warns_about_skill_files_sync_never_copies(
    tmp_path, make_synthetic_repo, capsys, monkeypatch
):
    """A skill's secret file is reported as a non-fatal warning (SPEC §17.3)."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    repo = make_synthetic_repo(tmp_path)
    _write_skill(repo, "query-db", "id: query-db\ndescription: Run a query\n")
    scripts = repo / "playbook" / "skills" / "query-db" / "scripts"
    scripts.mkdir()
    (scripts / "run.sh").write_text("echo\n", encoding="utf-8")
    (scripts / ".env").write_text("TOKEN=secret\n", encoding="utf-8")

    rc = _validate.run(_ns(repo))

    captured = capsys.readouterr()
    assert rc == 0
    assert "OK" in captured.out
    assert "warning: skills/query-db (<repo-local>):" in captured.err
    assert f"{scripts / '.env'} is never copied" in captured.err
    assert "run.sh" not in captured.err
