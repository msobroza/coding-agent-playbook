"""Tests for ``playbook validate`` (PR 10 Task 6).

Covers each error class documented in SPEC §12.6 plus the happy path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import coding_agent_playbook
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.validation import context as _validate_context
from coding_agent_playbook.validation.checks import _check_output_contracts
from tests._catalog import CORE_ROOT

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


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
        "skill: python-coding\n"
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


def _write_repo_prompt(repo: Path, filename: str, frontmatter: str, body: str) -> None:
    """Write ``playbook/prompts/<filename>`` with prompt ``bad-prompt``'s frontmatter + ``body``."""
    prompts_dir = repo / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / filename).write_text(
        f"---\nid: bad-prompt\nname: Bad\ndescription: Bad\nslash: bad\n{frontmatter}---\n{body}",
        encoding="utf-8",
    )


def test_validate_rejects_any_rule_call_in_a_prompt(tmp_path, make_synthetic_repo, capsys):
    """D15: even a call to a rule ``includes_rules`` lists fails, with the migration message."""
    repo = make_synthetic_repo(tmp_path)
    _write_repo_prompt(
        repo,
        "bad-prompt.md.j2",
        "includes_rules:\n  - python-typing\n",
        'Some text {{ rule("python-typing") }} more text.\n',
    )
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert (
        "FAIL " + str(repo / "playbook" / "prompts" / "bad-prompt.md.j2") + ": body calls "
        '{{ rule("python-typing") }}; prompts no longer inline rules. Remove the call and keep '
        "'python-typing' in includes_rules: Claude Code and OpenCode commands then point at "
        "its skill, Continue appends its text\n"
    ) in out
    assert "validation failed with 1 error(s)" in out


def test_validate_flags_includes_rules_naming_no_rule(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path)
    _write_repo_prompt(repo, "bad-prompt.md", "includes_rules:\n  - python-typng\n", "Body.\n")

    assert _validate.run(_ns(repo)) == 1
    assert (
        "includes_rules names 'python-typng', which is no rule in core, an enabled overlay "
        "or playbook/rules/; did you mean 'python-typing'?"
    ) in capsys.readouterr().out


def test_validate_flags_includes_rules_that_is_not_a_list(tmp_path, make_synthetic_repo, capsys):
    """Regression: a bare string was iterated character by character."""
    repo = make_synthetic_repo(tmp_path)
    _write_repo_prompt(repo, "bad-prompt.md", "includes_rules: python-typing\n", "Body.\n")

    assert _validate.run(_ns(repo)) == 1
    out = capsys.readouterr().out
    assert (
        "includes_rules 'python-typing': expected a list of rule ids, "
        "e.g. ['python-typing', 'pytest']"
    ) in out
    assert "includes_rules names" not in out
    assert "validation failed with 1 error(s)" in out


@pytest.mark.parametrize(
    ("scope_yaml", "expected"),
    [
        ("  read_only: true\n  globs: [tests/**]\n", "got both keys"),
        ("  {}\n", None),
        ("  read_only: false\n", "read_only must be true, got False"),
        ("  globs: []\n", "globs must be a non-empty list"),
        ("  mode: read\n", "unknown key(s) ['mode']"),
        ("  globs: [tests/**, '']\n", "globs entries must be non-empty strings"),
    ],
    ids=["both", "neither", "read_only_false", "empty_globs", "unknown_key", "blank_glob"],
)
def test_write_scope_requires_exactly_one_of_read_only_or_globs(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
    scope_yaml: str,
    expected: str | None,
) -> None:
    """specs/prK-hook-pack.md §E.3: each malformed scope is one field-precise finding."""
    repo = make_synthetic_repo(tmp_path)
    prompts_dir = repo / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "scoped.md").write_text(
        "---\nid: scoped\nname: Scoped\ndescription: d\nslash: scoped\n"
        f"write_scope:\n{scope_yaml}---\nBody\n",
        encoding="utf-8",
    )

    rc = _validate.run(_ns(repo))

    out = capsys.readouterr().out
    if expected is None:  # an empty mapping is "no scope": valid
        assert rc == 0, out
        return
    assert rc == 1
    assert f"write_scope: {expected}" in out
    assert "scoped.md" in out


