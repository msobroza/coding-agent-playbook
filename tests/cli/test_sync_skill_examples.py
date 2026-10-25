"""End-to-end ``playbook sync`` of a skill's ``references/`` and ``examples/`` (prU D48, D58).

``examples/`` is a synced skill directory like ``scripts/`` and ``references/``:
sync byte-copies it into every native skills root and the ``agent_harness``
tree. A ``playbook.references`` entry whose ``applies_if`` fails is neither
listed in the skill's "References and examples" section nor written, whether
it names a reference file or an example directory. Each test syncs a synthetic
repo whose own skill holds both kinds; ``click`` is absent, so the click-gated
entries fail.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.commands import sync as _sync
from tests.engine_version import ENGINE_VERSION
from tests.member_skill_samples import write_repo_member_rule, write_repo_member_skill

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_CONFIG: Final = f"""\
schema_version = 1
adapters_enabled = {{adapters}}
overlays_enabled = []

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "{ENGINE_VERSION}"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"
"""
_SKILL_MD: Final = """\
---
id: risk-models
name: risk-models
description: Conventions for the risk models.
playbook:
  use_when: changing a risk model
  files: Risk model modules
  references:
    - path: references/glossary.md
      open_when: Naming a new model.
    - path: references/click-cli.md
      open_when: Adding a command.
      applies_if:
        has_framework: [click]
    - path: examples/pricing-app
      open_when: Wiring a new pricer.
    - path: examples/click-app
      open_when: Building a command-line pricer.
      applies_if:
        has_framework: [click]
---
# Risk models
"""
#: Skill-relative path -> bytes of every file the sample skill ships beside SKILL.md.
_SIDE_FILES: Final = {
    "references/glossary.md": b"# Glossary\n",
    "references/click-cli.md": b"# Click CLI\n",
    "examples/pricing-app/pyproject.toml": b'[project]\nname = "pricing-app"\n',
    "examples/pricing-app/app/main.py": b"def price() -> int:\n    return 1\n",
    "examples/click-app/main.py": b"import click\n",
}
#: The files whose entry passes its gate: the ungated ones.
_WRITTEN: Final = (
    "examples/pricing-app/app/main.py",
    "examples/pricing-app/pyproject.toml",
    "references/glossary.md",
)


def _synced_repo(tmp_path: Path, make_synthetic_repo: Callable[..., Path], adapters: str) -> Path:
    """A synthetic repo whose ``risk-models`` skill ships references and examples, synced."""
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG.format(adapters=adapters))
    skill_dir = write_repo_member_skill(repo)
    (skill_dir / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    for relative, data in _SIDE_FILES.items():
        target = skill_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_repo_member_rule(repo, "risk-naming")
    assert _sync.run(argparse.Namespace(repo_root=str(repo), check=False)) == 0
    return repo


def _side_files(skill_dir: Path) -> list[str]:
    """Every file under ``skill_dir``'s references/ and examples/, skill-relative, sorted."""
    return sorted(
        path.relative_to(skill_dir).as_posix()
        for name in ("references", "examples")
        for path in (skill_dir / name).rglob("*")
        if path.is_file()
    )


@pytest.mark.parametrize(
    "root", [".claude/skills", ".opencode/skills", ".agents/skills"], ids=lambda r: r.split("/")[0]
)
def test_native_roots_write_only_the_references_and_examples_whose_gate_passes(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], root: str
) -> None:
    repo = _synced_repo(
        tmp_path, make_synthetic_repo, '["claude_code", "opencode", "shared_skills"]'
    )
    skill_dir = repo / root / "risk-models"

    assert _side_files(skill_dir) == list(_WRITTEN)
    for relative in _WRITTEN:
        assert (skill_dir / relative).read_bytes() == _SIDE_FILES[relative], relative


def test_skill_md_lists_only_the_entries_whose_gate_passes(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _synced_repo(tmp_path, make_synthetic_repo, '["claude_code"]')
    text = (repo / ".claude/skills/risk-models/SKILL.md").read_text(encoding="utf-8")

    assert "references/glossary.md" in text and "examples/pricing-app" in text
    assert "click-cli" not in text and "click-app" not in text


def test_agent_harness_writes_only_the_references_and_examples_whose_gate_passes(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _synced_repo(tmp_path, make_synthetic_repo, '["agent_harness"]')
    skill_dir = repo / "skills" / "risk-models"

    assert _side_files(skill_dir) == list(_WRITTEN)
