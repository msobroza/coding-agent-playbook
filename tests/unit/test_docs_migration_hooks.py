"""Docs-consistency guard: MIGRATION.md carries the lifecycle-hooks upgrade (prK §H Track K11).

PR K is opt-in, but a few changes reach every consumer on upgrade: the
validate-gated sync, lockfile schema 2, the ``.local.toml`` policy exclusion,
``--no-run-tests`` on the metrics hooks, the ``CoverageCheck`` fix, the PEP 503
``detector_cache`` churn (OQ-36), the one-time heartbeat line (OQ-30), the
adapter ABC additions and the Claude Code rules' move to
``.claude/rules/coding-agent-playbook.md``. Each test reads its expected text from the landed code
where one exists (the lockfile schema, the sync abort and absent-table lines,
the heartbeat line, the ``Adapter`` members, the ``CoverageCheck`` default), so
the guide cannot drift from what shipped. Prose-only: no engine behaviour runs.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from coding_agent_playbook._pep503 import canonical_name
from coding_agent_playbook.adapters._claude_hooks import CLAUDE_HEARTBEAT_LINE
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.claude_rule_paths import CLAUDE_RULES_PATH
from coding_agent_playbook.commands._sync_hooks import HOOKS_NOTICE
from coding_agent_playbook.commands._sync_lockfile import LOCKFILE_SCHEMA
from coding_agent_playbook.commands.sync import _ABORT_OUTCOME
from coding_agent_playbook.evaluators.checks.execution import CoverageCheck

_ROOT = Path(__file__).resolve().parents[2]
_V020 = "## v0.20 — Assistant lifecycle hooks (PR K)"
_RELEASE_VERSION = re.compile(r"^## v(\d+)\.(\d+)\b", re.MULTILINE)

#: The ``Adapter`` members PR K added; out-of-tree adapter authors read about each.
_ADAPTER_HOOK_MEMBERS = (
    "hook_support",
    "shared_outputs",
    "runtime_outputs",
    "begin_sync",
    "write_hook",
    "managed_lock_entries",
)

#: Each numbered topic of the v0.20 section, in the order a consumer meets them.
_TOPIC_ORDER = (
    "Lockfile",
    "playbook validate",
    "[hooks]",
    ".local.toml",
    "--no-run-tests",
    "CoverageCheck",
    "metrics",
    "PEP 503",
    "heartbeat",
    "adapter",
    "catalog/",
    ".claude/rules/",
)


def _migration() -> str:
    return (_ROOT / "MIGRATION.md").read_text(encoding="utf-8")


def _v020_section() -> str:
    text = _migration()
    start = text.index(_V020)
    end = text.find("\n## ", start + len(_V020))
    return text[start : end if end > 0 else len(text)]


def _release_versions(text: str) -> list[tuple[int, int]]:
    """The ``(major, minor)`` of every ``## v<major>.<minor>`` release heading, in file order."""
    headings = re.findall(r"^## v.*$", text, re.MULTILINE)
    versions = [(int(major), int(minor)) for major, minor in _RELEASE_VERSION.findall(text)]
    assert len(versions) == len(headings), f"a release heading has no vX.Y version: {headings}"
    return versions


def test_migration_has_v0_20_lifecycle_hooks_section() -> None:
    text = _migration()
    assert _V020 in text
    versions = _release_versions(text)
    assert versions == sorted(versions, reverse=True), f"newest release first, got {versions}"
    assert "### TL;DR — who needs to do anything" in _v020_section()


def test_migration_heads_up_points_at_v0_20() -> None:
    text = _migration()
    heads_up = text[: text.index("\n## ")]
    assert "v0.20" in heads_up and "playbook validate" in heads_up


@pytest.mark.parametrize(
    "phrase",
    [
        f"schema_version = {LOCKFILE_SCHEMA}",
        _ABORT_OUTCOME,
        HOOKS_NOTICE,
        "--no-hooks",
        ".coding-agent-playbook.local.toml",
        "--no-run-tests",
        "extend_select",
        "detector_cache",
        CLAUDE_HEARTBEAT_LINE,
        "hook_support",
        CLAUDE_RULES_PATH,
        "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT",
    ],
)
def test_migration_v0_20_covers_topic(phrase: str) -> None:
    assert phrase in _v020_section()


def test_migration_v0_20_names_the_coverage_check_fix() -> None:
    default = inspect.signature(CoverageCheck).parameters["warn"].default
    section = _v020_section()
    assert f"warn={default}" in section and "warn=80.0" in section


def test_migration_v0_20_shows_the_pep_503_spelling() -> None:
    section = _v020_section()
    assert f"`Foo_Bar` → `{canonical_name('Foo_Bar')}`" in section


@pytest.mark.parametrize("member", _ADAPTER_HOOK_MEMBERS)
def test_migration_names_every_new_adapter_member(member: str) -> None:
    assert hasattr(Adapter, member), f"Adapter has no {member!r}: update the guide and this list"
    assert f"`{member}`" in _v020_section()


def test_migration_folds_in_the_stale_outputs_port() -> None:
    section = _v020_section()
    assert "def stale_outputs(self, written_paths, repo_root):" in section
    assert "overrides cleanup_stale() but not stale_outputs()" in section
    # Track P shipped with PR K, so its adapter note lives in the v0.20 section.
    assert "## v0.16 — Out-of-tree adapters" not in _migration()


def test_migration_v0_20_topics_follow_upgrade_order() -> None:
    headings = re.findall(r"^### (\d+)\. (.+)$", _v020_section(), re.MULTILINE)
    assert [int(number) for number, _ in headings] == list(range(1, len(_TOPIC_ORDER) + 1))
    for (_, title), keyword in zip(headings, _TOPIC_ORDER, strict=True):
        assert keyword in title, f"topic {title!r} should be about {keyword!r}"