@pytest.mark.parametrize(
    ("codes_yaml", "expected"),
    [
        ("  warn: [E722]\n  block: [S101]\n", "lint_codes: unknown key(s) ['block']"),
        ("  warn: E722\n", "lint_codes.warn: expected a list of ruff rule codes, got 'E722'"),
        ("  warn: [E722, e7]\n", "lint_codes.warn: 'e7' is not a ruff rule code"),
        (
            "  warn: [ANN001]\n  when:\n    - applies_if: {pyver: '3.12'}\n      warn: [UP046]\n",
            "lint_codes.when[0].applies_if: ",
        ),
        (
            "  warn: [ANN001]\n  when:\n    - applies_if: {python_version: '>=3.12'}\n",
            "lint_codes.when[0]: expected exactly the keys ['applies_if', 'warn']",
        ),
        ("  warn: [ANN001]\n  when: {python_version: '>=3.12'}\n", "lint_codes.when: expected a"),
        ("  {}\n", None),
    ],
    ids=[
        "block_key",
        "warn_not_list",
        "bad_code",
        "unknown_predicate",
        "when_without_warn",
        "when_not_list",
        "empty",
    ],
)
def test_lint_codes_shape_errors_are_field_precise(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
    codes_yaml: str,
    expected: str | None,
) -> None:
    """specs/prK-lifecycle-hooks.md §A.7: each malformed ``lint_codes`` names the field and value."""
    repo = make_synthetic_repo(tmp_path)
    rules_dir = repo / "playbook" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "linted.md").write_text(
        "---\nid: linted\nname: Linted\ndescription: d\nscope: always\n"
        f"lint_codes:\n{codes_yaml}---\nBody\n",
        encoding="utf-8",
    )

    rc = _validate.run(_ns(repo))

    out = capsys.readouterr().out
    if expected is None:  # an empty mapping is "no codes": valid
        assert rc == 0, out
        return
    assert rc == 1
    assert expected in out
    assert "linted.md" in out


def test_validate_rejects_rule_call_with_trim_markers(tmp_path, make_synthetic_repo, capsys):
    """``validate`` shares the renderer's rule-call pattern, so a trim-marker spelling fails too."""
    repo = make_synthetic_repo(tmp_path)
    _write_repo_prompt(
        repo,
        "bad-prompt.md.j2",
        "includes_rules:\n  - python-typing\n",
        "Some text {{- rule('python-typing') -}} more text.\n",
    )
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "Remove the call and keep 'python-typing' in includes_rules" in out


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


def test_invalid_output_contract_regex_fails_validate(tmp_path, make_synthetic_repo, capsys):
    """A contract that does not compile fails closed, naming the pattern and the shape."""
    repo = make_synthetic_repo(tmp_path)
    prompts_dir = repo / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "bad-contract.md").write_text(
        "---\n"
        "id: bad-contract\n"
        "name: Bad\n"
        "description: Bad\n"
        "slash: bad-contract\n"
        "output_contract:\n"
        "  - '(?i)verdict: (approve'\n"
        "---\n"
        "Review it.\n",
        encoding="utf-8",
    )

    rc = _validate.run(_ns(repo))

    out = capsys.readouterr().out
    assert rc == 1
    assert "output_contract pattern '(?i)verdict: (approve'" in out
    assert "expected a list of Python regular expressions" in out


@pytest.mark.catalog
def test_shipped_prompt_contracts_compile() -> None:
    """The engine's review, security-review and find-injected-vulnerability contracts compile."""
    import re

    from coding_agent_playbook.artifacts.prompt import Prompt

    root = CORE_ROOT / "prompts"
    contracts = {
        path.name.split(".")[0]: Prompt.from_markdown(path, "pkg").frontmatter.output_contract
        for path in sorted(root.glob("*.md*"))
    }

    with_contract = {name for name, contract in contracts.items() if contract}
    assert with_contract == {"review", "security-review", "find-injected-vulnerability"}
    for contract in contracts.values():
        assert all(re.compile(pattern) for pattern in contract)
    assert (
        _check_output_contracts(  # the validate rule itself agrees
            [Prompt.from_markdown(path, "pkg") for path in sorted(root.glob("*.md*"))]
        )
        == []
    )


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


# --- Config-less validate (specs/prK-lifecycle-hooks.md §P P8a) -----------------

_UNKNOWN_FACT_RULE = (
    "---\nid: bad\nname: Bad\ndescription: bad\nscope: scoped\n"
    "skill: python-coding\napplies_if:\n  orm_version: '>=2'\n---\nBody\n"
)


def _engine_artifact_count(repo: Path) -> int:
    """Rules + prompts + hooks the engine package resolves to (ids are unique per kind)."""
    engine = FileSystemArtifactSource(repo_root=repo)
    rule_ids = {rule.frontmatter.id for rule in engine.list_rules()}
    prompt_ids = {prompt.frontmatter.id for prompt in engine.list_prompts()}
    hook_ids = {hook.frontmatter.id for hook in engine.list_hooks()}
    return len(rule_ids) + len(prompt_ids) + len(hook_ids)


