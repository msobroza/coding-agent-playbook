"""The import-light protected-set classifier (specs/prK-hook-pack.md §E.1, guard-generated-outputs).

``protected_paths`` reads only the rendered ``guard_config.json`` tables (and,
for installed resources, ``machine.json``); ``classify`` decides one
normalized path. The lockfile rows are authoritative and need no read; the
sentinel counts only at its anchored position, only inside an adapter output
dir, and never through a symlink or on a secret path. The head reader and the
platform are injected, so darwin folding is testable on any host.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook._sentinel import SENTINEL, file_has_sentinel, sentinel_line
from coding_agent_playbook.hook_runtime._config_reader import Malformed
from coding_agent_playbook.hook_runtime.config import GuardConfig, parse_guard_config
from coding_agent_playbook.hook_runtime.event import RepoInfo
from coding_agent_playbook.hook_runtime.paths import normalize_path
from coding_agent_playbook.hook_runtime.pin import MachinePins
from coding_agent_playbook.hook_runtime.protected import (
    ENGINE_RESOURCES_ID,
    ProtectedHit,
    classify,
    protected_paths,
)
from tests.hook_runtime.guard_repo import canonical

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.protected import ProtectedSet

_HTML = sentinel_line("html")
_ENTRIES: list[dict[str, str]] = [
    {
        "path": ".claude/CLAUDE.md",
        "kind": "composite",
        "artifact_id": "",
        "source": "",
        "scope": "",
    },
    {
        "path": ".claude/skills/demo/SKILL.md",
        "kind": "skill",
        "artifact_id": "demo",
        "source": "<repo-local>",
        "scope": "",
    },
    {
        "path": ".claude/hooks/playbook/launch.sh",
        "kind": "runtime",
        "artifact_id": "",
        "source": "",
        "scope": "",
    },
    {
        "path": ".claude/settings.json",
        "kind": "runtime",
        "artifact_id": "registration:pre_tool_use",
        "source": "",
        "scope": "json:/hooks/PreToolUse",
        "sha256": "ab" * 32,
    },
]
_HOOK_ARTIFACTS = [
    ".coding-agent-playbook/hooks/",
    ".claude/hooks/playbook/",
    ".opencode/plugins/playbook-hooks.js",
]


def _cfg(*, platform: str = "linux", **protected: Any) -> GuardConfig:
    table = {
        "entries": _ENTRIES,
        "output_dirs": [".claude/CLAUDE.md", ".claude/commands/", "AGENTS.md"],
        "hook_artifacts": _HOOK_ARTIFACTS,
        "resource_roots": [ENGINE_RESOURCES_ID],
        **protected,
    }
    document = {"schema_version": 1, "hooks": {}, "sentinel": SENTINEL, "protected": table}
    parsed = parse_guard_config(canonical(document), platform=platform, home="/home/dev")
    assert isinstance(parsed, GuardConfig), parsed
    return parsed


def _pset(cfg: GuardConfig, machine: MachinePins | None = None, **kw: Any) -> ProtectedSet:
    """``protected_paths`` for the linux folding the paths below are normalized with."""
    return protected_paths(cfg, machine, platform="linux", **kw)


class SpyReader:
    """The injected head reader: records every path it is asked to open."""

    def __init__(self) -> None:
        self.opened: list[str] = []

    def __call__(self, path: str, sentinel: str) -> bool:
        self.opened.append(path)
        return file_has_sentinel(path, sentinel=sentinel)


def _repo(root: Path) -> RepoInfo:
    git = str(root / ".git")
    return RepoInfo(worktree_root=str(root), git_dir=git, common_dir=git, is_linked_worktree=False)


def _write(root: Path, rel: str, text: str = "x\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _hit(
    pset: ProtectedSet, root: Path, raw: str, *, platform: str = "linux", reader: Any = None
) -> ProtectedHit | None:
    npath = normalize_path(raw, base=str(root), repo=_repo(root), home=None, platform=platform)
    if reader is None:
        return classify(pset, npath)
    return classify(pset, npath, read_sentinel=reader)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    return repo.resolve()


def test_lock_entry_hit_is_authoritative_without_sentinel(root: Path) -> None:
    _write(root, ".claude/skills/demo/SKILL.md", "---\nname: demo\n---\nNo sentinel.\n")
    _write(root, ".coding-agent-playbook.lock", "schema_version = 2\n")
    reader = SpyReader()
    pset = _pset(_cfg())

    hit = _hit(pset, root, ".claude/skills/demo/SKILL.md", reader=reader)
    lock = _hit(pset, root, ".coding-agent-playbook.lock", reader=reader)

    assert hit is not None and hit.kind == "entry"
    assert hit.entry is not None and (hit.entry.artifact_id, hit.entry.source) == (
        "demo",
        "<repo-local>",
    )
    assert lock == ProtectedHit(path=".coding-agent-playbook.lock", kind="lockfile")
    assert reader.opened == []


def test_sentinel_counts_only_at_anchored_positions(root: Path) -> None:
    _write(root, ".claude/commands/new.md", f"{_HTML}\n# New\n")
    _write(root, ".claude/commands/review.md", f"---\ndescription: r\n---\n{_HTML}\nbody\n")
    _write(root, ".claude/commands/notes.md", f"# Notes\nLines like `{_HTML}` are generated.\n")
    _write(root, "renderer.py", f'SENTINEL = "{SENTINEL}"\n')
    _write(root, "tests/harness/fixtures/out.md", f"{_HTML}\nfixture\n")
    pset = _pset(_cfg())

    assert _hit(pset, root, ".claude/commands/new.md") == ProtectedHit(
        path=".claude/commands/new.md", kind="sentinel"
    )
    hit = _hit(pset, root, ".claude/commands/review.md")
    assert hit is not None and hit.kind == "sentinel"
    assert _hit(pset, root, ".claude/commands/notes.md") is None
    assert _hit(pset, root, "renderer.py") is None
    assert _hit(pset, root, "tests/harness/fixtures/out.md") is None  # not an output dir


def test_all_scoped_entries_are_skipped(root: Path) -> None:
    _write(root, ".claude/settings.json", '{"hooks": {}}\n')
    reader = SpyReader()
    pset = _pset(_cfg())

    assert _hit(pset, root, ".claude/settings.json", reader=reader) is None
    assert pset.scoped(".claude/settings.json")[0].sha256 == "ab" * 32
    assert reader.opened == []


def test_hook_artifacts_classified_ask_the_user(root: Path) -> None:
    for rel in (
        ".coding-agent-playbook/hooks/guard_config.json",
        ".coding-agent-playbook/hooks/scripts/guard-ext/check.sh",
        ".claude/hooks/playbook/launch.sh",
        ".opencode/plugins/playbook-hooks.js",
    ):
        _write(root, rel)
    pset = _pset(_cfg())

    kinds = {
        rel: (hit.kind if (hit := _hit(pset, root, rel)) else None)
        for rel in (
            ".coding-agent-playbook/hooks/guard_config.json",
            ".coding-agent-playbook/hooks/scripts/guard-ext/check.sh",
            ".claude/hooks/playbook/launch.sh",
            ".opencode/plugins/playbook-hooks.js",
        )
    }

    assert set(kinds.values()) == {"hook_artifact"}


def test_resource_root_inside_worktree_not_protected(root: Path, tmp_path: Path) -> None:
    inside = root / "src" / "pkg" / "resources"
    _write(inside, "rules/x.md", f"{_HTML}\n")
    outside = (tmp_path / "site-packages" / "overlay" / "resources").resolve()
    _write(outside, "rules/y.md")
    machine = MachinePins(
        engine_version="0",
        tools={},
        resource_roots={ENGINE_RESOURCES_ID: str(inside), "pkg:overlay/resources": str(outside)},
    )
    cfg = _cfg(resource_roots=[ENGINE_RESOURCES_ID, "pkg:overlay/resources"])
    pset = _pset(cfg, machine)

    assert _hit(pset, root, str(inside / "rules" / "x.md")) is None
    hit = _hit(pset, root, str(outside / "rules" / "y.md"))
    assert hit == ProtectedHit(path=str(outside / "rules" / "y.md"), kind="resource")
    new = _hit(pset, root, str(outside / "rules" / "new.md"))
    assert new is not None and new.kind == "resource"  # installed resources: always denied
    assert _hit(pset, root, str(tmp_path / "elsewhere.md")) is None


def test_engine_resources_fall_back_to_the_runtime_package_without_machine_json() -> None:
    """Without ``machine.json`` the engine id resolves to this package's bundled ``catalog/core``."""
    pset = _pset(_cfg())

    from coding_agent_playbook.catalog import engine_layer_root

    assert pset.resource_roots == (os.path.realpath(engine_layer_root()),)


