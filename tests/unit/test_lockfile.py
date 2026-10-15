"""Tests for the Lockfile / LockEntry dataclasses (SPEC §14.4)."""

from __future__ import annotations

import re
import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.claude_settings import scoped_lock_entry
from coding_agent_playbook.lockfile import (
    LockEntry,
    Lockfile,
    LockfileFormatError,
    Provenance,
    compute_hash,
)
from coding_agent_playbook.sources.filesystem import FileSystemStateSource

if TYPE_CHECKING:
    from pathlib import Path


def test_compute_hash_stable():
    # sha256("hello") is a known value — see test vectors.
    assert compute_hash(b"hello") == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_lockfile_roundtrip():
    lockfile = Lockfile(
        schema_version=1,
        engine_version="0.1.0a0",
        rendered_at="2026-05-28T12:00:00Z",
        entries=[
            LockEntry(path=".continue/rules/a.md", sha256="abc123", bytes=42),
            LockEntry(path=".claude/CLAUDE.md", sha256="def456", bytes=128),
        ],
    )
    data = lockfile.to_dict()
    restored = Lockfile.from_dict(data)
    assert restored == lockfile


def test_lockfile_roundtrip_empty_entries():
    lockfile = Lockfile(
        schema_version=1,
        engine_version="0.1.0a0",
        rendered_at="2026-05-28T12:00:00Z",
    )
    data = lockfile.to_dict()
    restored = Lockfile.from_dict(data)
    assert restored == lockfile
    assert restored.entries == []


def test_find_returns_entry():
    lockfile = Lockfile(
        schema_version=1,
        engine_version="0.1.0a0",
        rendered_at="2026-05-28T12:00:00Z",
        entries=[
            LockEntry(path="path/x.md", sha256="abc", bytes=1),
            LockEntry(path="path/y.md", sha256="def", bytes=2),
        ],
    )
    found = lockfile.find("path/x.md")
    assert found is not None
    assert found.sha256 == "abc"
    assert lockfile.find("missing") is None


# --- schema v2: provenance fields (specs/prK-lifecycle-hooks.md §P P4, §B.6) ---

_V1_LOCKFILE_TOML = """\
schema_version = 1
engine_version = "0.1.0a0"
rendered_at = "2026-05-28T12:00:00Z"

[[entries]]
path = ".continue/rules/50-a.md"
sha256 = "abc123"
bytes = 42
"""


def _all_fields_entry() -> LockEntry:
    return LockEntry(
        path=".claude/settings.json",
        sha256="41ab",
        bytes=212,
        kind="runtime",
        artifact_id="registration:pre_tool_use",
        source="coding_agent_playbook",
        adapter="claude_code",
        scope="json:/hooks/PreToolUse",
        executable=True,
    )


def test_v1_lockfile_loads_with_defaults() -> None:
    """A v1 lockfile (path/sha256/bytes only) loads; every v2 field defaults."""
    restored = Lockfile.from_dict(tomllib.loads(_V1_LOCKFILE_TOML))
    assert restored.schema_version == 1
    assert restored.entries == [
        LockEntry(path=".continue/rules/50-a.md", sha256="abc123", bytes=42)
    ]
    entry = restored.entries[0]
    assert (entry.kind, entry.artifact_id, entry.source, entry.adapter, entry.scope) == (
        "",
        "",
        "",
        "",
        "",
    )
    assert entry.executable is False


def test_v2_roundtrip_all_fields(tmp_path: Path) -> None:
    """Every v2 field survives to_dict -> TOML on disk -> tomllib -> from_dict."""
    original = Lockfile(
        schema_version=2,
        engine_version="0.2.0",
        rendered_at="2026-10-14T10:00:00Z",
        entries=[
            LockEntry(
                path=".continue/rules/50-python-typing.md",
                sha256="9c1e",
                bytes=1834,
                kind="rule",
                artifact_id="python-typing",
                source="coding_agent_playbook",
                adapter="continue",
            ),
            _all_fields_entry(),
        ],
    )
    state = FileSystemStateSource(repo_root=tmp_path)
    state.save_lockfile(original)
    assert state.load_lockfile() == original


def test_default_valued_fields_omitted_from_toml(tmp_path: Path) -> None:
    """New fields at their default are not serialized: v1-shaped entries stay
    compact, and a rule entry carries no ``scope``/``executable`` keys."""
    rule_entry = LockEntry(
        path=".continue/rules/50-x.md",
        sha256="aa",
        bytes=1,
        kind="rule",
        artifact_id="x",
        source="<repo-local>",
        adapter="continue",
    )
    bare_entry = LockEntry(path="AGENTS.md", sha256="bb", bytes=2)
    assert bare_entry.to_dict() == {"path": "AGENTS.md", "sha256": "bb", "bytes": 2}
    assert list(rule_entry.to_dict()) == [
        "path",
        "sha256",
        "bytes",
        "kind",
        "artifact_id",
        "source",
        "adapter",
    ]
    assert _all_fields_entry().to_dict()["executable"] is True

    lockfile = Lockfile(
        schema_version=2,
        engine_version="0.2.0",
        rendered_at="2026-10-14T10:00:00Z",
        entries=[rule_entry, bare_entry],
    )
    FileSystemStateSource(repo_root=tmp_path).save_lockfile(lockfile)
    text = (tmp_path / ".coding-agent-playbook.lock").read_text(encoding="utf-8")
    assert "scope" not in text
    assert "executable" not in text
    assert text.count("kind = ") == 1


