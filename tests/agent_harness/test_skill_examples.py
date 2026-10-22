"""A skill's ``examples/`` survives the harness round trip (prU D48).

``examples/`` is a synced skill directory like ``scripts/`` and ``references/``:
the ``agent_harness`` adapter byte-copies it into ``skills/<id>/examples/``, and
importing the harness back (with or without the sidecar manifest) writes it to
the canonical ``skills/<id>/examples/`` again, nested directories included.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter
from coding_agent_playbook.agent_harness.importer import import_harness, write_import
from coding_agent_playbook.artifacts.skill import Skill

if TYPE_CHECKING:
    from pathlib import Path

#: Example-relative path -> bytes of the sample example app.
_EXAMPLE_FILES: Final = {
    "pricing-app/pyproject.toml": b'[project]\nname = "pricing-app"\n',
    "pricing-app/app/main.py": b"def price() -> int:\n    return 1\n",
}


def _tree(root: Path) -> dict[str, bytes]:
    """Every file under ``root``, by root-relative POSIX path."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _emit(tmp_path: Path) -> Path:
    """Emit a harness holding one skill whose ``examples/`` holds the sample app."""
    examples = tmp_path / "src_examples"
    for relative, data in _EXAMPLE_FILES.items():
        (examples / relative).parent.mkdir(parents=True, exist_ok=True)
        (examples / relative).write_bytes(data)
    skill = Skill(
        frontmatter={"id": "pricing", "name": "pricing", "description": "Pricing conventions."},
        body="# Pricing\n",
        scripts_dir=None,
        references_dir=None,
        source_package="test",
        examples_dir=examples,
    )
    harness = tmp_path / "harness"
    harness.mkdir()
    adapter = AgentHarnessAdapter()
    adapter.write_skill(skill, harness)
    adapter.finalize(harness)
    return harness


def test_agent_harness_copies_a_skill_examples_dir(tmp_path: Path) -> None:
    harness = _emit(tmp_path)

    assert _tree(harness / "skills" / "pricing" / "examples") == _EXAMPLE_FILES


@pytest.mark.parametrize("sidecar", [True, False], ids=["lossless", "best-effort"])
def test_harness_import_writes_the_examples_dir_back(tmp_path: Path, sidecar: bool) -> None:
    harness = _emit(tmp_path)
    if not sidecar:
        shutil.rmtree(harness / ".playbook")

    write_import(import_harness(harness), tmp_path / "playbook")

    assert _tree(tmp_path / "playbook" / "skills" / "pricing" / "examples") == _EXAMPLE_FILES
