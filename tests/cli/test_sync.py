"""End-to-end tests for ``playbook sync`` (PR 10 Task 2 + Task 3).

Builds a synthetic consumer repo, runs sync programmatically, and asserts
adapter outputs landed in the expected places plus the lockfile carries
the right entries.
"""

from __future__ import annotations

import argparse
import dataclasses
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.detector import detect
from coding_agent_playbook.lockfile import LockEntry, Lockfile, Provenance, compute_hash
from coding_agent_playbook.orchestrator import SyncContext
from coding_agent_playbook.sources.filesystem import FileSystemStateSource
from coding_agent_playbook.types import Prompt, PromptFrontmatter, Rule, RuleFrontmatter

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.detector import Facts

    SyntheticRepoFactory = Callable[..., Path]


def _ns(repo: Path, **kwargs: object) -> argparse.Namespace:
    base = {"repo_root": str(repo), "check": False}
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_sync_writes_continue_rules_and_agents_md(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("style-guide", "Use spaces, not tabs.\n")],
        prompts=[("refactor", {"slash": "refactor", "body": "Refactor the code.\n"})],
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
    continue_prompt = repo / ".continue" / "prompts" / "refactor.md"
    assert continue_prompt.is_file()
    # claude code prompt slash command
    claude_command = repo / ".claude" / "commands" / "refactor.md"
    assert claude_command.is_file()
    # opencode prompt slash command
    opencode_command = repo / ".opencode" / "command" / "refactor.md"
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
    claude_md = _entry(lockfile, ".claude/CLAUDE.md")
    assert _provenance_of(claude_md) == ("composite", "", "", "claude_code")
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
    until hook-capable adapters contribute scoped entries."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    result = _sync._run_sync(SyncContext.from_repo(repo))
    assert isinstance(result, _sync.SyncResult)
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
    recorder = _sync._dispatch_to_adapters(adapters, rules, [prompt], [], tmp_path)
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
    lockfile = _sync._build_lockfile(
        [settings, agents],
        tmp_path,
        "0.2.0",
        {agents.resolve(): composite, settings.resolve(): composite},
        (scoped,),
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


# --- sync --check: orphans + hygienic scratch copy (specs/prK-lifecycle-hooks.md §P P2) ---

_ORPHAN_HINT = "    Orphaned generated file; run 'playbook sync' to remove."


def _orphan_line(rel: str) -> str:
    return f"  {rel}\n{_ORPHAN_HINT}"


def _check(repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    """Run ``playbook sync --check`` on ``repo``; return (exit code, stdout)."""
    capsys.readouterr()
    rc = _sync.run(_ns(repo, check=True))
    return rc, capsys.readouterr().out


def _write_gated_rule(repo: Path, rule_id: str, applies_if: str) -> None:
    """Write a repo-local rule whose frontmatter carries ``applies_if`` (YAML text)."""
    target = repo / "playbook" / "rules" / f"{rule_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"---\nid: {rule_id}\nname: Gated\ndescription: d\nscope: always\npriority: 50\n"
        f"applies_if:\n  {applies_if}\n---\nGated body for {rule_id}.\n",
        encoding="utf-8",
    )


def _write_skill(repo: Path, skill_id: str) -> None:
    skill_dir = repo / "playbook" / "skills" / skill_id
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: {skill_id}\nname: Skill\ndescription: Do it.\n---\nRun it.\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "run.sh").write_text("echo hi\n", encoding="utf-8")


@dataclasses.dataclass
class ScratchCopyRecord:
    """What one spied ``shutil.copytree`` call of the repo produced."""

    ignored: dict[str, set[str]]  # directory -> names the ``ignore`` callable skipped
    kinds: dict[str, str]  # scratch-relative path -> "link" | "dir" | "file"