def test_provenance_rejects_unknown_kind() -> None:
    """A typo'd provenance kind fails loudly, naming the value and the choices."""
    with pytest.raises(ValueError, match=r"'rules'.*composite"):
        Provenance(kind="rules")  # type: ignore[arg-type]


def test_lock_entry_from_provenance_copies_fields() -> None:
    """``LockEntry.from_provenance`` stamps the four provenance fields."""
    provenance = Provenance(
        kind="prompt", artifact_id="refactor", source="<repo-local>", adapter="opencode"
    )
    entry = LockEntry.from_provenance(".opencode/command/refactor.md", b"body", provenance)
    assert entry == LockEntry(
        path=".opencode/command/refactor.md",
        sha256=compute_hash(b"body"),
        bytes=4,
        kind="prompt",
        artifact_id="refactor",
        source="<repo-local>",
        adapter="opencode",
    )


_HEADER = {"schema_version": 2, "engine_version": "0.2.0", "rendered_at": "2026-10-14T10:00:00Z"}
_ENTRY = {"path": "AGENTS.md", "sha256": "ab", "bytes": 2}


@pytest.mark.parametrize(
    ("data", "message"),
    [
        pytest.param(
            {**_HEADER, "entries": "oops"}, "entries: expected list, got str", id="entries"
        ),
        pytest.param({**_HEADER, "entries": ["x"]}, "entries[0]: expected a table", id="entry"),
        pytest.param(
            {**_HEADER, "entries": [{**_ENTRY, "path": 3}]},
            "entries[0].path: expected str, got int 3",
            id="path",
        ),
        pytest.param(
            {**_HEADER, "entries": [{**_ENTRY, "bytes": True}]},
            "entries[0].bytes: expected int, got bool True",
            id="bytes-bool",
        ),
        pytest.param(
            {**_HEADER, "entries": [{"path": "a", "bytes": 1}]},
            "entries[0].sha256: missing",
            id="missing-sha256",
        ),
        pytest.param(
            {**_HEADER, "entries": [{**_ENTRY, "kind": 1}]},
            "entries[0].kind: expected str, got int 1",
            id="kind",
        ),
        pytest.param(
            {**_HEADER, "entries": [{**_ENTRY, "executable": "yes"}]},
            "entries[0].executable: expected bool",
            id="executable",
        ),
        pytest.param(
            {**_HEADER, "schema_version": "2"}, "schema_version: expected int", id="schema"
        ),
        pytest.param(
            {"engine_version": "x", "rendered_at": "t"}, "schema_version: missing", id="no-schema"
        ),
    ],
)
def test_from_dict_rejects_wrong_shape_naming_key_and_value(
    data: dict[str, object], message: str
) -> None:
    """A valid-TOML lockfile of the wrong shape raises ``LockfileFormatError`` (a
    ``ValueError``) naming the key and value — never a bare ``TypeError``."""
    with pytest.raises(LockfileFormatError, match=re.escape(message)):
        Lockfile.from_dict(data)
    assert issubclass(LockfileFormatError, ValueError)


def test_lock_entry_is_whole_file_unless_scoped() -> None:
    assert LockEntry(path="AGENTS.md", sha256="a", bytes=1).is_whole_file
    scoped = LockEntry(path=".claude/settings.json", sha256="a", bytes=1, scope="json:/hooks/X")
    assert not scoped.is_whole_file


def test_scoped_entry_roundtrips_with_scope_and_omits_defaults(tmp_path: Path) -> None:
    """A managed settings element (K3 §C.1.4) survives save/load, and its TOML
    carries ``scope`` but neither ``source`` nor ``executable`` (both default)."""
    entry = scoped_lock_entry(
        ".claude/settings.json",
        "/permissions/deny",
        "Read(./.env)",
        artifact_id="permission:deny:Read(./.env)",
    )
    assert list(entry.to_dict()) == [
        "path",
        "sha256",
        "bytes",
        "kind",
        "artifact_id",
        "adapter",
        "scope",
    ]
    lockfile = Lockfile(2, "0.2.0", "2026-10-14T10:00:00Z", entries=[entry])
    state = FileSystemStateSource(repo_root=tmp_path)
    state.save_lockfile(lockfile)

    assert state.load_lockfile() == lockfile
    text = (tmp_path / ".coding-agent-playbook.lock").read_text(encoding="utf-8")
    assert 'scope = "json:/permissions/deny"' in text
    assert "source" not in text
    assert "executable" not in text
