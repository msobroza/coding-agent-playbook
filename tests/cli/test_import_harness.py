"""Tests for ``playbook import-harness`` (PR H Track H3).

Covers the CLI surface: a successful import writes canonical artifacts into the
``--into`` overlay dir (in the ``FileSystemArtifactSource`` layout, so a later
``playbook sync`` could re-read them) and exits 0; a non-harness path / missing
``HARNESS.md`` exits non-zero with a clear stderr message; and a sidecar-less
(foreign) harness prints lossiness warnings to stderr.
"""

from __future__ import annotations

import argparse
import os
import stat
from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.agent_harness_adapter import AgentHarnessAdapter
from coding_agent_playbook.commands import import_harness as _import
from coding_agent_playbook.types import (
    Prompt,
    PromptFrontmatter,
    Rule,
    RuleFrontmatter,
    Skill,
)

if TYPE_CHECKING:
    from pathlib import Path


def _ns(path: Path, into: Path | None = None) -> argparse.Namespace:
    return argparse.Namespace(path=str(path), into=None if into is None else str(into))


# --- harness fixtures ------------------------------------------------------


def _emit_full_harness(tmp_path: Path) -> Path:
    scripts_src = tmp_path / "scripts_src"
    scripts_src.mkdir()
    run = scripts_src / "run_query.py"
    run.write_text("#!/usr/bin/env python\nprint('q')\n", encoding="utf-8")
    run.chmod(run.stat().st_mode | stat.S_IXUSR)

    refs_src = tmp_path / "refs_src"
    refs_src.mkdir()
    (refs_src / "schema.md").write_text("# Schema\n", encoding="utf-8")

    repo = tmp_path / "harness"
    repo.mkdir()
    adapter = AgentHarnessAdapter()
    adapter.write_skill(
        Skill(
            frontmatter={
                "id": "query-database",
                "name": "Query database",
                "description": "Run SQL",
            },
            body="# Query database\n\nUse run_query.\n",
            scripts_dir=scripts_src,
            references_dir=refs_src,
            source_package="test",
        ),
        repo,
    )
    adapter.write_prompt(
        Prompt(
            frontmatter=PromptFrontmatter(
                id="review", name="Review", description="Review code", slash="review"
            ),
            body="# Review\n\nReview the diff.\n",
            template_body="# Review\n\nReview the diff.\n",
            is_templated=False,
            source_path=None,
            source_package="test",
        ),
        repo,
    )
    adapter.write_rule(
        Rule(
            frontmatter=RuleFrontmatter(
                id="python-house-style",
                name="python-house-style",
                description="House style",
                scope="always",
                priority=10,
                tags=["python"],
            ),
            body="# Style\n\nUse type hints.\n",
            template_body="# Style\n\nUse type hints.\n",
            is_templated=False,
            source_path=None,
            source_package="test",
        ),
        repo,
    )
    adapter.write_rule(
        Rule(
            frontmatter=RuleFrontmatter(
                id="sql-guidelines",
                name="sql-guidelines",
                description="Use params",
                scope="scoped",
                globs=["**/*.sql"],
                priority=40,
            ),
            body="# SQL\n\nUse params.\n",
            template_body="# SQL\n\nUse params.\n",
            is_templated=False,
            source_path=None,
            source_package="test",
        ),
        repo,
    )
    adapter.finalize(repo)
    return repo


# --- success path ----------------------------------------------------------


def test_import_writes_canonical_layout_and_exits_zero(tmp_path, capsys):
    harness = _emit_full_harness(tmp_path)
    into = tmp_path / "out"
    rc = _import.run(_ns(harness, into))
    assert rc == 0

    # FileSystemArtifactSource layout: ALL rules (always + scoped) live under
    # rules/<id>.md — that is the ONLY directory list_rules() reads, so a scoped
    # rule written to references/ would be silently dropped on the next sync.
    # scope=scoped is preserved in the rule's frontmatter, not its directory.
    assert (into / "rules" / "python-house-style.md").is_file()
    assert (into / "rules" / "sql-guidelines.md").is_file()
    assert not (into / "references" / "sql-guidelines.md").exists()
    assert (into / "prompts" / "review.md").is_file()
    assert (into / "skills" / "query-database" / "SKILL.md").is_file()
    assert (into / "skills" / "query-database" / "scripts" / "run_query.py").is_file()
    assert (into / "skills" / "query-database" / "references" / "schema.md").is_file()


