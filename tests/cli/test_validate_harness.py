"""Tests for ``playbook validate-harness`` (PR H Track H4).

The validator runs ``harnesses-ref``-equivalent structural checks against a
harness tree (emitted or foreign):

- **errors** (non-zero exit): ``HARNESS.md`` absent; its ``name``/``description``
  empty; a detected skill leaf missing ``name``/``description``;
- **warnings** (exit 0 by default, non-zero under ``--strict``): a grouping
  subdir lacks its routing file; a content ``.md`` lacks ``description``.

A harness emitted by :class:`AgentHarnessAdapter` must validate warning-clean
(spec §A: the adapter emits routing files + content descriptions to stay clean).
"""

from __future__ import annotations

import argparse
import stat
from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.commands import validate_harness as _validate_harness
from tests.hook_samples import resolved_from_disk

if TYPE_CHECKING:
    from pathlib import Path


def _ns(path: Path | None, *, strict: bool = False) -> argparse.Namespace:
    return argparse.Namespace(path=None if path is None else str(path), strict=strict)


# --- fixtures --------------------------------------------------------------


def _minimal_harness(tmp_path: Path) -> Path:
    """A bare-but-valid harness: just ``HARNESS.md`` with name + description."""
    root = tmp_path / "harness"
    root.mkdir()
    (root / "HARNESS.md").write_text(
        "---\nname: My harness\ndescription: Does things\n---\nRole summary.\n",
        encoding="utf-8",
    )
    return root


def _adapter_emitted_harness(tmp_path: Path) -> Path:
    """A harness produced by the real :class:`AgentHarnessAdapter` (spec §A clean)."""
    scripts_src = tmp_path / "scripts_src"
    scripts_src.mkdir()
    run = scripts_src / "run_query.py"
    run.write_text("#!/usr/bin/env python\nprint('q')\n", encoding="utf-8")
    run.chmod(run.stat().st_mode | stat.S_IXUSR)

    refs_src = tmp_path / "refs_src"
    refs_src.mkdir()
    (refs_src / "schema.md").write_text(
        "---\ndescription: warehouse schema\n---\n# Schema\n", encoding="utf-8"
    )

    repo = tmp_path / "emitted"
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
                skill="python-coding",
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


# --- success paths ---------------------------------------------------------


def test_valid_minimal_harness_passes(tmp_path, capsys):
    root = _minimal_harness(tmp_path)
    rc = _validate_harness.run(_ns(root))
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_adapter_emitted_harness_validates_clean(tmp_path, capsys):
    """An AgentHarnessAdapter-emitted tree is warning-clean (spec §A)."""
    root = _adapter_emitted_harness(tmp_path)
    rc = _validate_harness.run(_ns(root))
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    # Warning-clean: no warnings on stderr.
    assert "warning" not in captured.err.lower()
    # And clean under --strict too (no warnings to promote).
    rc_strict = _validate_harness.run(_ns(root, strict=True))
    assert rc_strict == 0


# --- error paths -----------------------------------------------------------


def test_missing_harness_md_is_error(tmp_path, capsys):
    root = tmp_path / "empty"
    root.mkdir()
    rc = _validate_harness.run(_ns(root))
    assert rc != 0
    out = capsys.readouterr().out
    assert "HARNESS.md" in out


def test_empty_name_is_error(tmp_path, capsys):
    root = tmp_path / "harness"
    root.mkdir()
    (root / "HARNESS.md").write_text(
        "---\nname: ''\ndescription: Does things\n---\nRole.\n", encoding="utf-8"
    )
    rc = _validate_harness.run(_ns(root))
    assert rc != 0
    out = capsys.readouterr().out
    assert "name" in out.lower()


def test_skill_leaf_missing_description_is_error(tmp_path, capsys):
    root = _minimal_harness(tmp_path)
    (root / ".leaf-detectors").write_text("skill=SKILL.md\n", encoding="utf-8")
    skills = root / "skills"
    skills.mkdir()
    (skills / "SKILLS.md").write_text(
        "---\ndescription: skills index\n---\nSkills.\n", encoding="utf-8"
    )
    leaf = skills / "broken"
    leaf.mkdir()
    # name present, description empty -> error.
    (leaf / "SKILL.md").write_text(
        "---\nname: Broken\ndescription: ''\n---\nBody.\n", encoding="utf-8"
    )
    rc = _validate_harness.run(_ns(root))
    assert rc != 0
    out = capsys.readouterr().out
    assert "description" in out.lower()


