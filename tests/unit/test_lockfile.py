"""Tests for the Lockfile / LockEntry dataclasses (SPEC §14.4)."""

from __future__ import annotations

from coding_agent_playbook.lockfile import LockEntry, Lockfile, compute_hash


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
