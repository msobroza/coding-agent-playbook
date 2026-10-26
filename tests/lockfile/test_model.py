"""Tests for the Lockfile / LockEntry dataclasses (SPEC §14.4)."""

from __future__ import annotations

import json
import os
import re
import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.claude_code.settings.managed_merge import scoped_lock_entry
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.lockfile.drift import (
    DriftItem,
    ScopedUnreadable,
    drift_entries,
    parse_json_document,
)
from coding_agent_playbook.lockfile.model import (
    ArtifactDigest,
    LockEntry,
    Lockfile,
    LockfileFormatError,
    Provenance,
    compute_hash,
    generated_paths,
)
from tests.engine_version import ENGINE_VERSION

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
        engine_version=ENGINE_VERSION,
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
        engine_version=ENGINE_VERSION,
        rendered_at="2026-05-28T12:00:00Z",
    )
    data = lockfile.to_dict()
    restored = Lockfile.from_dict(data)
    assert restored == lockfile
    assert restored.entries == []


def test_find_returns_entry():
    lockfile = Lockfile(
        schema_version=1,
        engine_version=ENGINE_VERSION,
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

_V1_LOCKFILE_TOML = f"""\
schema_version = 1
engine_version = "{ENGINE_VERSION}"
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
        engine_version="9.9.9",
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
        engine_version="9.9.9",
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


_HEADER = {"schema_version": 2, "engine_version": "9.9.9", "rendered_at": "2026-10-14T10:00:00Z"}
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
    lockfile = Lockfile(2, "9.9.9", "2026-10-14T10:00:00Z", entries=[entry])
    state = FileSystemStateSource(repo_root=tmp_path)
    state.save_lockfile(lockfile)

    assert state.load_lockfile() == lockfile
    text = (tmp_path / ".coding-agent-playbook.lock").read_text(encoding="utf-8")
    assert 'scope = "json:/permissions/deny"' in text
    assert "source" not in text
    assert "executable" not in text


# --- drift_entries: the jinja2-free drift definition (specs/prK-hook-pack.md §E.1) -----

_SETTINGS = ".claude/settings.json"
_GROUP = {"hooks": [{"type": "command", "command": "launch.sh dispatch stop"}]}


def _whole(root: Path, rel: str, content: bytes, *, executable: bool = False) -> LockEntry:
    """Write ``rel`` with ``content`` and return its pristine whole-file entry."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return LockEntry(rel, compute_hash(content), len(content), executable=executable)


def _lock(*entries: LockEntry) -> Lockfile:
    return Lockfile(2, "9.9.9", "2026-10-14T10:00:00Z", entries=list(entries))


def test_drift_entries_missing_and_hash_mismatch(tmp_path: Path) -> None:
    clean = _whole(tmp_path, "AGENTS.md", b"# agents\n")
    edited = _whole(tmp_path, ".continue/rules/10-x.md", b"rule\n")
    (tmp_path / edited.path).write_bytes(b"hand edit\n")
    gone = LockEntry(".claude/commands/triage.md", compute_hash(b"x"), 1)
    folder = LockEntry(".opencode/command/x.md", compute_hash(b"x"), 1)
    (tmp_path / folder.path).mkdir(parents=True)

    items = drift_entries(_lock(clean, edited, gone, folder), tmp_path)

    assert items == [
        DriftItem(".continue/rules/10-x.md", "hash_mismatch"),
        DriftItem(".claude/commands/triage.md", "missing"),
        DriftItem(".opencode/command/x.md", "missing"),
    ]
    assert [item.line() for item in items] == [
        "hash mismatch: .continue/rules/10-x.md",
        "missing: .claude/commands/triage.md",
        "missing: .opencode/command/x.md",
    ]


def test_drift_entries_scoped_entry_matched_by_canonical_hash(tmp_path: Path) -> None:
    entry = scoped_lock_entry(_SETTINGS, "/hooks/Stop", _GROUP, artifact_id="registration:stop")
    settings = tmp_path / _SETTINGS
    settings.parent.mkdir()
    reordered = {"command": "launch.sh dispatch stop", "type": "command"}
    settings.write_text(
        json.dumps({"model": "x", "hooks": {"Stop": [{"hooks": [reordered]}]}}, indent=4),
        encoding="utf-8",
    )
    present = drift_entries(_lock(entry), tmp_path)
    settings.write_text('{"hooks": {"Stop": []}}', encoding="utf-8")
    removed = drift_entries(_lock(entry), tmp_path)
    settings.write_text('{"hooks": ', encoding="utf-8")
    broken = drift_entries(_lock(entry), tmp_path)
    settings.unlink()
    absent = drift_entries(_lock(entry), tmp_path)

    assert present == []
    assert removed == absent == [DriftItem(_SETTINGS, "managed_missing", pointer="/hooks/Stop")]
    assert removed[0].line() == "managed entry missing: .claude/settings.json#/hooks/Stop"
    [unreadable] = broken
    assert unreadable.line().startswith("unreadable: .claude/settings.json (line 1, col ")


def test_drift_entries_scoped_edited_probe_names_an_edited_element(tmp_path: Path) -> None:
    entry = scoped_lock_entry(_SETTINGS, "/hooks/Stop", _GROUP, artifact_id="registration:stop")
    (tmp_path / ".claude").mkdir()
    (tmp_path / _SETTINGS).write_text('{"hooks": {"Stop": [{"hooks": []}]}}', encoding="utf-8")
    calls: list[tuple[str, int, frozenset[str]]] = []

    def edited(pointer: str, items: object, hashes: object, recorded: frozenset[str]) -> bool:
        calls.append((pointer, len(hashes), recorded))  # type: ignore[arg-type]
        return True

    items = drift_entries(_lock(entry), tmp_path, edited=edited)

    assert items == [DriftItem(_SETTINGS, "managed_edited", pointer="/hooks/Stop")]
    assert calls == [("/hooks/Stop", 1, frozenset({entry.sha256}))]


@pytest.mark.skipif(os.name != "posix", reason="exec bits are POSIX-only")
def test_drift_entries_exec_bit_mode_drift(tmp_path: Path) -> None:
    script = _whole(tmp_path, ".coding-agent-playbook/hooks/scripts/g/check.sh", b"#!/bin/sh\n")
    script.executable = True
    (tmp_path / script.path).chmod(0o644)

    drifted = drift_entries(_lock(script), tmp_path)
    (tmp_path / script.path).chmod(0o755)

    assert [item.line() for item in drifted] == [
        "mode mismatch: .coding-agent-playbook/hooks/scripts/g/check.sh (expected executable)"
    ]
    assert drift_entries(_lock(script), tmp_path) == []


@pytest.mark.skipif(os.name != "posix", reason="symlinks need POSIX permissions")
def test_drift_entries_never_follows_symlink_or_reads_secret_path(tmp_path: Path) -> None:
    target = _whole(tmp_path, "real.md", b"engine output\n")
    linked = LockEntry("AGENTS.md", target.sha256, target.bytes)  # same bytes, through a link
    (tmp_path / linked.path).symlink_to(tmp_path / target.path)
    secret = _whole(tmp_path, ".env", b"TOKEN=1\n")
    (tmp_path / secret.path).write_bytes(b"TOKEN=2\n")  # would be a hash mismatch if read
    outside = LockEntry("../outside.md", compute_hash(b"x"), 1)
    absolute = LockEntry(str(tmp_path / "real.md"), compute_hash(b"x"), 1)

    items = drift_entries(
        _lock(linked, secret, outside, absolute), tmp_path, skip=lambda rel: rel == ".env"
    )

    assert items == [DriftItem("AGENTS.md", "hash_mismatch")]


def test_parse_json_document_reads_blank_as_empty_and_names_what_it_cannot_read() -> None:
    assert parse_json_document(b"\xef\xbb\xbf  \n", "s.json") == {}
    assert parse_json_document(b'\xef\xbb\xbf{"a": [1]}', "s.json") == {"a": [1]}
    with pytest.raises(ScopedUnreadable, match="not valid UTF-8 at byte 2"):
        parse_json_document(b'{"\xff": 1}', "s.json")
    with pytest.raises(ScopedUnreadable, match=r"^line 2, col 2: Extra data"):
        parse_json_document(b"{\n}x", "s.json")


def test_drift_entries_shared_file_that_is_not_a_regular_file_is_one_unreadable_line(
    tmp_path: Path,
) -> None:
    entry = scoped_lock_entry(_SETTINGS, "/hooks/Stop", _GROUP, artifact_id="registration:stop")
    other = scoped_lock_entry(_SETTINGS, "/permissions/allow", "Bash(ls)", artifact_id="allow")
    (tmp_path / _SETTINGS).mkdir(parents=True)

    items = drift_entries(_lock(entry, other), tmp_path)

    assert [item.line() for item in items] == [
        "unreadable: .claude/settings.json (not a regular file)"
    ]


def test_recorded_paths_lists_each_path_once_scoped_entries_included() -> None:
    whole = LockEntry(path="AGENTS.md", sha256="0" * 64, bytes=1)
    scoped = [
        LockEntry(path=".claude/settings.json", sha256="1" * 64, bytes=1, scope=f"json:/{i}")
        for i in range(2)
    ]
    lock = Lockfile(schema_version=2, engine_version="0", rendered_at="", entries=[whole, *scoped])

    assert lock.recorded_paths() == frozenset({"AGENTS.md", ".claude/settings.json"})
    assert generated_paths(lock) == lock.recorded_paths()


def test_generated_paths_is_empty_before_the_first_sync() -> None:
    assert generated_paths(None) == frozenset()


# --- artifact digests (#281 ticket 03) -----------------------------------------


def test_artifact_digests_and_entry_digest_roundtrip_through_toml(tmp_path: Path) -> None:
    entry = LockEntry("a.md", "0" * 64, 1, kind="rule", artifact_id="x", digest="d" * 64)
    record = ArtifactDigest(kind="rule", artifact_id="x", digest="d" * 64)
    lockfile = Lockfile(2, "9.9.9", "t", entries=[entry], artifacts=[record])
    state = FileSystemStateSource(repo_root=tmp_path)

    state.save_lockfile(lockfile)

    assert state.load_lockfile() == lockfile
    assert record.key == "rule:x"


def test_a_lockfile_without_digests_writes_neither_key(tmp_path: Path) -> None:
    state = FileSystemStateSource(repo_root=tmp_path)
    state.save_lockfile(Lockfile(2, "9.9.9", "t", entries=[LockEntry("a.md", "0" * 64, 1)]))

    text = (tmp_path / ".coding-agent-playbook.lock").read_text(encoding="utf-8")

    assert "digest" not in text
    assert "artifacts" not in text


@pytest.mark.parametrize(
    ("artifacts", "message"),
    [
        ("oops", r"artifacts: expected list, got str 'oops'"),
        (["oops"], r"artifacts\[0\]: expected a table, got str 'oops'"),
        ([{"kind": "rule", "artifact_id": "x"}], r"artifacts\[0\]\.digest: missing"),
    ],
)
def test_bad_artifacts_tables_name_the_key_and_value(artifacts: object, message: str) -> None:
    data = {"schema_version": 2, "engine_version": "0", "rendered_at": "", "artifacts": artifacts}

    with pytest.raises(LockfileFormatError, match=message):
        Lockfile.from_dict(data)
