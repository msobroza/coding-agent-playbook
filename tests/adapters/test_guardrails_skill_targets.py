"""Which adapters receive the ``playbook-guardrails`` skill (D6, specs/prS-skills-context.md 8.4.3).

The dispatch hands the composed skill only to an adapter whose
``writes_guardrails_skill`` says so: ``opencode`` and ``shared_skills`` whenever
any on hook has guardrail text, ``claude_code`` only for a hook it cannot run
natively, and never ``continue``, ``agent_harness`` or ``agents_md``, which keep
their own guardrail channels. The skill then goes through the normal
``write_skill`` path, so every copy it gets is the shared ``SkillWriter``'s.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.adapters.agent_harness_adapter import AgentHarnessAdapter
from coding_agent_playbook.adapters.agents_md_adapter import AgentsMdAdapter
from coding_agent_playbook.adapters.claude_code.paths import CLAUDE_RULES_PATH
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.continue_adapter import ContinueAdapter
from coding_agent_playbook.adapters.opencode_adapter import OpenCodeAdapter
from coding_agent_playbook.adapters.shared_skills_adapter import SharedSkillsAdapter
from coding_agent_playbook.commands._sync_lockfile import HookDispatch, dispatch_to_adapters
from coding_agent_playbook.config.tables.hooks import HooksConfig
from coding_agent_playbook.hook_policy.guardrails_skill import (
    GUARDRAILS_SKILL_ID,
    compose_guardrails_skill,
)
from coding_agent_playbook.types import Skill
from tests.hook_samples import GUARDRAILS_SECTION_HEAD, resolved_hook

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.hook_policy import ResolvedHook

_SKILL_MD = f"{GUARDRAILS_SKILL_ID}/SKILL.md"
_NATIVE_ROOTS = (".claude/skills", ".opencode/skills", ".agents/skills")
#: guard-x as Continue's 30-guardrail file holds it before and after D6 (byte pin).
_CONTINUE_GUARDRAIL = (
    f"{sentinel_line('html')}\n"
    "---\n"
    "name: 'Guardrail: Guard X'\n"
    "description: Deny x.\n"
    "alwaysApply: true\n"
    "---\n"
    "Advice.\n\n"
    "*Enforced by lifecycle hooks on: Claude Code. "
    "Everywhere else this is guidance: apply it yourself.*\n"
)
#: guard-x as agent_harness's rules/30-guardrail file holds it before and after D6 (byte pin).
_HARNESS_GUARDRAIL = (
    "---\n"
    "description: Deny x.\n"
    "---\n"
    f"{sentinel_line('html')}\n\n"
    "Advice.\n\n"
    "*Enforced by lifecycle hooks on: Claude Code. "
    "Everywhere else this is guidance: apply it yourself.*\n"
)


def _authored() -> Skill:
    frontmatter = {
        "id": GUARDRAILS_SKILL_ID,
        "name": GUARDRAILS_SKILL_ID,
        "description": "Holds the full guardrail text. Use when a guardrail needs detail.",
    }
    return Skill(frontmatter, "\n# Playbook guardrails\n", None, None, "coding_agent_playbook")


def _every_adapter() -> dict[str, Adapter]:
    return {
        "agents_md": AgentsMdAdapter(),
        "claude_code": ClaudeCodeAdapter(),
        "continue": ContinueAdapter(),
        "opencode": OpenCodeAdapter(),
        "shared_skills": SharedSkillsAdapter(),
        "agent_harness": AgentHarnessAdapter(),
    }


def _dispatch(out: Path, hooks: Sequence[ResolvedHook], adapters: Mapping[str, Adapter]) -> None:
    """One sync's dispatch of ``hooks`` with the skill composed from them, into ``out``."""
    plan = HookDispatch(
        hooks, out, None, HooksConfig(enabled=True), compose_guardrails_skill(_authored(), hooks)
    )
    dispatch_to_adapters(adapters, [], [], [], out, hooks=plan)


def _roots_with_the_skill(out: Path) -> list[str]:
    return [root for root in _NATIVE_ROOTS if (out / root / _SKILL_MD).is_file()]


def test_opencode_and_shared_skills_write_the_skill_when_any_advisory_exists(
    tmp_path: Path,
) -> None:
    _dispatch(tmp_path, [resolved_hook()], _every_adapter())

    assert _roots_with_the_skill(tmp_path) == [".opencode/skills", ".agents/skills"]
    opencode, shared = (tmp_path / root / _SKILL_MD for root in _NATIVE_ROOTS[1:])
    assert opencode.read_bytes() == shared.read_bytes()
    text = opencode.read_text(encoding="utf-8")
    assert "## Guard X (`guard-x`)\n\nAdvice.\n" in text