def test_engine_resources_protect_nothing_when_the_catalog_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A broken install leaves the engine id unresolved: it protects nothing, never raises."""
    from coding_agent_playbook import catalog

    monkeypatch.setattr(catalog, "_PACKAGE_DIR", tmp_path / "pkg")

    assert _pset(_cfg()).resource_roots == ()


def test_missing_path_is_creation_not_protected(root: Path) -> None:
    pset = _pset(_cfg())

    assert _hit(pset, root, ".claude/CLAUDE.md") is None
    assert _hit(pset, root, ".claude/commands/new.md") is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_symlink_and_secret_paths_never_opened(root: Path) -> None:
    target = _write(root, ".claude/commands/real.md", f"{_HTML}\n")
    (root / ".claude" / "commands" / "link.md").symlink_to(target)
    _write(root, ".claude/commands/.env.local", f"{_HTML}\n")
    _write(root, ".claude/commands/id_rsa", f"{_HTML}\n")
    reader = SpyReader()
    pset = _pset(_cfg())

    via_link = normalize_path(
        ".claude/commands/link.md", base=str(root), repo=_repo(root), home=None, platform="linux"
    )

    assert via_link.is_symlink
    assert classify(pset, via_link, read_sentinel=reader) is None
    assert _hit(pset, root, ".claude/commands/.env.local", reader=reader) is None
    assert _hit(pset, root, ".claude/commands/id_rsa", reader=reader) is None
    assert reader.opened == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_repo_reached_through_a_symlinked_dir_still_reads_the_sentinel(
    root: Path, tmp_path: Path
) -> None:
    """Only a linked *file* is skipped: a project under ``/tmp`` (darwin) or a linked checkout."""
    _write(root, ".claude/commands/new.md", f"{_HTML}\n")
    alias = tmp_path / "alias"
    alias.symlink_to(root)
    pset = _pset(_cfg())

    hit = _hit(pset, root, str(alias / ".claude" / "commands" / "new.md"))

    assert hit == ProtectedHit(path=".claude/commands/new.md", kind="sentinel")


def test_case_folded_lookup_on_darwin(root: Path) -> None:
    _write(root, ".Claude/CLAUDE.md", f"{_HTML}\n")

    folded = protected_paths(_cfg(platform="darwin"), platform="darwin")
    exact = protected_paths(_cfg(platform="linux"), platform="linux")

    hit = _hit(folded, root, ".Claude/CLAUDE.md", platform="darwin")
    assert hit is not None and hit.kind == "entry"
    assert hit.entry is not None and hit.entry.kind == "composite"
    assert _hit(exact, root, ".Claude/CLAUDE.md", platform="linux") is None


def test_extra_protected_globs_extend_the_set(root: Path) -> None:
    _write(root, "docs/generated/api.md")
    pset = _pset(_cfg(), extra=("docs/generated/",))

    assert _hit(pset, root, "docs/generated/api.md") == ProtectedHit(
        path="docs/generated/api.md", kind="extra"
    )


def test_missing_tables_protect_the_lockfile_and_hook_artifacts(root: Path) -> None:
    _write(root, ".coding-agent-playbook.lock")
    _write(root, ".claude/hooks/playbook/launch.sh")
    document = {"schema_version": 1, "hooks": {}}
    cfg = parse_guard_config(canonical(document))
    assert isinstance(cfg, GuardConfig)

    pset = _pset(cfg)

    lock = _hit(pset, root, ".coding-agent-playbook.lock")
    launcher = _hit(pset, root, ".claude/hooks/playbook/launch.sh")
    assert lock is not None and lock.kind == "lockfile"
    assert launcher is not None and launcher.kind == "hook_artifact"
    assert pset.sentinel == SENTINEL


def test_malformed_protected_table_raises_naming_the_key() -> None:
    with pytest.raises(Malformed, match=r"protected\.entries\[0\]\.path"):
        _pset(_cfg(entries=[{"path": 3, "kind": "rule"}]))
