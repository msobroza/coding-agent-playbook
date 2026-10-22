"""The core-skill directory gates, proved on scratch skills (prU L0-13; D2, D19, D25, D48, D78).

A core skill may ship ``rules/``, ``references/``, ``scripts/`` and
``examples/`` beside its ``SKILL.md``. ``tests/_core_skill_layout.py`` holds the
gates ``test_core_skills.py`` runs over the real catalog; this module builds
scratch skills under ``tmp_path`` to show what each gate accepts and what it
names when it fails, so the gates are pinned before any core skill ships these
directories.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.adapters.claude_code.adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.opencode import OpenCodeAdapter
from coding_agent_playbook.adapters.shared_skills import SharedSkillsAdapter
from tests._catalog import REPO_ROOT
from tests._core_skill_layout import (
    every_gate_problems,
    inventory_problems,
    link_problems,
    nesting_problems,
)

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.adapters.base import Adapter

pytestmark = pytest.mark.catalog

_SKILL_MD: Final = "---\nid: demo\nname: demo\ndescription: Demo.\n---\n# Demo\n"
_RULE: Final = "---\nid: demo-rule\nscope: scoped\n---\n# Demo rule\n"
#: A member skill's SKILL.md whose playbook block lists its reference and its example.
_MEMBER_SKILL_MD: Final = """\
---
id: demo
name: demo
description: Conventions for the demo models.
playbook:
  use_when: changing a demo model
  files: Demo modules
  references:
    - path: references/x.md
      open_when: Naming a demo model.
    - path: examples/app
      open_when: Wiring a demo app.
      applies_if:
        has_framework: [fastapi]
---
# Demo

Open the reference the change needs.
"""
#: A complete member rule of the scratch skill, delivered from its rules/.
_MEMBER_RULE: Final = """\
---
id: demo-rule
name: Demo rule
description: Follow the demo conventions.
scope: scoped
globs: ["src/demo/**/*.py"]
priority: 50
---
# Demo rule