def test_validate_without_config_checks_engine_resources(tmp_path, capsys):
    """An engine or overlay checkout has no consumer config: validate must not
    raise FileNotFoundError, and still validates the engine and ``playbook/``."""
    assert _validate.run(_ns(tmp_path)) == 0
    out = capsys.readouterr().out
    assert f"OK {_engine_artifact_count(tmp_path)} artifacts validated" in out
    assert "no .coding-agent-playbook.toml" in out

    bad = tmp_path / "playbook" / "rules" / "bad.md"
    bad.parent.mkdir(parents=True)
    bad.write_text(_UNKNOWN_FACT_RULE, encoding="utf-8")

    assert _validate.run(_ns(tmp_path)) == 1
    fail_lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("FAIL")]
    assert fail_lines == [f"FAIL {bad}: applies_if: unknown predicate key: 'orm_version'"]


def test_validate_without_config_checks_checkout_resources(tmp_path, capsys):
    """An overlay checkout's own ``src/<pkg>/resources/`` is a validated layer."""
    rule = tmp_path / "src" / "acme_overlay" / "resources" / "rules" / "x.md"
    rule.parent.mkdir(parents=True)
    rule.write_text(
        "---\nid: x\nname: X\ndescription: d\nscope: always\n---\n"
        "Read [docs](https://example.com/docs).\n",
        encoding="utf-8",
    )

    assert _validate.run(_ns(tmp_path)) == 1

    out = capsys.readouterr().out
    assert f"FAIL {rule}: markdown link 'https://example.com/docs'" in out
    assert f"OK {_engine_artifact_count(tmp_path) + 1}" not in out


def test_validate_without_config_reports_consumer_checks_skipped(tmp_path, capsys):
    assert _validate.run(_ns(tmp_path)) == 0
    skipped = [line for line in capsys.readouterr().out.splitlines() if line.startswith("skipped")]
    assert len(skipped) == len(_validate_context.CONSUMER_CONFIG_CHECKS) == 4
    assert any("overlays_enabled" in line for line in skipped)
    assert any("[links] allowed_domains" in line for line in skipped)
    assert any("[hooks] / [guardrails] policy" in line for line in skipped)
    assert any("[forge] hosts" in line for line in skipped)


def test_validate_with_config_prints_no_config_less_note(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path)
    assert _validate.run(_ns(repo)) == 0
    out = capsys.readouterr().out
    assert "no .coding-agent-playbook.toml" not in out
    assert "skipped" not in out


@pytest.fixture
def fake_engine_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """``<tmp_path>/src/<pkg>/resources`` as an importable package: a checkout whose
    src/ package IS the engine, as in an editable install of the engine repo."""
    name = "fake_engine_p8"
    package = tmp_path / "src" / name
    (package / "resources" / "rules").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path / "src"))
    yield name
    sys.modules.pop(name, None)


def test_checkout_resource_roots_skips_the_engine_package(tmp_path, fake_engine_checkout):
    overlay_resources = tmp_path / "src" / "acme_overlay" / "resources"
    overlay_resources.mkdir(parents=True)
    (tmp_path / "src" / "no_resources").mkdir()
    (tmp_path / "src" / ".hidden" / "resources").mkdir(parents=True)

    roots = _validate_context.checkout_resource_roots(tmp_path, engine_package=fake_engine_checkout)

    assert roots == [overlay_resources]


def test_checkout_resource_roots_without_src_is_empty(tmp_path):
    assert _validate_context.checkout_resource_roots(tmp_path, engine_package="x") == []


@pytest.mark.skipif(sys.platform == "win32", reason="needs a directory symlink")
def test_config_less_context_in_the_engine_checkout_walks_the_engine_once(tmp_path, capsys):
    """A checkout whose ``src/coding_agent_playbook`` IS the engine package walks
    the engine once: before v0.19 its ``resources/`` was the engine's content and
    needed the resolved-path dedupe; the content now lives in ``catalog/``, so
    no ``src/*/resources/`` layer may appear at all."""
    engine_dir = Path(coding_agent_playbook.__file__).parent
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "coding_agent_playbook").symlink_to(engine_dir, target_is_directory=True)

    ctx = _validate_context.config_less_context(tmp_path)

    assert isinstance(ctx.artifact_source, FileSystemArtifactSource)
    assert ctx.artifact_source.extra_resource_roots == ()
    assert ctx.overlay_collisions == []
    assert _validate.run(_ns(tmp_path)) == 0
    assert f"OK {_engine_artifact_count(tmp_path)} artifacts validated" in capsys.readouterr().out