def test_nested_skill_leaf_missing_name_is_error(tmp_path, capsys):
    """A skill leaf nested under a grouping subtree is reached (recursion)."""
    root = _minimal_harness(tmp_path)
    (root / ".leaf-detectors").write_text("skill=SKILL.md\n", encoding="utf-8")
    skills = root / "skills"
    skills.mkdir()
    (skills / "SKILLS.md").write_text(
        "---\ndescription: skills index\n---\nSkills.\n", encoding="utf-8"
    )
    # A nested grouping dir (routing propagates to SKILLS.md) below skills/.
    group = skills / "db"
    group.mkdir()
    (group / "SKILLS.md").write_text("---\ndescription: db skills\n---\nDB.\n", encoding="utf-8")
    leaf = group / "migrate"
    leaf.mkdir()
    # description present, name empty -> error.
    (leaf / "SKILL.md").write_text(
        "---\nname: ''\ndescription: Run migrations\n---\nBody.\n", encoding="utf-8"
    )
    rc = _validate_harness.run(_ns(root))
    assert rc != 0
    out = capsys.readouterr().out
    assert "name" in out.lower()


# --- warning paths ---------------------------------------------------------


def test_grouping_subdir_missing_routing_file_warns(tmp_path, capsys):
    root = _minimal_harness(tmp_path)
    # A grouping dir (no leaf detector, so it stays a grouping directory) with
    # NO routing file (SKILLS.md) -> warning, not error.
    skills = root / "skills"
    skills.mkdir()
    (skills / "note.md").write_text("---\ndescription: a note\n---\nContent.\n", encoding="utf-8")
    rc = _validate_harness.run(_ns(root))
    assert rc == 0  # warning only, no --strict
    err = capsys.readouterr().err
    assert "SKILLS.md" in err or "routing" in err.lower()
    # --strict promotes the warning to a failure.
    rc_strict = _validate_harness.run(_ns(root, strict=True))
    assert rc_strict != 0


def test_content_md_missing_description_warns(tmp_path, capsys):
    root = _minimal_harness(tmp_path)
    refs = root / "references"
    refs.mkdir()
    (refs / "REFERENCES.md").write_text(
        "---\ndescription: refs index\n---\nRefs.\n", encoding="utf-8"
    )
    # A content .md with NO description frontmatter -> warning.
    (refs / "loose.md").write_text("# Loose\n\nNo frontmatter here.\n", encoding="utf-8")
    rc = _validate_harness.run(_ns(root))
    assert rc == 0
    err = capsys.readouterr().err
    assert "loose.md" in err or "description" in err.lower()
    rc_strict = _validate_harness.run(_ns(root, strict=True))
    assert rc_strict != 0


# --- opaque-leaf directories -----------------------------------------------


def test_opaque_harnessleaf_dir_validates_clean(tmp_path, capsys):
    """An opaque ``.harnessleaf`` directory is a leaf: no routing-file or content checks.

    Per spec §A/§B a directory carrying a ``.harnessleaf`` marker for its own path
    is terminal — generic clients stop traversing it, so the validator must NEVER
    expect it to carry a routing file (``EVALS.md``) and must NOT inspect its
    internal content (e.g. an ``internal.md`` with no ``description``). Such a
    harness must validate warning-clean, including under ``--strict``.
    """
    root = _minimal_harness(tmp_path)
    evals = root / "evals"
    evals.mkdir()
    # The marker makes the whole directory opaque (precedence over any detector).
    (evals / ".harnessleaf").write_text("", encoding="utf-8")
    # Internal content the client must NOT inspect: no description frontmatter.
    (evals / "internal.md").write_text("# Internal\n\nEval internals.\n", encoding="utf-8")

    rc = _validate_harness.run(_ns(root))
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    # No false warnings: neither the missing routing file nor the content check fire.
    assert "warning" not in captured.err.lower()
    assert "EVALS.md" not in captured.err
    assert "internal.md" not in captured.err

    # And clean under --strict too (no warnings to promote into a failure).
    rc_strict = _validate_harness.run(_ns(root, strict=True))
    assert rc_strict == 0
    assert "warning" not in capsys.readouterr().err.lower()


# --- argument errors -------------------------------------------------------


def test_missing_path_arg_exits_two(capsys):
    rc = _validate_harness.run(_ns(None))
    assert rc == 2
    assert capsys.readouterr().err


def test_nonexistent_path_exits_two(tmp_path, capsys):
    rc = _validate_harness.run(_ns(tmp_path / "does-not-exist"))
    assert rc == 2
    assert capsys.readouterr().err


def test_emitted_tree_with_hooks_has_zero_findings(tmp_path, capsys):
    """The hook sidecar is opaque and the guardrail advisory a described content file (§C.6)."""
    repo = tmp_path / "emitted"
    adapter = AgentHarnessAdapter()
    adapter.write_hook(resolved_from_disk(tmp_path / "src"), repo)
    adapter.write_hook(resolved_from_disk(tmp_path / "src", "guard-y", body=""), repo)
    adapter.finalize(repo)
    assert (repo / ".playbook" / "hooks" / "guard-x" / "scripts" / "check.sh").is_file()
    assert (repo / "rules" / "30-guardrail-guard-x.md").is_file()

    rc = _validate_harness.run(_ns(repo, strict=True))

    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "warning" not in captured.err.lower()
    assert "error" not in captured.err.lower()
