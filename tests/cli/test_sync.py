"""End-to-end tests for ``playbook sync`` (PR 10 Task 2 + Task 3).

Builds a synthetic consumer repo, runs sync programmatically, and asserts
adapter outputs landed in the expected places plus the lockfile carries
the right entries — schema 2, with provenance on every entry
(specs/prK-lifecycle-hooks.md §P P4). ``--check`` orphans live in
``test_sync_check.py``; the Jinja sandbox in ``test_sync_sandbox.py``; the
validate gate (§P P8) in ``test_sync_validate_gate.py``.
"""

from __future__ import annotations

import argparse
import dataclasses
import shutil
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.commands import _sync_lockfile
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.lockfile import LockEntry, Lockfile, Provenance, compute_hash
from coding_agent_playbook.orchestrator import SyncContext
from coding_agent_playbook.types import Prompt, PromptFrontmatter, Rule, RuleFrontmatter
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]


def _ns(repo: Path, **kwargs: object) -> argparse.Namespace:
    base = {"repo_root": str(repo), "check": False}
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_sync_writes_continue_rules_and_agents_md(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("style-guide", "Use spaces, not tabs.\n")],
        # Not an engine prompt id: overriding one (``refactor``) without its
        # eval_tasks fails validate, so sync would refuse to write (prK §P P8).
        prompts=[("tidy-up", {"slash": "tidy-up", "body": "Tidy up the code.\n"})],
    )
    rc = _sync.run(_ns(repo))
    assert rc == 0
    # Continue adapter must have written its rule file.
    continue_rule = repo / ".continue" / "rules" / "50-style-guide.md"
    assert continue_rule.is_file()
    # AGENTS.md is always generated.
    agents_md = repo / "AGENTS.md"
    assert agents_md.is_file()
    # Continue prompt landed under .continue/prompts.
    continue_prompt = repo / ".continue" / "prompts" / "tidy-up.md"
    assert continue_prompt.is_file()
    # claude code prompt slash command
    claude_command = repo / ".claude" / "commands" / "tidy-up.md"
    assert claude_command.is_file()
    # opencode prompt slash command
    opencode_command = repo / ".opencode" / "command" / "tidy-up.md"
    assert opencode_command.is_file()


def test_sync_stamps_lockfile(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("a-rule", "A rule body\n")],
    )
    rc = _sync.run(_ns(repo))
    assert rc == 0
    state = FileSystemStateSource(repo_root=repo)
    lockfile = state.load_lockfile()
    assert isinstance(lockfile, Lockfile)
    assert lockfile.schema_version == 2
    # Lockfile should reference at least the AGENTS.md and continue rule outputs.
    paths = [entry.path for entry in lockfile.entries]
    assert "AGENTS.md" in paths
    assert ".continue/rules/50-a-rule.md" in paths
    # Each entry has a sha256 + bytes count.
    for entry in lockfile.entries:
        assert entry.sha256
        assert entry.bytes > 0


def test_sync_uses_cwd_when_repo_root_not_set(tmp_path, make_synthetic_repo, monkeypatch):
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    monkeypatch.chdir(repo)
    rc = _sync.run(argparse.Namespace(repo_root=None, check=False))
    assert rc == 0
    assert (repo / "AGENTS.md").is_file()


