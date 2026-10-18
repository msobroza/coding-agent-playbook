"""A rule entry's ``skill`` in the harness manifest (specs/prS-skills-context.md 6.4.9, 6.8.7).

``skill`` is emitted only when set, like ``lint_codes``, so manifests of rules
without it stay byte-identical. Split from ``test_manifest_roundtrip.py``,
which is already over 500 lines.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from coding_agent_playbook.harness.manifest import ManifestEntry, read_manifest, write_manifest

if TYPE_CHECKING:
    from pathlib import Path

_SCOPED = ManifestEntry(
    kind="rule",
    path="references/python-typing.md",
    id="python-typing",
    name="Typing",
    body="# Typing\n",
    is_templated=False,
    scope="scoped",
    priority=50,
    globs=["**/*.py"],
    version=1,
)

_SCOPED_TOML = (
    "schema = 1\n"
    "\n"
    "[[artifact]]\n"
    'kind = "rule"\n'
    'path = "references/python-typing.md"\n'
    'id = "python-typing"\n'
    'name = "Typing"\n'
    'body = "# Typing\\n"\n'
    "is_templated = false\n"
    'scope = "scoped"\n'
    "priority = 50\n"
    'globs = ["**/*.py"]\n'
    "tags = []\n"
    "version = 1\n"
    "applies_if = {}\n"
)


def test_rule_entry_round_trips_skill(tmp_path: Path) -> None:
    entry = dataclasses.replace(_SCOPED, skill="python-coding")

    written = write_manifest(tmp_path, [entry])

    assert written.read_text(encoding="utf-8") == f'{_SCOPED_TOML}skill = "python-coding"\n'
    manifest = read_manifest(tmp_path)
    assert manifest is not None and manifest.entries == [entry]


def test_rule_entry_without_skill_is_byte_identical(tmp_path: Path) -> None:
    written = write_manifest(tmp_path, [_SCOPED])

    assert written.read_text(encoding="utf-8") == _SCOPED_TOML
    manifest = read_manifest(tmp_path)
    assert manifest is not None and manifest.entries[0].skill is None
