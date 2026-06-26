"""Tests for harness.manifest — .playbook/manifest.toml sidecar (Track H1)."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.harness.manifest import (
    ManifestEntry,
    ScriptEntry,
    _format_scalar,
    read_manifest,
    write_manifest,
)

if TYPE_CHECKING:
    from pathlib import Path


def _rule_entry() -> ManifestEntry:
    return ManifestEntry(
        kind="rule",
        path="rules/10-python-house-style.md",
        id="python-house-style",
        # ``name`` and the un-rendered source ``body`` are part of the canonical
        # reconstruction payload the sidecar records for every kind.
        name="Python House Style (Human)",
        body="# House style\n\nUse type hints.\n",
        is_templated=False,
        scope="always",
        priority=10,
        globs=[],
        applies_if={},
        tags=["python"],
        version=1,
    )


def _scoped_rule_entry() -> ManifestEntry:
    return ManifestEntry(
        kind="rule",
        path="references/db-conventions.md",
        id="db-conventions",
        name="DB Conventions",
        body="# DB\n\nUse snake_case.\n",
        is_templated=True,
        scope="scoped",
        priority=50,
        globs=["**/*.sql"],
        applies_if={"language": "sql"},
        tags=[],
        version=2,
    )


def _prompt_entry() -> ManifestEntry:
    return ManifestEntry(
        kind="prompt",
        path="prompts/refactor/SKILL.md",
        id="refactor",
        name="Refactor",
        body="# Refactor\n\nRefactor the code.\n",
        is_templated=True,
        slash="refactor",
        input_variables=[{"name": "target", "required": True}],
        includes_rules=["python-house-style"],
        eval_tasks=["refactor-001"],
        applies_if={},
        version=3,
    )


def _skill_entry() -> ManifestEntry:
    return ManifestEntry(
        kind="skill",
        path="skills/query-database/SKILL.md",
        id="query-database",
        name="Query database",
        body="# Query database\n\nUse the run_query script.\n",
        extra_frontmatter={"license": "MIT"},
        scripts=[
            ScriptEntry(path="skills/query-database/scripts/run_query.py", executable=True),
            ScriptEntry(path="skills/query-database/scripts/_db.py", executable=False),
        ],
    )


def _eval_entry() -> ManifestEntry:
    return ManifestEntry(
        kind="eval_task",
        path="evals/refactor-001.toml",
        id="refactor-001",
    )


def test_read_manifest_absent_returns_none(tmp_path: Path) -> None:
    assert read_manifest(tmp_path) is None


def test_write_manifest_creates_file_with_schema(tmp_path: Path) -> None:
    out = write_manifest(tmp_path, [_rule_entry()])
    assert out == tmp_path / ".playbook" / "manifest.toml"
    assert out.is_file()
    parsed = tomllib.loads(out.read_text(encoding="utf-8"))
    assert parsed["schema"] == 1


def test_roundtrip_rule(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_rule_entry(), _scoped_rule_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [_rule_entry(), _scoped_rule_entry()]


def test_roundtrip_prompt(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_prompt_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [_prompt_entry()]


def test_roundtrip_records_name_body_and_is_templated(tmp_path: Path) -> None:
    """The canonical reconstruction payload (``name`` + un-rendered source
    ``body`` + ``is_templated``) round-trips for rules, prompts and skills —
    these are what let the importer rebuild losslessly without the rendered leaf.
    """
    write_manifest(tmp_path, [_rule_entry(), _prompt_entry(), _skill_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    index = manifest.index_by_path()

    rule = index["rules/10-python-house-style.md"]
    assert rule.name == "Python House Style (Human)"
    assert rule.body == "# House style\n\nUse type hints.\n"
    assert rule.is_templated is False

    prompt = index["prompts/refactor/SKILL.md"]
    assert prompt.name == "Refactor"
    assert prompt.body == "# Refactor\n\nRefactor the code.\n"
    # is_templated is now recorded for prompts too (defect #3).
    assert prompt.is_templated is True

    skill = index["skills/query-database/SKILL.md"]
    assert skill.name == "Query database"
    assert skill.body == "# Query database\n\nUse the run_query script.\n"


def test_roundtrip_skill_with_scripts(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_skill_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    [entry] = manifest.entries
    assert entry == _skill_entry()
    assert entry.scripts[0].executable is True
    assert entry.scripts[1].executable is False


def test_roundtrip_eval_task(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_eval_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [_eval_entry()]


def test_roundtrip_full_manifest(tmp_path: Path) -> None:
    entries = [
        _rule_entry(),
        _scoped_rule_entry(),
        _prompt_entry(),
        _skill_entry(),
        _eval_entry(),
    ]
    write_manifest(tmp_path, entries)
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == entries


def test_index_by_path_lookup(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_rule_entry(), _skill_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    index = manifest.index_by_path()
    assert index["rules/10-python-house-style.md"].id == "python-house-style"
    assert index["skills/query-database/SKILL.md"].kind == "skill"
    assert "missing.md" not in index


def test_written_toml_is_parseable_and_has_array_of_tables(tmp_path: Path) -> None:
    out = write_manifest(tmp_path, [_rule_entry(), _skill_entry()])
    text = out.read_text(encoding="utf-8")
    assert "[[artifact]]" in text
    assert "[[artifact.script]]" in text
    # Must be valid TOML.
    tomllib.loads(text)


def test_write_manifest_overwrites_existing(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_rule_entry()])
    write_manifest(tmp_path, [_eval_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [_eval_entry()]


def test_roundtrip_special_chars_in_strings(tmp_path: Path) -> None:
    entry = ManifestEntry(
        kind="rule",
        path="rules/weird.md",
        id="weird",
        name='weird "name" with\ttabs',
        body="line1\nline2\twith tab\n",
        is_templated=False,
        scope="always",
        priority=1,
        globs=['has"quote', "back\\slash", "tab\tchar", "line\nbreak", "ret\rurn", "ctrl\x01x"],
        applies_if={"note": 'a "quoted" value'},
        tags=[],
        version=1,
    )
    write_manifest(tmp_path, [entry])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [entry]


def test_roundtrip_non_identifier_key_in_inline_table(tmp_path: Path) -> None:
    # A frontmatter key with a dot/space must be emitted as a quoted TOML key.
    entry = ManifestEntry(
        kind="skill",
        path="skills/x/SKILL.md",
        id="x",
        name="X",
        body="# X\n",
        extra_frontmatter={"weird key.dotted": "v"},
    )
    write_manifest(tmp_path, [entry])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [entry]


def test_format_scalar_rejects_unsupported_type() -> None:
    with pytest.raises(TypeError):
        _format_scalar(object())
