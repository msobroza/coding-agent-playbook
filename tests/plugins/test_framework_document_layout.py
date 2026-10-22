"""The bundled frameworks write their specs and plans in the document layout (D60, D61).

Both bundled spec-driven frameworks, ``superpowers`` and ``mattpocock_skills``, name
the D60 default paths (``docs/specs/``, ``docs/plans/``) in their own text, so the
layout adapter (D71) rewrites them for a repo whose ``[layout]`` differs and neither
framework needs ``[layout_aliases]``. ``.scratch/`` stays only as the throwaway
prototype directory: no file names a path below it. ``ATTRIBUTIONS.md`` is not
scanned, since its change list records the upstream paths each edit replaced.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Final

import pytest

pytestmark = pytest.mark.catalog

_PLUGINS_ROOT: Final = Path(__file__).resolve().parents[2] / "catalog" / "plugins"
_FRAMEWORKS: Final = ("superpowers", "mattpocock_skills")

#: A framework's own document folder, or any path below ``.scratch/``.
_OFF_LAYOUT_RE: Final = re.compile(r"docs/superpowers/|\.scratch/[^\s`'\")]")


def _framework_files(plugin: str) -> list[Path]:
    root = _PLUGINS_ROOT / plugin
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"ATTRIBUTIONS.md", "LICENSE"}
    )


@pytest.mark.parametrize("plugin", _FRAMEWORKS)
def test_no_framework_file_names_a_document_path_outside_the_layout(plugin: str) -> None:
    hits = [
        f"{path.relative_to(_PLUGINS_ROOT)}:{number}: {line.strip()}"
        for path in _framework_files(plugin)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _OFF_LAYOUT_RE.search(line)
    ]
    assert hits == [], "write specs to docs/specs/ and plans to docs/plans/ (D60)"


@pytest.mark.parametrize("plugin", _FRAMEWORKS)
def test_framework_declares_no_layout_aliases(plugin: str) -> None:
    metadata = tomllib.loads((_PLUGINS_ROOT / plugin / "framework.toml").read_text("utf-8"))
    assert "layout_aliases" not in metadata


#: Each path edit of D61: (plugin, file under skills/, the edited text it now holds).
PATH_EDITS: Final[tuple[tuple[str, str, str], ...]] = (
    ("superpowers", "brainstorming/SKILL.md", "`docs/specs/YYYY-MM-DD-<topic>-design.md`"),
    ("superpowers", "writing-plans/SKILL.md", "`docs/plans/YYYY-MM-DD-<feature-name>.md`"),
    ("superpowers", "writing-plans/SKILL.md", "saved to `docs/plans/<filename>.md`"),
    ("superpowers", "requesting-code-review/SKILL.md", "from docs/plans/deployment-plan.md"),
    ("superpowers", "executing-plans/SKILL.md", "plan once: docs/plans/feature-plan.md"),
    ("superpowers", "executing-plans/SKILL.md", "sdd-workspace docs/plans/feature-plan.md"),
    (
        "superpowers",
        "subagent-driven-development/SKILL.md",
        "file once: docs/plans/feature-plan.md",
    ),
    (
        "superpowers",
        "subagent-driven-development/SKILL.md",
        "scripts/sdd-workspace docs/plans/feature-plan.md",
    ),
    (
        "mattpocock_skills",
        "setup-matt-pocock-skills/references/issue-tracker-local.md",
        "The spec is `docs/specs/YYYY-MM-DD-<feature-slug>.md`",
    ),
    (
        "mattpocock_skills",
        "setup-matt-pocock-skills/references/issue-tracker-local.md",
        "`docs/plans/YYYY-MM-DD-<feature-slug>/<NN>-<slug>.md`",
    ),
    (
        "mattpocock_skills",
        "setup-matt-pocock-skills/references/issue-tracker-local.md",
        "**Map**: `docs/plans/YYYY-MM-DD-<effort>.md`",
    ),
    (
        "mattpocock_skills",
        "setup-matt-pocock-skills/references/issue-tracker-local.md",
        "**Child ticket**: `docs/plans/YYYY-MM-DD-<effort>/NN-<slug>.md`",
    ),
    (
        "mattpocock_skills",
        "to-tickets/SKILL.md",
        "under `docs/plans/YYYY-MM-DD-<feature-slug>/<NN>-<slug>.md`",
    ),
    (
        "mattpocock_skills",
        "ask-matt/SKILL.md",
        "one file per ticket under `docs/plans/YYYY-MM-DD-<feature>/`",
    ),
    (
        "mattpocock_skills",
        "setup-matt-pocock-skills/SKILL.md",
        "issues live as files under `docs/plans/YYYY-MM-DD-<feature>/`",
    ),
    (
        "mattpocock_skills",
        "two-axis-review/SKILL.md",
        "A spec file under `docs/specs/`, `docs/`, or `specs/`",
    ),
)


@pytest.mark.parametrize(("plugin", "file", "text"), PATH_EDITS)
def test_each_path_edit_names_the_default_layout(plugin: str, file: str, text: str) -> None:
    path = _PLUGINS_ROOT / plugin / "skills" / file
    assert text in path.read_text(encoding="utf-8")
