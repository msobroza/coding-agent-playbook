"""Tests for ``playbook render`` (PR 10 Task 7)."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.commands import render as _render
from tests.hook_samples import write_hook

if TYPE_CHECKING:
    from collections.abc import Callable
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


def test_render_show_source_omits_overrides_when_no_collision(
    tmp_path, make_synthetic_repo, capsys
):
    """A rule with no overlay collision should NOT emit an 'Overrides:' line.

    SPEC §12.7 shows ``Overrides:`` only when a winner shadows a loser; when
    there's no shadowing the line is omitted entirely.
    """
    repo = make_synthetic_repo(tmp_path, rules=[("loner-rule", "Body\n")])
    rc = _render.run(_ns(repo, "loner-rule", show_source=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Template:" in out
    # No collision means no "Overrides:" header at all.
    assert "Overrides:" not in out


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


def test_render_prompt_format_against_rule_exits_one(tmp_path, make_synthetic_repo, capsys):
    """Requesting a prompt-only format for a rule should fail with a clear error."""
    repo = make_synthetic_repo(tmp_path, rules=[("rule-a", "body\n")])
    rc = _render.run(_ns(repo, "rule-a", fmt="prompt_continue"))
    assert rc == 1
    err = capsys.readouterr().err
    # The error should call out that the format is not valid for rules.
    assert "prompt_continue" in err
    assert "rule" in err.lower()


def test_render_rule_format_against_prompt_exits_one(tmp_path, make_synthetic_repo, capsys):
    """Requesting a rule-only format for a prompt should fail with a clear error."""
    repo = make_synthetic_repo(tmp_path, prompts=[("hello", {"slash": "hello", "body": "Hello\n"})])
    rc = _render.run(_ns(repo, "hello", fmt="continue_rule"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "continue_rule" in err
    assert "prompt" in err.lower()


# --- K3: `playbook render <hook-id>` (specs/prK-lifecycle-hooks.md §C.4.1) ---------------


def _hook_repo(tmp_path: Path, make_synthetic_repo: Callable[..., Path], **hook: Any) -> Path:
    repo = make_synthetic_repo(tmp_path)
    write_hook(repo / "playbook" / "hooks", "guard-x", **hook)
    return repo


def test_render_hook_id_defaults_to_hook_advisory(tmp_path, make_synthetic_repo, capsys):
    repo = _hook_repo(tmp_path, make_synthetic_repo, body="Never edit generated files.\n")

    rc = _render.run(_ns(repo, "guard-x"))

    assert rc == 0
    assert capsys.readouterr().out == (
        "### Guard X\n\nNever edit generated files.\n\n"
        "*Enforced by lifecycle hooks on: Claude Code. "
        "Everywhere else this is guidance: apply it yourself.*\n\n"
    )


def test_render_templated_hook_body(tmp_path, make_synthetic_repo, capsys):
    repo = _hook_repo(
        tmp_path, make_synthetic_repo, marker="HOOK.md.j2", body="Guard {{ project_name }}.\n"
    )

    assert _render.run(_ns(repo, "guard-x", fmt="hook_advisory")) == 0
    assert "Guard synthetic." in capsys.readouterr().out


def test_render_hook_as_claude_settings(tmp_path, make_synthetic_repo, capsys):
    repo = _hook_repo(tmp_path, make_synthetic_repo, matcher={"pre_tool_use": {"tools": ["edit"]}})

    assert _render.run(_ns(repo, "guard-x", fmt="hook_claude_settings")) == 0
    projection = json.loads(capsys.readouterr().out)
    assert projection["hooks"]["PreToolUse"][0]["matcher"] == "Edit|MultiEdit"


def test_render_hook_rejects_rule_formats(tmp_path, make_synthetic_repo, capsys):
    repo = _hook_repo(tmp_path, make_synthetic_repo)

    rc = _render.run(_ns(repo, "guard-x", fmt="continue"))

    assert rc == 1
    err = capsys.readouterr().err
    assert "not valid for hooks" in err
    assert "hook_advisory" in err


def test_render_rule_rejects_hook_formats(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("my-rule", "Body\n")])

    assert _render.run(_ns(repo, "my-rule", fmt="hook_advisory")) == 1
    assert "not valid for rules" in capsys.readouterr().err


def test_hook_body_cannot_call_rule(tmp_path, make_synthetic_repo, capsys):
    repo = _hook_repo(
        tmp_path, make_synthetic_repo, marker="HOOK.md.j2", body="{{ rule('my-rule') }}\n"
    )

    rc = _render.run(_ns(repo, "guard-x"))

    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "'rule' is undefined" in captured.err
    assert "playbook/hooks/protect/guard-x/HOOK.md.j2" in captured.err


def test_render_hook_show_source(tmp_path, make_synthetic_repo, capsys):
    repo = _hook_repo(tmp_path, make_synthetic_repo)

    assert _render.run(_ns(repo, "guard-x", show_source=True)) == 0
    out = capsys.readouterr().out
    assert "playbook/hooks/protect/guard-x/HOOK.md" in out
    assert "applies_if evaluated: True" in out