def test_sync_prints_summary_line(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    rc = _sync.run(_ns(repo))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Summary:" in out
    assert "files written" in out


def test_sync_no_artifacts_still_succeeds(tmp_path, make_synthetic_repo):
    """A repo with no rules/prompts is valid; sync should succeed and the
    lockfile should be created (possibly empty)."""
    repo = make_synthetic_repo(tmp_path)
    rc = _sync.run(_ns(repo))
    assert rc == 0
    state = FileSystemStateSource(repo_root=repo)
    assert state.load_lockfile() is not None


# --- playbook sync --check (drift detection) -----------------------------------


def test_sync_check_clean_repo_returns_zero(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    # Build the on-disk artifacts first.
    assert _sync.run(_ns(repo)) == 0
    capsys.readouterr()  # clear
    rc = _sync.run(_ns(repo, check=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "No drift" in out


def test_sync_check_detects_modified_file(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Original body\n")])
    assert _sync.run(_ns(repo)) == 0
    # Mutate the rendered file so the next --check sees drift.
    agents_md = repo / "AGENTS.md"
    agents_md.write_text(agents_md.read_text() + "\nMUTATED LINE\n")
    capsys.readouterr()
    rc = _sync.run(_ns(repo, check=True))
    assert rc == 1
    out = capsys.readouterr().out
    assert "Drift detected" in out
    assert "AGENTS.md" in out


def test_sync_check_detects_missing_file(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("y", "Body y\n")])
    assert _sync.run(_ns(repo)) == 0
    # Delete a written file to simulate a drift-by-omission case.
    (repo / "AGENTS.md").unlink()
    capsys.readouterr()
    rc = _sync.run(_ns(repo, check=True))
    assert rc == 1
    out = capsys.readouterr().out
    assert "Missing" in out or "AGENTS.md" in out


# --- lockfile schema v2: provenance (specs/prK-lifecycle-hooks.md §P P4) -------


def _sync_and_load_lockfile(repo: Path) -> Lockfile:
    assert _sync.run(_ns(repo)) == 0
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return lockfile


def _entry(lockfile: Lockfile, path: str) -> LockEntry:
    entry = lockfile.find(path)
    assert entry is not None, f"no lockfile entry for {path!r}"
    return entry


def _provenance_of(entry: LockEntry) -> tuple[str, str, str, str]:
    return (entry.kind, entry.artifact_id, entry.source, entry.adapter)


def test_lockfile_records_rule_provenance(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """Each per-rule output names its rule, its source package and its adapter."""
    repo = make_synthetic_repo(tmp_path, rules=[("a-rule", "A rule body\n")])
    lockfile = _sync_and_load_lockfile(repo)
    engine_rule = _entry(lockfile, ".continue/rules/10-python-house-style.md")
    assert _provenance_of(engine_rule) == (
        "rule",
        "python-house-style",
        "coding_agent_playbook",
        "continue",
    )
    local_rule = _entry(lockfile, ".continue/rules/50-a-rule.md")
    assert _provenance_of(local_rule) == ("rule", "a-rule", "<repo-local>", "continue")
    assert (engine_rule.scope, engine_rule.executable) == ("", False)


def test_lockfile_records_prompt_provenance(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = make_synthetic_repo(
        tmp_path, prompts=[("tidy", {"slash": "tidy", "body": "Tidy up.\n"})]
    )
    lockfile = _sync_and_load_lockfile(repo)
    for path, adapter in (
        (".claude/commands/tidy.md", "claude_code"),
        (".opencode/command/tidy.md", "opencode"),
        (".continue/prompts/tidy.md", "continue"),
    ):
        entry = _entry(lockfile, path)
        assert _provenance_of(entry) == ("prompt", "tidy", "<repo-local>", adapter)


def test_lockfile_records_skill_provenance(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """``SKILL.md`` and copied scripts carry no sentinel; the lockfile owns them."""
    repo = make_synthetic_repo(tmp_path)
    skill_dir = repo / "playbook" / "skills" / "query-db"
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nid: query-db\nname: Query DB\ndescription: Query it.\n---\nRun it.\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "run.sh").write_text("echo hi\n", encoding="utf-8")
    lockfile = _sync_and_load_lockfile(repo)
    for path in (".claude/skills/query-db/SKILL.md", ".claude/skills/query-db/scripts/run.sh"):
        entry = _entry(lockfile, path)
        assert _provenance_of(entry) == ("skill", "query-db", "<repo-local>", "claude_code")


def test_claude_md_is_composite(tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory) -> None:
    """Multi-artifact outputs composed in ``finalize`` are ``kind="composite"``."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    lockfile = _sync_and_load_lockfile(repo)
    for path in (".claude/CLAUDE.md", ".claude/rules/coding-agent-playbook.md"):
        assert _provenance_of(_entry(lockfile, path)) == ("composite", "", "", "claude_code")
    agents_md = _entry(lockfile, "AGENTS.md")
    assert _provenance_of(agents_md) == ("composite", "", "", "agents_md")
    text = (repo / ".coding-agent-playbook.lock").read_text(encoding="utf-8")
    assert 'artifact_id = ""' not in text


def test_sync_rewrites_v1_lockfile_as_v2(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """A v1 lockfile on disk loads, and the first sync rewrites it as schema 2."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    (repo / ".coding-agent-playbook.lock").write_text(
        'schema_version = 1\nengine_version = "0.1.0a0"\n'
        'rendered_at = "2026-05-28T12:00:00Z"\n\n'
        '[[entries]]\npath = "AGENTS.md"\nsha256 = "abc"\nbytes = 3\n',
        encoding="utf-8",
    )
    state = FileSystemStateSource(repo_root=repo)
    v1 = state.load_lockfile()
    assert v1 is not None
    assert _provenance_of(_entry(v1, "AGENTS.md")) == ("", "", "", "")
    lockfile = _sync_and_load_lockfile(repo)
    assert lockfile.schema_version == 2
    assert _entry(lockfile, "AGENTS.md").kind == "composite"


def test_run_sync_returns_frozen_sync_result(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """``_run_sync`` returns one frozen ``SyncResult``; ``managed`` is empty
    without hooks (only hook-capable adapters contribute scoped entries)."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    ctx = SyncContext.from_repo(repo)
    result = _sync._run_sync(ctx, _sync._leftover_policy(ctx, FakeGitClient(), None))
    assert isinstance(result, _sync_lockfile.SyncResult)
    assert result.managed == ()
    assert result.removed == ()
    assert result.written
    assert {p.resolve() for p in result.written} == set(result.provenance)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.written = ()  # type: ignore[misc]


class FakeSharedPathAdapter(Adapter):
    """Writes every rule into one shared file and finalizes a second file."""

    name = "fake_shared"

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        target = repo_root / "shared.md"
        with target.open("a", encoding="utf-8") as fh:
            fh.write(rule.body)
        return [target]

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        target = repo_root / f"{prompt.frontmatter.id}.md"
        target.write_text(prompt.body, encoding="utf-8")
        return [target]

    def finalize(self, repo_root: Path) -> list[Path]:
        target = repo_root / "index.md"
        target.write_text("index\n", encoding="utf-8")
        return [target]


def _rule(rule_id: str, source: str) -> Rule:
    frontmatter = RuleFrontmatter(id=rule_id, name=rule_id, description="d", scope="always")
    return Rule(frontmatter, "body\n", "body\n", False, None, source)


def test_dispatch_marks_multi_artifact_path_composite(tmp_path: Path) -> None:
    """A path written by two different artifacts, or by ``finalize``, is composite;
    a path written by one artifact keeps that artifact's provenance."""
    adapters = {"fake_shared": FakeSharedPathAdapter()}
    rules = [_rule("one", "<repo-local>"), _rule("two", "pkg")]
    solo = PromptFrontmatter(id="solo", name="solo", description="d", slash="solo")
    prompt = Prompt(solo, "p\n", "p\n", False, None, "pkg")
    recorder = _sync_lockfile.dispatch_to_adapters(adapters, rules, [prompt], [], tmp_path)
    provenance = recorder.provenance
    shared = (tmp_path / "shared.md").resolve()
    assert provenance[shared] == Provenance(kind="composite", adapter="fake_shared")
    assert provenance[(tmp_path / "index.md").resolve()] == Provenance(
        kind="composite", adapter="fake_shared"
    )
    assert provenance[(tmp_path / "solo.md").resolve()] == Provenance(
        kind="prompt", artifact_id="solo", source="pkg", adapter="fake_shared"
    )
    assert len(recorder.written) == 4  # duplicates kept: the summary count is unchanged


def test_build_lockfile_scoped_entries_replace_whole_file_entry(tmp_path: Path) -> None:
    """A path with any ``managed`` (scoped) entry gets no whole-file entry."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text('{"hooks": {}}\n', encoding="utf-8")
    agents = tmp_path / "AGENTS.md"
    agents.write_text("agents\n", encoding="utf-8")
    scoped = LockEntry(
        path=".claude/settings.json",
        sha256="41ab",
        bytes=212,
        kind="runtime",
        artifact_id="registration:pre_tool_use",
        adapter="claude_code",
        scope="json:/hooks/PreToolUse",
    )
    composite = Provenance(kind="composite", adapter="agents_md")
    lockfile = _sync_lockfile.build_lockfile(
        [settings, agents],
        tmp_path,
        "0.2.0",
        provenance={agents.resolve(): composite, settings.resolve(): composite},
        managed=(scoped,),
    )
    assert lockfile.schema_version == 2
    assert lockfile.entries == [
        LockEntry(
            path="AGENTS.md",
            sha256=compute_hash(b"agents\n"),
            bytes=7,
            kind="composite",
            adapter="agents_md",
        ),
        scoped,
    ]


def test_build_lockfile_appends_carried_orphans_unchanged(tmp_path: Path) -> None:
    """Kept orphans (main's leftover policy) ride along with their v2 fields intact."""
    agents = tmp_path / "AGENTS.md"
    agents.write_text("agents\n", encoding="utf-8")
    carried = LockEntry(
        path=".claude/skills/old/scripts/run.sh",
        sha256="aa",
        bytes=3,
        kind="skill",
        artifact_id="old",
        source="<repo-local>",
        adapter="claude_code",
    )
    lockfile = _sync_lockfile.build_lockfile(
        [agents], tmp_path, "0.2.0", provenance={}, carried=(carried,)
    )
    assert lockfile.entries[0].path == "AGENTS.md"
    assert lockfile.entries[0].kind == ""  # no recorded origin: v1 unknown provenance
    assert lockfile.entries[1] is carried


# --- lockfile ownership of native skill output (Track Pa review) --------------


def _write_skill(repo: Path, skill_id: str, scripts: dict[str, str]) -> Path:
    skill_dir = repo / "playbook" / "skills" / skill_id
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: {skill_id}\nname: Skill\ndescription: Do it.\n---\nRun it.\n",
        encoding="utf-8",
    )
    for name, body in scripts.items():
        (skill_dir / "scripts" / name).write_text(body, encoding="utf-8")
    return skill_dir


def _lock_paths(repo: Path) -> set[str]:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return {entry.path for entry in lockfile.entries}


def test_lockfile_never_records_user_file_in_generated_skill_dir(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """Regression: the old ``_copy_tree`` returned ``dst.rglob('*')``, so a user file
    dropped into a generated skill dir was stamped ``kind="skill"`` (engine-owned)
    on the next sync. Only files copied from the source are ever recorded."""
    repo = make_synthetic_repo(tmp_path)
    _write_skill(repo, "query-db", {"run.sh": "echo hi\n"})
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    notes = repo / ".claude" / "skills" / "query-db" / "scripts" / "notes.txt"
    notes.write_text("mine\n", encoding="utf-8")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    paths = _lock_paths(repo)
    assert ".claude/skills/query-db/scripts/run.sh" in paths
    assert ".claude/skills/query-db/scripts/notes.txt" not in paths
    assert notes.read_text(encoding="utf-8") == "mine\n"


def test_kept_orphan_keeps_its_provenance(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """An edited leftover the policy keeps is carried with its v2 provenance."""
    repo = make_synthetic_repo(tmp_path)
    skill_dir = _write_skill(repo, "query-db", {"run.sh": "echo hi\n"})
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    script = repo / ".claude" / "skills" / "query-db" / "scripts" / "run.sh"
    script.write_text("echo edited\n", encoding="utf-8")
    shutil.rmtree(skill_dir)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert script.read_text(encoding="utf-8") == "echo edited\n"
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    kept = _entry(lockfile, ".claude/skills/query-db/scripts/run.sh")
    assert _provenance_of(kept) == ("skill", "query-db", "<repo-local>", "claude_code")


# --- includes_rules appendix decided on the template body (SPEC §6.2.5) -------


_ALL_PROMPT_ADAPTERS_CONFIG = """\
schema_version = 1
adapters_enabled = ["continue", "claude_code", "opencode", "agent_harness"]
overlays_enabled = []

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"
"""

_INLINE_RULE_PROMPT = """\
---
id: inline-review
name: Inline review
description: Inlines its rule
slash: inline-review
includes_rules:
  - house-rule
---
Review it.

{{rule("house-rule")}}
"""


def _generated_prompt_files(repo: Path, slash: str) -> list[Path]:
    return [
        repo / ".claude" / "commands" / f"{slash}.md",
        repo / ".continue" / "prompts" / f"{slash}.md",
        repo / ".opencode" / "command" / f"{slash}.md",
        repo / "prompts" / slash / "SKILL.md",
    ]


def test_sync_emits_an_inlined_rule_once_in_every_prompt_adapter(tmp_path, make_synthetic_repo):
    """Regression: an inlined ``rule()`` was also re-appended as a
    ``## Reference rules`` appendix (SPEC §6.2.5 forbids that)."""
    repo = make_synthetic_repo(
        tmp_path,
        config_text=_ALL_PROMPT_ADAPTERS_CONFIG,
        rules=[("house-rule", "HOUSE RULE BODY\n")],
    )
    (repo / "playbook" / "prompts").mkdir(parents=True)
    (repo / "playbook" / "prompts" / "inline-review.md.j2").write_text(
        _INLINE_RULE_PROMPT, encoding="utf-8"
    )

    assert _sync.run(_ns(repo)) == 0

    for path in _generated_prompt_files(repo, "inline-review"):
        content = path.read_text(encoding="utf-8")
        assert content.count("HOUSE RULE BODY") == 1, path
        assert "## Reference rules" not in content, path


def test_sync_still_appends_rules_to_a_prompt_without_inline_calls(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(
        tmp_path,
        config_text=_ALL_PROMPT_ADAPTERS_CONFIG,
        rules=[("house-rule", "HOUSE RULE BODY\n")],
        prompts=[("plain", {"body": "Do it.\n", "includes_rules": ["house-rule"]})],
    )

    assert _sync.run(_ns(repo)) == 0

    for path in _generated_prompt_files(repo, "plain"):
        content = path.read_text(encoding="utf-8")
        assert content.count("HOUSE RULE BODY") == 1, path
        assert "## Reference rules" in content, path


def test_sync_shipped_review_command_inlines_each_rule_once(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(tmp_path)

    assert _sync.run(_ns(repo)) == 0

    review = (repo / ".claude" / "commands" / "review.md").read_text(encoding="utf-8")
    assert review.count("### Typing") == 1
    assert review.count("### Error handling") == 1


def test_sync_migrates_legacy_opencode_commands_to_frontmatter_first(tmp_path, make_synthetic_repo):
    """Commands written with the sentinel on line 1 (older engines) are rewritten
    in place with the envelope first, and a stale legacy command is still cleaned.

    A new prompt id: overriding the engine's ``refactor`` without its ``eval_tasks``
    fails the validate gate ``playbook sync`` runs first (prK §P P8b)."""
    repo = make_synthetic_repo(
        tmp_path, prompts=[("tidy-up", {"slash": "tidy-up", "body": "Tidy the code.\n"})]
    )
    commands = repo / ".opencode" / "command"
    commands.mkdir(parents=True)
    legacy = "<!-- {s} -->\n---\ndescription: old\n---\nold body\n"
    from coding_agent_playbook.renderer import SENTINEL

    (commands / "tidy-up.md").write_text(legacy.format(s=SENTINEL), encoding="utf-8")
    (commands / "gone.md").write_text(legacy.format(s=SENTINEL), encoding="utf-8")

    assert _sync.run(_ns(repo)) == 0

    tidy_up = (commands / "tidy-up.md").read_text(encoding="utf-8")
    assert tidy_up.startswith("---\ndescription:")
    assert tidy_up.count(SENTINEL) == 1
    assert not (commands / "gone.md").exists()
