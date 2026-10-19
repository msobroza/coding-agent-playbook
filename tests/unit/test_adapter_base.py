"""Tests for the Adapter ABC (PR 1 + PR 6 cleanup refactor)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.agent_harness_adapter import AgentHarnessAdapter
from coding_agent_playbook.adapters.agents_md_adapter import AgentsMdAdapter
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.continue_adapter import ContinueAdapter
from coding_agent_playbook.adapters.opencode_adapter import OpenCodeAdapter
from coding_agent_playbook.adapters.shared_skills_adapter import SharedSkillsAdapter
from coding_agent_playbook.config.tables.hooks import HooksConfig
from coding_agent_playbook.generated_output.sentinel import SENTINEL
from coding_agent_playbook.lockfile.model import Lockfile
from coding_agent_playbook.types import Prompt, Rule, Skill
from tests.hook_samples import resolved_hook
from tests.member_skill_samples import sample_member_reference, sample_member_skill

if TYPE_CHECKING:
    from collections.abc import Iterable


class _DummyAdapter(Adapter):
    name = "dummy"

    def __init__(self) -> None:
        self.written_prompts: list[object] = []

    def write_rule(self, rule, repo_root):
        return []

    def write_prompt(self, prompt, repo_root):
        self.written_prompts.append(prompt)
        return [repo_root / f"{prompt}.md"]


class _ScannedAdapter(_DummyAdapter):
    """Subclass that publishes one output directory for cleanup scanning."""

    name = "scanned"

    def __init__(self, output_dir: Path) -> None:
        super().__init__()
        self._output_dir = output_dir

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        return [self._output_dir]


def test_adapter_abc_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Adapter()  # type: ignore[abstract]


def test_concrete_subclass_can_be_instantiated():
    assert isinstance(_DummyAdapter(), Adapter)


def test_finalize_defaults_to_no_output():
    assert _DummyAdapter().finalize(Path(".")) == []


def test_write_skill_default_degrades_to_write_prompt(tmp_path):
    """The ABC's default write_skill calls Skill.to_prompt() and forwards the
    resulting Prompt to the adapter's write_prompt. _DummyAdapter records the
    prompt it received, so the test asserts on that."""
    skill = Skill(
        frontmatter={
            "id": "demo",
            "name": "Demo",
            "description": "A demo",
            "slash": "demo",
        },
        body="body\n",
        scripts_dir=None,
        references_dir=None,
        source_package="pkg",
    )
    adapter = _DummyAdapter()
    adapter.write_skill(skill, tmp_path)
    assert len(adapter.written_prompts) == 1
    # The forwarded artifact is the Prompt returned by Skill.to_prompt().
    forwarded = adapter.written_prompts[0]
    assert isinstance(forwarded, Prompt)
    assert forwarded.frontmatter.id == "demo"
    assert forwarded.body == "body\n"


def test_default_write_skill_skips_skill_with_members(tmp_path: Path) -> None:
    """E4: a skill's member rules already reach this adapter as rules, and a degraded
    prompt would index references it never receives (specs/prS-skills-context.md 6.4.7)."""
    adapter = _DummyAdapter()

    skill = sample_member_skill("python-coding", sample_member_reference())

    written = adapter.write_skill(skill, tmp_path)

    assert written == []
    assert adapter.written_prompts == []


def test_default_output_directories_is_empty():
    """ABC default returns no directories; subclasses opt in to scanning."""
    assert list(_DummyAdapter()._output_directories(Path("."))) == []


def test_default_cleanup_no_directories_returns_empty(tmp_path):
    """An adapter that does not override _output_directories cleans nothing."""
    assert _DummyAdapter().cleanup_stale(set(), tmp_path) == []


def test_default_cleanup_skips_missing_output_directory(tmp_path):
    """If the configured output dir does not exist, scan is a no-op."""
    missing = tmp_path / "never" / "created"
    adapter = _ScannedAdapter(missing)
    assert adapter.cleanup_stale(set(), tmp_path) == []


def test_default_cleanup_removes_stale_sentinel_file(tmp_path):
    """A sentinel-tagged file not in written_paths is deleted and returned."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    stale = output_dir / "stale.md"
    stale.write_text(f"<!-- {SENTINEL} -->\nbody\n", encoding="utf-8")
    adapter = _ScannedAdapter(output_dir)
    deleted = adapter.cleanup_stale(set(), tmp_path)
    assert deleted == [stale]
    assert not stale.exists()


def test_default_cleanup_preserves_written_paths(tmp_path):
    """A sentinel-tagged file IS preserved when its resolved path is in written_paths."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    current = output_dir / "current.md"
    current.write_text(f"<!-- {SENTINEL} -->\nbody\n", encoding="utf-8")
    adapter = _ScannedAdapter(output_dir)
    deleted = adapter.cleanup_stale({current.resolve()}, tmp_path)
    assert deleted == []
    assert current.exists()


def test_default_cleanup_preserves_user_authored_file(tmp_path):
    """Files without the sentinel are never deleted, even if not in written_paths."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    user_file = output_dir / "user.md"
    user_file.write_text("# Hand-written, never touch this\n", encoding="utf-8")
    adapter = _ScannedAdapter(output_dir)
    deleted = adapter.cleanup_stale(set(), tmp_path)
    assert deleted == []
    assert user_file.exists()