def _spy_scratch_copy(monkeypatch: pytest.MonkeyPatch, repo: Path) -> list[ScratchCopyRecord]:
    """Wrap ``shutil.copytree``: record the ignore decisions and the tree it
    produced for every copy whose source is ``repo`` (adapters' own copies pass)."""
    real_copytree = shutil.copytree
    records: list[ScratchCopyRecord] = []

    def spy(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
        if Path(src) != repo:
            return real_copytree(src, dst, *args, **kwargs)
        ignored: dict[str, set[str]] = {}
        ignore = kwargs.get("ignore")

        def recording(directory: str, names: list[str]) -> set[str]:
            skipped = set(ignore(directory, names)) if ignore is not None else set()
            ignored[directory] = skipped
            return skipped

        kwargs["ignore"] = recording
        result = real_copytree(src, dst, *args, **kwargs)
        records.append(ScratchCopyRecord(ignored=ignored, kinds=_tree_kinds(Path(dst))))
        return result

    monkeypatch.setattr(shutil, "copytree", spy)
    return records


def _tree_kinds(root: Path) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for path in root.rglob("*"):
        kind = "link" if path.is_symlink() else "dir" if path.is_dir() else "file"
        kinds[path.relative_to(root).as_posix()] = kind
    return kinds


def test_check_reports_orphaned_generated_file(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """A deleted rule's generated file is reported (once) as an orphan."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    assert _sync.run(_ns(repo)) == 0
    (repo / "playbook" / "rules" / "x.md").unlink()
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert _orphan_line(".continue/rules/50-x.md") in out
    # Found by both the scratch cleanup and the lockfile; reported once.
    assert out.count(".continue/rules/50-x.md") == 1
    assert (repo / ".continue" / "rules" / "50-x.md").is_file()  # real tree untouched


def test_check_fails_on_sentinel_orphan_alone(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stale sentinel-tagged output is drift even when nothing else differs."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    assert _sync.run(_ns(repo)) == 0
    stale = repo / ".continue" / "rules" / "99-stale.md"
    stale.write_text(f"{sentinel_line('html')}\nstale\n", encoding="utf-8")
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert out.startswith("Drift detected:\n")
    assert _orphan_line(".continue/rules/99-stale.md") in out
    assert "Generated content differs" not in out
    assert stale.is_file()


def test_check_reports_lockfile_orphan_without_sentinel(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """A removed skill's sentinel-less outputs are orphans via the lockfile."""
    repo = make_synthetic_repo(tmp_path)
    _write_skill(repo, "query-db")
    assert _sync.run(_ns(repo)) == 0
    shutil.rmtree(repo / "playbook" / "skills" / "query-db")
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert _orphan_line(".claude/skills/query-db/scripts/run.sh") in out
    assert _orphan_line(".claude/skills/query-db/SKILL.md") in out


def test_check_lockfile_orphan_needs_existing_whole_file(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only an unscoped, in-repo lock entry whose file still exists is an orphan."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = make_synthetic_repo(repo_dir, rules=[("x", "Body of x\n")])
    assert _sync.run(_ns(repo)) == 0
    for rel in ("kept.txt", "scoped.json", "../outside.txt"):
        (repo / rel).write_text("generated once\n", encoding="utf-8")
    state = FileSystemStateSource(repo_root=repo)
    lockfile = state.load_lockfile()
    assert lockfile is not None
    lockfile.entries += [
        LockEntry(path="kept.txt", sha256="0", bytes=1, kind="skill"),
        LockEntry(path="gone.txt", sha256="0", bytes=1, kind="skill"),
        LockEntry(path="scoped.json", sha256="0", bytes=1, kind="runtime", scope="json:/x"),
        LockEntry(path="../outside.txt", sha256="0", bytes=1),
    ]
    state.save_lockfile(lockfile)
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert out.count("Orphaned generated file") == 1
    assert _orphan_line("kept.txt") in out


def test_check_reports_unreadable_lockfile(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """A conflicted lockfile is drift with a clear line, never a traceback."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    assert _sync.run(_ns(repo)) == 0
    (repo / ".coding-agent-playbook.lock").write_text("<<<<<<< HEAD\n", encoding="utf-8")
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert "  .coding-agent-playbook.lock\n    Unreadable lockfile (" in out


def test_check_scratch_excludes_ignored_and_secret_paths(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VCS, envs, caches, build outputs and secret files never reach the scratch tree."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    for rel in (
        ".venv/lib/site.py",
        ".git/HEAD",
        "node_modules/pkg/index.js",
        ".ruff_cache/0.1/x",
        "dist/pkg.whl",
        "src/pkg/__pycache__/m.pyc",
        "certs/server.pem",
    ):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("x\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (repo / ".env.example").write_text("TOKEN=\n", encoding="utf-8")
    assert _sync.run(_ns(repo)) == 0
    records = _spy_scratch_copy(monkeypatch, repo)
    rc, _ = _check(repo, capsys)
    assert rc == 0
    [record] = records
    assert {".venv", ".git", ".env", "node_modules", ".ruff_cache", "dist"} <= record.ignored[
        str(repo)
    ]
    assert ".env.example" not in record.ignored[str(repo)]
    for rel in (".venv", ".git", ".env", "node_modules", "dist", "certs/server.pem"):
        assert rel not in record.kinds
    assert "src/pkg/__pycache__" not in record.kinds
    assert record.kinds[".env.example"] == "file"
    assert record.kinds["playbook/rules/x.md"] == "file"


def test_check_scratch_keeps_canonical_sources_verbatim(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``playbook/`` is sync input: a ``build`` skill or a ``*credentials*`` rule is
    copied, so the scratch run renders the same artifact set (no false drift)."""
    repo = make_synthetic_repo(tmp_path, rules=[("handling-credentials", "Rotate keys.\n")])
    _write_skill(repo, "build")
    assert _sync.run(_ns(repo)) == 0
    records = _spy_scratch_copy(monkeypatch, repo)
    rc, out = _check(repo, capsys)
    assert rc == 0, out
    [record] = records
    assert record.kinds["playbook/rules/handling-credentials.md"] == "file"
    assert record.kinds["playbook/skills/build/SKILL.md"] == "file"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_check_skips_symlink_outside_repo(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A link resolving outside the repo is skipped; an in-repo link is copied as content."""
    outside = tmp_path / "home" / ".ssh"
    outside.mkdir(parents=True)
    (outside / "id_rsa").write_text("PRIVATE\n", encoding="utf-8")
    (tmp_path / "home" / "notes.txt").write_text("outside\n", encoding="utf-8")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = make_synthetic_repo(repo_dir, rules=[("x", "Body of x\n")])
    (repo / "docs").mkdir()
    (repo / "docs" / "inside.md").write_text("inside\n", encoding="utf-8")
    (repo / "ssh").symlink_to(outside, target_is_directory=True)
    (repo / "notes.txt").symlink_to(tmp_path / "home" / "notes.txt")
    (repo / "alias.md").symlink_to(repo / "docs" / "inside.md")
    (repo / "dangling.md").symlink_to(repo / "missing.md")
    assert _sync.run(_ns(repo)) == 0
    records = _spy_scratch_copy(monkeypatch, repo)
    rc, out = _check(repo, capsys)
    assert rc == 0, out
    [record] = records
    assert {"ssh", "notes.txt", "dangling.md"} <= record.ignored[str(repo)]
    assert not any(rel.startswith("ssh") for rel in record.kinds)
    assert record.kinds["alias.md"] == "file"  # dereferenced, never written through
    assert "alias.md" not in record.ignored[str(repo)]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_check_skips_symlink_into_excluded_path_or_ancestor(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An innocuous link name never smuggles a secret or an ignored dir into the
    scratch tree, and a link to its own ancestor is not followed forever."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    (repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (repo / ".venv").mkdir()
    (repo / "settings.txt").symlink_to(repo / ".env")
    (repo / "env").symlink_to(repo / ".venv", target_is_directory=True)
    (repo / "loop").symlink_to(repo, target_is_directory=True)
    assert _sync.run(_ns(repo)) == 0
    records = _spy_scratch_copy(monkeypatch, repo)
    rc, out = _check(repo, capsys)
    assert rc == 0, out
    [record] = records
    assert {"settings.txt", "env", "loop"} <= record.ignored[str(repo)]


def test_check_facts_not_flipped_by_scratch_exclusions(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Facts are detected once, on the real repo: a notebook under the excluded
    ``build/`` keeps ``has_notebooks`` true for the scratch run."""
    repo = make_synthetic_repo(tmp_path)
    (repo / "build").mkdir()
    (repo / "build" / "analysis.ipynb").write_text("{}\n", encoding="utf-8")
    _write_gated_rule(repo, "notebook-hygiene", "has_notebooks: true")
    assert _sync.run(_ns(repo)) == 0
    assert (repo / ".continue" / "rules" / "50-notebook-hygiene.md").is_file()
    detected: list[Path] = []

    def spy_detect(root: Path) -> Facts:
        detected.append(root)
        return detect(root)

    monkeypatch.setattr("coding_agent_playbook.orchestrator.detect", spy_detect)
    scratch_facts: list[Facts] = []
    real_run_sync = _sync._run_sync

    def spy_run_sync(ctx: SyncContext, **kwargs: Any) -> _sync.SyncResult:
        scratch_facts.append(ctx.facts)
        return real_run_sync(ctx, **kwargs)

    monkeypatch.setattr(_sync, "_run_sync", spy_run_sync)
    rc, out = _check(repo, capsys)
    assert rc == 0, out
    assert detected == [repo]
    assert [facts.get("has_notebooks") for facts in scratch_facts] == [True]


def test_check_has_file_predicate_sees_real_repo(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """``applies_if: has_file`` is evaluated against the real repo, so a path the
    scratch copy excludes (``.env``) never flips the rendered rule set."""
    repo = make_synthetic_repo(tmp_path)
    (repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    _write_gated_rule(repo, "dotenv-hygiene", 'has_file: [".env"]')
    assert _sync.run(_ns(repo)) == 0
    assert (repo / ".continue" / "rules" / "50-dotenv-hygiene.md").is_file()
    rc, out = _check(repo, capsys)
    assert rc == 0, out


# --- sandboxed Jinja (specs/prK-lifecycle-hooks.md §P P1) ---------------------

_ESCAPE_BODY = '{{ lipsum.__globals__["os"].__name__ }}\n'


def _write_templated_rule(repo: Path, rule_id: str, body: str) -> Path:
    """Write a repo-local ``.md.j2`` rule (rendered through Jinja) and return its path."""
    target = repo / "playbook" / "rules" / f"{rule_id}.md.j2"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"---\nid: {rule_id}\nname: Templated\ndescription: d\nscope: always\npriority: 50\n"
        f"---\n{body}",
        encoding="utf-8",
    )
    return target


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` (repo-relative posix path -> bytes)."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_sync_fails_loudly_on_sandbox_violation(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("benign", "Benign body.\n")])
    _write_templated_rule(repo, "escape", _ESCAPE_BODY)
    before = _tree_snapshot(repo)
    rc = _sync.run(_ns(repo))
    assert rc != 0
    err = capsys.readouterr().err
    assert "playbook/rules/escape.md.j2" in err
    assert str(tmp_path) not in err  # named repo-relative, not by absolute path
    assert "unsafe" in err  # jinja2's SecurityError detail is surfaced
    assert _tree_snapshot(repo) == before  # nothing written, no lockfile


def test_sync_check_fails_loudly_on_sandbox_violation(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--check`` renders in a scratch copy; the error still names the repo file."""
    repo = make_synthetic_repo(tmp_path)
    assert _sync.run(_ns(repo)) == 0
    _write_templated_rule(repo, "escape", _ESCAPE_BODY)
    before = _tree_snapshot(repo)
    capsys.readouterr()
    rc = _sync.run(_ns(repo, check=True))
    assert rc != 0
    err = capsys.readouterr().err
    assert "error: playbook/rules/escape.md.j2:" in err
    assert "playbook-sync-check-" not in err  # never the deleted scratch path
    assert _tree_snapshot(repo) == before