@pytest.mark.parametrize(
    "hooks",
    [
        pytest.param([], id="hooks_off"),
        pytest.param([resolved_hook("quiet", body="")], id="no_hook_with_a_body"),
    ],
)
def test_no_adapter_writes_the_skill_without_an_advisory(
    tmp_path: Path, hooks: list[ResolvedHook]
) -> None:
    _dispatch(tmp_path, hooks, _every_adapter())

    assert _roots_with_the_skill(tmp_path) == []


def test_claude_code_skips_the_skill_when_every_hook_is_native(tmp_path: Path) -> None:
    hooks = [resolved_hook(), resolved_hook("guard-y", supports=("claude_code", "opencode"))]

    _dispatch(tmp_path, hooks, {"claude_code": ClaudeCodeAdapter()})

    assert not (tmp_path / ".claude" / "skills" / GUARDRAILS_SKILL_ID).exists()


def test_claude_code_writes_skill_and_line_for_a_hook_it_cannot_run(tmp_path: Path) -> None:
    """D26 (open question Q3, R4-5): an overlay hook without ``claude_code`` in ``supports``.

    The skill holds every hook's full text; the rules file gets one guardrail line
    for the hook Claude Code cannot run, none for the native one, and no full section.
    """
    overlay = resolved_hook("overlay-only", supports=("opencode",), summary="Ask first.")
    hooks = [resolved_hook(), overlay]

    _dispatch(tmp_path, hooks, {"claude_code": ClaudeCodeAdapter()})

    text = (tmp_path / ".claude" / "skills" / _SKILL_MD).read_text(encoding="utf-8")
    assert "(`overlay-only`)" in text and "(`guard-x`)" in text
    rules = (tmp_path / CLAUDE_RULES_PATH).read_text(encoding="utf-8")
    assert rules.endswith(f"\n{GUARDRAILS_SECTION_HEAD}- `overlay-only`: Ask first.\n")
    assert rules.count("## Guardrails\n") == 1
    assert "guard-x" not in rules and "## Guardrail: " not in rules and "Advice." not in rules


def test_continue_guardrail_rule_files_are_byte_identical(tmp_path: Path) -> None:
    """Regression: Continue keeps its rule file per hook and gets no guardrails prompt."""
    _dispatch(tmp_path, [resolved_hook()], {"continue": ContinueAdapter()})

    rules = tmp_path / ".continue" / "rules" / "30-guardrail-guard-x.md"
    assert rules.read_text(encoding="utf-8") == _CONTINUE_GUARDRAIL
    assert sorted(p.name for p in (tmp_path / ".continue").rglob("*") if p.is_file()) == [
        "30-guardrail-guard-x.md"
    ]


def test_agent_harness_guardrail_rule_file_is_byte_identical(tmp_path: Path) -> None:
    """Regression (D6): the summary is AGENTS.md's line only; the sidecar copies the key."""
    _dispatch(
        tmp_path, [resolved_hook(summary="Ask first.")], {"agent_harness": AgentHarnessAdapter()}
    )

    rule = (tmp_path / "rules" / "30-guardrail-guard-x.md").read_text(encoding="utf-8")
    assert rule == _HARNESS_GUARDRAIL
    sidecar = (tmp_path / ".playbook" / "hooks" / "guard-x" / "HOOK.md").read_text(encoding="utf-8")
    assert "\nsummary: Ask first.\n" in sidecar


def test_agent_harness_never_writes_the_skill(tmp_path: Path) -> None:
    _dispatch(tmp_path, [resolved_hook("overlay-only", supports=())], _every_adapter())

    assert not (tmp_path / "skills" / GUARDRAILS_SKILL_ID).exists()
    assert (tmp_path / "rules" / "30-guardrail-overlay-only.md").is_file()


@pytest.mark.parametrize(
    ("adapter", "expected"),
    [
        pytest.param(AgentsMdAdapter(), False, id="agents_md"),
        pytest.param(ContinueAdapter(), False, id="continue"),
        pytest.param(AgentHarnessAdapter(), False, id="agent_harness"),
        pytest.param(OpenCodeAdapter(), True, id="opencode"),
        pytest.param(SharedSkillsAdapter(), True, id="shared_skills"),
        pytest.param(ClaudeCodeAdapter(), False, id="claude_code"),
    ],
)
def test_writes_guardrails_skill_for_a_native_hook_with_an_advisory(
    adapter: Adapter, expected: bool
) -> None:
    assert adapter.writes_guardrails_skill([resolved_hook()]) is expected
