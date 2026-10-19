"""The protected set sync assembles for ``guard_config.json`` (specs/prK-hook-pack.md §E.0.5, §E.1).

``sync._protect`` turns this sync's written set into lock rows (what the lockfile
records, minus content hashes) and lists the adapters' scan dirs, mapping a
``--check`` scratch path onto the repo through its symlinks; the writer renders both
into the ``protected`` table, which the runtime reads back.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.agents_md import AgentsMdAdapter
from coding_agent_playbook.adapters.claude_code.adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.continue_ import ContinueAdapter
from coding_agent_playbook.adapters.opencode import OpenCodeAdapter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
from coding_agent_playbook.generated_output.sentinel import SENTINEL
from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, parse_guard_config
from coding_agent_playbook.hooks.guard_config.compile import (
    GuardConfigRequest,
    compile_guard_config,
)
from coding_agent_playbook.hooks.guard_config.inputs import ProtectInputs
from coding_agent_playbook.lockfile.model import LockEntry, Provenance
from coding_agent_playbook.sync._dispatch import build_lockfile
from coding_agent_playbook.sync._protect import (
    COMPOSITE_SINGLETONS,
    adapter_output_dirs,
    protected_rows,
)

if TYPE_CHECKING:
    from pathlib import Path


def _written_tree(root: Path) -> tuple[dict[Path, Provenance], list[LockEntry]]:
    """A synced tree: two whole-file outputs, a composite and a co-owned settings file."""
    files = {
        ".claude/skills/demo/SKILL.md": Provenance("skill", "demo", "<repo-local>", "claude_code"),
        ".continue/rules/10-x.md": Provenance("rule", "x", "coding_agent_playbook", "continue"),
        "AGENTS.md": Provenance("composite", adapter="agents_md"),
        ".claude/settings.json": Provenance("composite", adapter="claude_code"),
    }
    provenance: dict[Path, Provenance] = {}
    for rel, origin in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{rel}\n", encoding="utf-8")
        provenance[path.resolve()] = origin
    managed = [
        LockEntry(
            path=".claude/settings.json",
            sha256="ab" * 32,
            bytes=40,
            kind="runtime",
            artifact_id="registration:pre_tool_use",
            adapter="claude_code",
            scope="json:/hooks/PreToolUse",
        )
    ]
    return provenance, managed


def test_protected_entries_mirror_lockfile_provenance(tmp_path: Path) -> None:
    provenance, managed = _written_tree(tmp_path)
    shared = (".claude/settings.json",)

    rows = protected_rows(provenance, managed, tmp_path, shared=shared)

    lock = build_lockfile(
        list(provenance), tmp_path, "0.2.0", provenance=provenance, managed=managed, shared=shared
    )
    columns = ("path", "kind", "artifact_id", "source", "scope")
    assert [{c: row.to_json()[c] for c in columns} for row in rows] == [
        {c: getattr(entry, c) for c in columns} for entry in lock.entries
    ]


def test_scoped_entries_carry_sha256(tmp_path: Path) -> None:
    provenance, managed = _written_tree(tmp_path)

    rows = [row.to_json() for row in protected_rows(provenance, managed, tmp_path)]

    scoped = [row for row in rows if row["scope"]]
    assert scoped == [
        {
            "path": ".claude/settings.json",
            "kind": "runtime",
            "artifact_id": "registration:pre_tool_use",
            "source": "",
            "scope": "json:/hooks/PreToolUse",
            "sha256": "ab" * 32,
        }
    ]
    assert all("sha256" not in row for row in rows if not row["scope"])


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_protected_rows_map_a_scratch_path_through_the_repos_symlinks(tmp_path: Path) -> None:
    """A ``--check`` scratch row names what write mode records: the resolved repo path."""
    repo, scratch = tmp_path / "repo", tmp_path / "scratch"
    (repo / ".agents" / "skills").mkdir(parents=True)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "skills").symlink_to("../.agents/skills", target_is_directory=True)
    written = scratch / ".claude" / "skills" / "demo" / "SKILL.md"
    provenance = {written.resolve(): Provenance(kind="skill", artifact_id="demo")}

    rows = protected_rows(provenance, [], scratch, repo_root=repo)

    assert [row.path for row in rows] == [".agents/skills/demo/SKILL.md"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_protected_rows_drop_a_path_the_repo_links_outside_itself(tmp_path: Path) -> None:
    repo, scratch, elsewhere = tmp_path / "repo", tmp_path / "scratch", tmp_path / "elsewhere"
    elsewhere.mkdir()
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "skills").symlink_to(elsewhere, target_is_directory=True)
    written = scratch / ".claude" / "skills" / "demo" / "SKILL.md"
    provenance = {written.resolve(): Provenance(kind="skill", artifact_id="demo")}

    assert protected_rows(provenance, [], scratch, repo_root=repo) == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_protected_output_dirs_list_a_linked_scan_dir_by_its_target(tmp_path: Path) -> None:
    repo, scratch = tmp_path / "repo", tmp_path / "scratch"
    (repo / "tools" / "claude-commands").mkdir(parents=True)
    (repo / ".claude" / "commands").parent.mkdir()
    (repo / ".claude" / "commands").symlink_to("../tools/claude-commands", target_is_directory=True)

    dirs = adapter_output_dirs({"claude_code": ClaudeCodeAdapter()}, scratch, repo_root=repo)

    assert "tools/claude-commands/" in dirs
    assert ".claude/commands/" not in dirs
    assert dirs == adapter_output_dirs({"claude_code": ClaudeCodeAdapter()}, repo)


def test_protected_output_dirs_match_adapter_stale_scan_dirs(tmp_path: Path) -> None:
    adapters = {
        "claude_code": ClaudeCodeAdapter(),
        "continue": ContinueAdapter(),
        "opencode": OpenCodeAdapter(),
        "agents_md": AgentsMdAdapter(),
    }

    dirs = adapter_output_dirs(adapters, tmp_path)

    scanned = {
        f"{path.relative_to(tmp_path).as_posix()}/"
        for adapter in adapters.values()
        for path in adapter._output_directories(tmp_path)
    }
    composites = {".claude/CLAUDE.md", ".claude/rules/coding-agent-playbook.md", "AGENTS.md"}
    assert set(dirs) == scanned | composites
    assert ".claude/skills/" not in dirs  # skill output is lockfile-only (main #25)
    assert ".claude/rules/" not in dirs  # every other rules file is the user's
    assert dirs == sorted(dirs)
    assert adapter_output_dirs({"continue": ContinueAdapter()}, tmp_path) == [
        ".continue/prompts/",
        ".continue/rules/",
    ]


@pytest.mark.parametrize("name", sorted(COMPOSITE_SINGLETONS))
def test_composite_singletons_are_exactly_what_finalize_writes(tmp_path: Path, name: str) -> None:
    """The guard, the drift scan and ``sync`` must agree on every multi-source file.

    Since the Claude Code rules moved to ``.claude/rules/coding-agent-playbook.md``
    (SPEC §10.3.1) ``claude_code`` composes two files; both are singletons.
    """
    adapter = {"claude_code": ClaudeCodeAdapter, "agents_md": AgentsMdAdapter}[name]()
    body = "Use type hints.\n"
    fm = RuleFrontmatter(id="typing", name="Typing", description="d", scope="always")
    adapter.write_rule(Rule(fm, body, body, False, None, "test"), tmp_path)

    written = adapter.finalize(tmp_path)

    relative = tuple(path.relative_to(tmp_path).as_posix() for path in written)
    assert relative == COMPOSITE_SINGLETONS[name]


def test_runtime_reads_the_protect_tables_back(tmp_path: Path) -> None:
    provenance, managed = _written_tree(tmp_path)
    request = GuardConfigRequest(
        repo_root=tmp_path,
        hooks=(),
        hooks_config=HooksConfig(enabled=True),
        guardrails=GuardrailsConfig(),
        engine_version="0.2.0",
        protected=ProtectInputs(entries=protected_rows(provenance, managed, tmp_path)),
    )

    parsed = parse_guard_config(compile_guard_config(request).data)

    assert isinstance(parsed, GuardConfig), parsed
    assert parsed.tables["sentinel"] == SENTINEL
    paths = [row["path"] for row in parsed.tables["protected"]["entries"]]
    assert paths == sorted(paths)