"""


def _scratch_skill(root: Path, files: dict[str, str], skill_id: str = "demo") -> Path:
    """Write ``root/<skill_id>/`` holding ``SKILL.md`` plus ``files`` (skill-relative path -> text)."""
    skill_dir = root / skill_id
    for relative, text in {"SKILL.md": _SKILL_MD, **files}.items():
        (skill_dir / relative).parent.mkdir(parents=True, exist_ok=True)
        (skill_dir / relative).write_text(text, encoding="utf-8")
    return skill_dir


def test_a_skill_with_references_scripts_examples_and_a_linking_rule_passes_every_gate(
    tmp_path: Path,
) -> None:
    """The directory, SKILL.md and ``playbook validate`` gates all accept it (D47 listing too)."""
    skill_dir = _scratch_skill(
        tmp_path / "playbook" / "skills",
        {
            "references/x.md": "# X\n",
            "references/LICENSE.python-best-practices": "MIT\n",
            "scripts/y.py": "print('y')\n",
            "examples/app/pyproject.toml": "[project]\nname = 'app'\n",
            "examples/app/src/app/main.py": "x = 1\n",
            "rules/demo-rule.md": _MEMBER_RULE + "See [x](../references/x.md).\n",
        },
    )
    (skill_dir / "SKILL.md").write_text(_MEMBER_SKILL_MD + "Read [x](references/x.md).\n", "utf-8")

    assert every_gate_problems(skill_dir) == []


def test_every_gate_names_a_references_file_no_entry_lists(tmp_path: Path) -> None:
    """D47 through ``playbook validate``: an unlisted references/ file fails the scratch skill."""
    skill_dir = _scratch_skill(
        tmp_path / "playbook" / "skills",
        {
            "references/x.md": "# X\n",
            "references/unlisted.md": "# U\n",
            "examples/app/main.py": "x = 1\n",
            "rules/demo-rule.md": _MEMBER_RULE,
        },
    )
    (skill_dir / "SKILL.md").write_text(_MEMBER_SKILL_MD, "utf-8")

    [problem] = every_gate_problems(skill_dir)

    assert problem.startswith("validate: ") and "references/unlisted.md" in problem


def test_a_rule_linking_into_another_skill_fails_naming_the_path(tmp_path: Path) -> None:
    _scratch_skill(tmp_path, {"references/z.md": "# Z\n"}, skill_id="other")
    skill_dir = _scratch_skill(
        tmp_path, {"rules/demo-rule.md": _RULE + "See [z](../../other/references/z.md).\n"}
    )

    [problem] = link_problems(skill_dir)

    assert "rules/demo-rule.md" in problem and "../../other/references/z.md" in problem


def test_skill_md_may_link_only_its_own_references(tmp_path: Path) -> None:
    skill_dir = _scratch_skill(
        tmp_path, {"scripts/y.py": "", "references/x.md": "# X\n", "rules/demo-rule.md": _RULE}
    )
    (skill_dir / "SKILL.md").write_text(
        _SKILL_MD + "[x](references/x.md) [y](scripts/y.py) [r](rules/demo-rule.md)\n", "utf-8"
    )

    problems = link_problems(skill_dir)

    assert len(problems) == 2, problems
    assert "scripts/y.py" in problems[0] and "rules/demo-rule.md" in problems[1]


def test_a_dangling_link_fails(tmp_path: Path) -> None:
    skill_dir = _scratch_skill(
        tmp_path, {"rules/demo-rule.md": _RULE + "[g](../references/g.md)\n"}
    )

    assert "../references/g.md" in " ".join(link_problems(skill_dir))


@pytest.mark.parametrize(
    ("relative", "named"),
    [
        ("notes.md", "notes.md"),
        ("rules/README.txt", "README.txt"),
        ("rules/README.md", "README.md"),
        ("references/data.json", "data.json"),
        ("references/deep/x.md", "deep"),
        ("scripts/run.sh", "run.sh"),
    ],
)
def test_inventory_names_what_a_core_skill_may_not_hold(
    tmp_path: Path, relative: str, named: str
) -> None:
    skill_dir = _scratch_skill(tmp_path, {relative: "x\n"})

    problems = inventory_problems(skill_dir)

    assert len(problems) == 1 and named in problems[0], problems


def test_nesting_check_flags_a_nested_reference_path_not_a_bare_tree(tmp_path: Path) -> None:
    """D78(16): a rule may draw a skill tree; only ``references/<dir>/`` is real nesting."""
    tree = "```\nreferences/\n  guide.md\n```\nOpen references/guide.md.\n"
    nested = "Open references/deep/guide.md.\n"
    flat = _scratch_skill(tmp_path, {"rules/demo-rule.md": _RULE + tree}, skill_id="flat")
    deep = _scratch_skill(tmp_path, {"rules/demo-rule.md": _RULE + nested}, skill_id="deep")

    assert nesting_problems(flat) == []
    [problem] = nesting_problems(deep)
    assert "rules/demo-rule.md" in problem and "references/deep/" in problem


def test_the_engine_test_run_never_collects_example_code() -> None:
    """D48: examples run in their own CI job; the engine's pytest reads only tests/."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        options = tomllib.load(handle)["tool"]["pytest"]["ini_options"]
    assert options["testpaths"] == ["tests"]


def test_ci_runs_every_core_example_in_its_own_environment() -> None:
    """D48: one job finds each examples/<app>/pyproject.toml; uv runs its tests and mypy on 3.10 and 3.12."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = workflow.partition("\n  core-examples:\n")[2].partition("\n  wheel-smoke:\n")[0]
    assert "'*/examples/*/pyproject.toml'" in job
    assert 'uv run --directory "$example" pytest' in job
    assert 'uv run --directory "$example" mypy' in job
    assert 'python-version: ["3.10", "3.12"]' in job


@pytest.mark.parametrize("adapter", [ClaudeCodeAdapter, OpenCodeAdapter, SharedSkillsAdapter])
def test_native_skill_roots_are_dot_directories(adapter: type[Adapter]) -> None:
    """D48: pytest skips dot-directories, so a consumer's test run never collects a synced example.

    The ``agent_harness`` tree is not a dot-directory; its ``skills/conftest.py``
    keeps pytest out instead (``tests/agent_harness/test_skill_examples.py``).
    """
    root = adapter.native_skills_root
    assert root is not None and root.startswith("."), root
