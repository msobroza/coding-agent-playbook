"""Tests for ``cap render`` (PR 10 Task 7)."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import render as _render

if TYPE_CHECKING:
    from pathlib import Path


def _ns(
    repo: Path,
    artifact_id: str,
    *,
    fmt: str | None = None,
    show_source: bool = False,
    show_rules: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        repo_root=str(repo),
        id=artifact_id,
        format=fmt,
        show_source=show_source,
        show_rules=show_rules,
    )


def test_render_rule_as_continue_writes_to_stdout(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("my-rule", "Body content\n")])
    rc = _render.run(_ns(repo, "my-rule", fmt="continue"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "alwaysApply" in out  # continue rule front-matter
    assert "Body content" in out


def test_render_rule_as_claude_section(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("my-rule", "Body content\n")])
    rc = _render.run(_ns(repo, "my-rule", fmt="claude"))
    assert rc == 0
    out = capsys.readouterr().out
    # claude_md_section emits `## name`
    assert out.startswith("## ") or "## " in out
    assert "Body content" in out


def test_render_prompt_as_prompt_continue(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(
        tmp_path, prompts=[("hello", {"slash": "hello", "body": "Hello prompt\n"})]
    )
    rc = _render.run(_ns(repo, "hello", fmt="prompt_continue"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Hello prompt" in out


def test_render_show_source_prints_template_path(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("my-rule", "Body\n")])
    rc = _render.run(_ns(repo, "my-rule", show_source=True))
    assert rc == 0
    out = capsys.readouterr().out
    # SPEC §12.7: Template line carries the full path to the source file.
    assert "Template:" in out
    assert "playbook/rules/my-rule.md" in out
    # Format line classifies templated vs verbatim.
    assert "Format:" in out
    assert ".md (verbatim)" in out
    # Adapters line lists discovered adapters.
    assert "Adapters:" in out
    # SPEC §12.7 final line: applies_if outcome under the current facts.
    assert "applies_if evaluated: True" in out


def test_render_show_rules_lists_inclusion_graph(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("included-rule", "Inner body\n")],
        prompts=[
            (
                "with-includes",
                {
                    "slash": "with-includes",
                    "includes_rules": ["included-rule", "missing-rule"],
                    "body": "Prompt body\n",
                },
            )
        ],
    )
    rc = _render.run(_ns(repo, "with-includes", show_rules=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "included-rule" in out
    assert "missing-rule" in out
    # The known rule should be INLINED; the unknown one UNKNOWN.
    assert "INLINED" in out
    assert "UNKNOWN" in out


def test_render_unknown_id_exits_one(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path)
    rc = _render.run(_ns(repo, "does-not-exist"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "does-not-exist" in err


def test_render_unknown_format_exits_one(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("rule-a", "body\n")])
    rc = _render.run(_ns(repo, "rule-a", fmt="nonsense"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "unknown format" in err.lower() or "valid" in err.lower()
