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


def test_render_show_rules_names_the_owning_skill(tmp_path, make_synthetic_repo, capsys):
    """Each included rule shows its delivery: a skill reference, always loaded, or unknown."""
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("included-rule", "Inner body\n")],
        prompts=[
            (
                "with-includes",
                {
                    "slash": "with-includes",
                    "includes_rules": ["python-typing", "included-rule", "missing-rule"],
                    "body": "Prompt body\n",
                },
            )
        ],
    )
    rc = _render.run(_ns(repo, "with-includes", show_rules=True))
    assert rc == 0
    assert capsys.readouterr().out == (
        "Prompt:    with-includes\n"
        "includes_rules:\n"
        "  - python-typing  (coding_agent_playbook, applies_if=True -> skill python-coding, "
        "rules/python-typing.md)\n"
        "  - included-rule  (<repo-local>, applies_if=True -> always loaded)\n"
        "  - missing-rule  (UNKNOWN)\n"
    )


def test_render_prompt_claude_command_shows_the_pointer_block(
    tmp_path, make_synthetic_repo, capsys
):
    repo = make_synthetic_repo(tmp_path)

    assert _render.run(_ns(repo, "review", fmt="prompt_claude_command")) == 0
    out = capsys.readouterr().out
    assert "## Before you start" in out
    assert "1. Load skill `python-coding` and read its rules" in out
    assert not [line for line in out.splitlines() if line.startswith("### ")]


def test_render_prompt_continue_keeps_the_reference_appendix(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path)

    assert _render.run(_ns(repo, "review", fmt="prompt_continue")) == 0
    out = capsys.readouterr().out
    assert out.count("## Reference rules") == 1
    assert out.count("### Typing") == 1
    assert out.index("## Output format") < out.index("## Reference rules")
    assert "## Before you start" not in out


def test_render_prompt_calling_rule_reports_the_file(tmp_path, make_synthetic_repo, capsys):
    """Regression (D15): the removed ``rule()`` helper names the prompt, not a traceback."""
    repo = make_synthetic_repo(tmp_path)
    prompt = repo / "playbook" / "prompts" / "inliner.md.j2"
    prompt.parent.mkdir(parents=True)
    prompt.write_text(
        "---\nid: inliner\nname: Inliner\ndescription: d\nslash: inliner\n---\n"
        'Review.\n{{ rule("python-typing") }}\n',
        encoding="utf-8",
    )

    rc = _render.run(_ns(repo, "inliner", fmt="prompt_claude_command"))

    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error: playbook/prompts/inliner.md.j2: 'rule' is undefined" in captured.err
    assert "playbook render aborted." in captured.err


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


# --- B1: render omits included rules whose applies_if is false (SPEC §6.2.5, §12.7) ------


def _write_gated_rule(repo: Path, rule_id: str, predicate: str, body: str) -> None:
    """Write a repo-local ``scope: always`` rule gated on ``has_framework: <predicate>``."""
    target = repo / "playbook" / "rules" / f"{rule_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"---\nid: {rule_id}\nname: Gated\ndescription: d\nscope: always\npriority: 50\n"
        f"applies_if:\n  has_framework: {predicate}\n---\n{body}",
        encoding="utf-8",
    )


def _tidy_repo(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], includes: list[str], **extras: Any
) -> Path:
    """A repo whose prompt ``tidy`` includes ``includes`` (the caller writes those rules)."""
    prompt = {"slash": "tidy", "includes_rules": includes, "body": "Tidy up.\n"}
    return make_synthetic_repo(tmp_path, prompts=[("tidy", prompt)], **extras)


def _delivered_ids(show_rules_out: str) -> set[str]:
    """Rule ids ``--show-rules`` delivers: every ``  - <id>`` line not ``OMITTED`` or ``UNKNOWN``."""
    return {
        line.split()[1]
        for line in show_rules_out.splitlines()
        if line.startswith("  - ") and not line.endswith(("-> OMITTED)", "(UNKNOWN)"))
    }


def test_render_prompt_omits_an_included_rule_whose_applies_if_is_false(
    tmp_path, make_synthetic_repo, capsys
):
    repo = _tidy_repo(tmp_path, make_synthetic_repo, ["gated"])
    _write_gated_rule(repo, "gated", '["fastapi"]', "GATED-BODY\n")

    rc = _render.run(_ns(repo, "tidy", fmt="prompt_continue"))

    assert rc == 0
    out = capsys.readouterr().out
    assert "GATED-BODY" not in out
    assert "## Reference rules" not in out


def test_render_prompt_inlines_an_applicable_included_rule(tmp_path, make_synthetic_repo, capsys):
    """The control: the same repo with fastapi installed inlines the gated rule."""
    repo = _tidy_repo(
        tmp_path, make_synthetic_repo, ["gated"], pyproject_extras={"dependencies": ["fastapi"]}
    )
    _write_gated_rule(repo, "gated", '["fastapi"]', "GATED-BODY\n")

    assert _render.run(_ns(repo, "tidy", fmt="prompt_continue")) == 0
    assert "GATED-BODY" in capsys.readouterr().out


def test_render_prompt_agrees_with_show_rules(tmp_path, make_synthetic_repo, capsys):
    repo = _tidy_repo(
        tmp_path, make_synthetic_repo, ["gated", "plain"], rules=[("plain", "PLAIN-BODY\n")]
    )
    _write_gated_rule(repo, "gated", '["fastapi"]', "GATED-BODY\n")
    bodies = {"gated": "GATED-BODY", "plain": "PLAIN-BODY"}

    assert _render.run(_ns(repo, "tidy", show_rules=True)) == 0
    delivered = _delivered_ids(capsys.readouterr().out)
    assert _render.run(_ns(repo, "tidy", fmt="prompt_continue")) == 0
    rendered = capsys.readouterr().out

    assert delivered == {rule_id for rule_id, body in bodies.items() if body in rendered}
    assert delivered == {"plain"}


def test_render_prompt_omits_an_included_rule_with_a_malformed_predicate(
    tmp_path, make_synthetic_repo, capsys
):
    """``has_framework: "fastapi"`` (a string, not a list) makes the detector raise."""
    repo = _tidy_repo(tmp_path, make_synthetic_repo, ["gated"])
    _write_gated_rule(repo, "gated", '"fastapi"', "GATED-BODY\n")

    rc = _render.run(_ns(repo, "tidy", fmt="prompt_continue"))

    assert rc == 0
    assert "GATED-BODY" not in capsys.readouterr().out