def test_default_cleanup_tolerates_binary_file(tmp_path):
    """Non-UTF-8 files in the scan dir don't crash the scanner."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    binary = output_dir / "image.bin"
    binary.write_bytes(b"\xff\xfe\x00\x00binary garbage")
    adapter = _ScannedAdapter(output_dir)
    deleted = adapter.cleanup_stale(set(), tmp_path)
    assert deleted == []
    assert binary.exists()


def test_default_cleanup_recursively_scans_subdirectories(tmp_path):
    """Stale sentinel files in nested subdirs are also removed."""
    output_dir = tmp_path / "out"
    nested = output_dir / "sub"
    nested.mkdir(parents=True)
    stale = nested / "deep.md"
    stale.write_text(f"<!-- {SENTINEL} -->\nbody\n", encoding="utf-8")
    adapter = _ScannedAdapter(output_dir)
    deleted = adapter.cleanup_stale(set(), tmp_path)
    assert deleted == [stale]
    assert not stale.exists()


def test_default_cleanup_never_deletes_a_written_file_under_another_name(tmp_path):
    """A case-only rename on a case-insensitive FS leaves the old spelling naming the
    file just written; a hard link reproduces that aliasing on every filesystem."""
    out = tmp_path / "out"
    out.mkdir()
    written = out / "demo.md"
    written.write_text(f"<!-- {SENTINEL} -->\nfresh\n", encoding="utf-8")
    os.link(written, out / "Demo-alias.md")
    adapter = _ScannedAdapter(out)

    assert adapter.cleanup_stale({written.resolve()}, tmp_path) == []
    assert written.read_text(encoding="utf-8").endswith("fresh\n")


# --- the hook additions (specs/prK-lifecycle-hooks.md §C.1.1) ---------------------------


_LOCK = Lockfile(schema_version=2, engine_version="0.1.0", rendered_at="2026-10-15T00:00:00Z")


class _RuleRecordingAdapter(_DummyAdapter):
    """Records every rule ``write_rule`` receives and reports one path per rule."""

    name = "recording"

    def __init__(self) -> None:
        super().__init__()
        self.written_rules: list[Rule] = []

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        self.written_rules.append(rule)
        return [repo_root / f"{rule.frontmatter.id}.md"]


def test_write_hook_default_routes_advisory_to_write_rule(tmp_path: Path) -> None:
    adapter = _RuleRecordingAdapter()
    hook = resolved_hook(body="Never edit generated files.\n")

    written = adapter.write_hook(hook, tmp_path)

    assert written == [tmp_path / "guardrail-guard-x.md"]
    (rule,) = adapter.written_rules
    assert rule is hook.advisory
    assert rule.frontmatter.priority == 30
    assert rule.body.startswith("Never edit generated files.\n\n*Enforced by")


def test_write_hook_default_writes_nothing_for_none_advisory(tmp_path: Path) -> None:
    adapter = _RuleRecordingAdapter()
    hook = resolved_hook(body="   \n")

    assert hook.advisory is None
    assert adapter.write_hook(hook, tmp_path) == []
    assert adapter.written_rules == []


def test_begin_sync_and_managed_lock_entries_defaults(tmp_path: Path) -> None:
    adapter = _DummyAdapter()

    adapter.begin_sync(tmp_path, None)
    adapter.begin_sync(tmp_path, _LOCK, hooks_config=HooksConfig(enabled=True))

    assert adapter.managed_lock_entries() == []
    assert adapter.finalize(tmp_path) == []
    assert dict(Adapter.hook_support) == {}
    assert Adapter.shared_outputs == ()


def test_note_native_skill_roots_default_is_a_no_op(tmp_path: Path) -> None:
    """An out-of-tree adapter that ignores the call writes exactly what it wrote before."""
    adapter = _DummyAdapter()

    adapter.note_native_skill_roots(frozenset())
    adapter.note_native_skill_roots(frozenset({".claude/skills"}))

    assert adapter.finalize(tmp_path) == []
    assert list(tmp_path.iterdir()) == []


def test_hook_support_default_is_read_only() -> None:
    with pytest.raises(TypeError):
        Adapter.hook_support["pre_tool_use"] = frozenset({"deny"})  # type: ignore[index]


def test_third_party_adapter_without_hook_overrides_still_works(tmp_path: Path) -> None:
    """An adapter written against the pre-hook ABC (rules + prompts only) still syncs hooks."""

    class _LegacyAdapter(Adapter):
        name = "legacy"

        def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
            target = repo_root / "legacy" / f"{rule.frontmatter.id}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rule.body, encoding="utf-8")
            return [target]

        def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
            return []

    adapter = _LegacyAdapter()
    adapter.begin_sync(tmp_path, None)
    written = adapter.write_hook(resolved_hook(), tmp_path)

    assert written == [tmp_path / "legacy" / "guardrail-guard-x.md"]
    assert adapter.finalize(tmp_path) == []
    assert adapter.managed_lock_entries() == []


@pytest.mark.parametrize(
    ("adapter_cls", "delivers"),
    [
        (_DummyAdapter, True),
        (AgentHarnessAdapter, True),
        (AgentsMdAdapter, False),
        (ClaudeCodeAdapter, True),
        (ContinueAdapter, True),
        (OpenCodeAdapter, True),
        (SharedSkillsAdapter, True),
    ],
)
def test_delivers_member_rules_defaults_true_and_agents_md_is_false(
    adapter_cls: type[Adapter], delivers: bool
) -> None:
    """An out-of-tree adapter still gets every rule through write_rule, so True is the
    default; only agents_md carries always rules alone (specs/prS-skills-context.md 6.4.10)."""
    assert adapter_cls.delivers_member_rules is delivers