def test_import_canonical_rule_has_full_frontmatter(tmp_path):
    harness = _emit_full_harness(tmp_path)
    into = tmp_path / "out"
    _import.run(_ns(harness, into))
    content = (into / "rules" / "python-house-style.md").read_text(encoding="utf-8")
    # Full canonical frontmatter, so a later `playbook sync` can re-read it.
    assert content.startswith("---")
    assert "id: python-house-style" in content
    assert "scope: always" in content
    assert "priority: 10" in content


def test_import_scoped_rule_lands_in_rules_dir_and_stays_scoped(tmp_path):
    """Defect #4: a scoped rule must land under rules/ (the only dir list_rules
    reads) while keeping scope=scoped + globs in its frontmatter."""
    harness = _emit_full_harness(tmp_path)
    into = tmp_path / "out"
    _import.run(_ns(harness, into))
    content = (into / "rules" / "sql-guidelines.md").read_text(encoding="utf-8")
    assert "id: sql-guidelines" in content
    assert "scope: scoped" in content
    assert "**/*.sql" in content


def test_import_restores_script_exec_bit(tmp_path):
    harness = _emit_full_harness(tmp_path)
    into = tmp_path / "out"
    _import.run(_ns(harness, into))
    script = into / "skills" / "query-database" / "scripts" / "run_query.py"
    assert script.read_text(encoding="utf-8") == "#!/usr/bin/env python\nprint('q')\n"
    if os.name == "posix":
        assert os.stat(script).st_mode & 0o111


def test_import_defaults_into_playbook_dir(tmp_path, monkeypatch):
    harness = _emit_full_harness(tmp_path)
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    rc = _import.run(_ns(harness, into=None))
    assert rc == 0
    assert (workdir / "playbook" / "rules" / "python-house-style.md").is_file()


# --- error paths -----------------------------------------------------------


def test_import_missing_harness_md_exits_nonzero(tmp_path, capsys):
    not_a_harness = tmp_path / "empty"
    not_a_harness.mkdir()
    rc = _import.run(_ns(not_a_harness, tmp_path / "out"))
    assert rc != 0
    err = capsys.readouterr().err
    assert "HARNESS.md" in err or "not a harness" in err.lower()


def test_import_nonexistent_path_exits_nonzero(tmp_path, capsys):
    rc = _import.run(_ns(tmp_path / "does-not-exist", tmp_path / "out"))
    assert rc != 0
    assert capsys.readouterr().err  # a message was printed


def test_import_missing_path_arg_exits_nonzero(capsys):
    rc = _import.run(argparse.Namespace(path=None, into=None))
    assert rc != 0
    assert "harness path" in capsys.readouterr().err


# --- lossiness reporting ---------------------------------------------------


def test_import_foreign_harness_writes_raw_asset(tmp_path):
    """A foreign harness's raw/binary asset is copied verbatim into --into."""
    root = tmp_path / "foreign"
    root.mkdir()
    (root / "HARNESS.md").write_text(
        "---\nname: foreign\ndescription: d\n---\nRole.\n", encoding="utf-8"
    )
    refs = root / "references"
    refs.mkdir()
    (refs / "logo.png").write_bytes(b"\x89PNG\r\nbinary")

    into = tmp_path / "out"
    rc = _import.run(_ns(root, into))
    assert rc == 0
    copied = into / "references" / "logo.png"
    assert copied.read_bytes() == b"\x89PNG\r\nbinary"


def test_import_foreign_harness_prints_warnings(tmp_path, capsys):
    harness = _emit_full_harness(tmp_path)
    # Remove the sidecar -> best-effort (foreign) import.
    sidecar = harness / ".playbook"
    for child in sorted(sidecar.iterdir()):
        child.unlink()
    sidecar.rmdir()

    rc = _import.run(_ns(harness, tmp_path / "out"))
    assert rc == 0
    err = capsys.readouterr().err
    assert err.strip(), "best-effort import must print lossiness warnings to stderr"
