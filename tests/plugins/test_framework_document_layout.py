"""The bundled frameworks write their specs and plans in the document layout (D60, D61).

Both bundled spec-driven frameworks, ``superpowers`` and ``mattpocock_skills``, name
the D60 default paths (``docs/specs/``, ``docs/plans/``) in their own text, so the
layout adapter (D71) rewrites them for a repo whose ``[layout]`` differs and neither
framework needs ``[layout_aliases]`` (``tests/config/test_framework.py`` pins that). ``.scratch/`` stays only as the throwaway
prototype directory: no file names a path below it. ``ATTRIBUTIONS.md`` is not
scanned, since its change list records the upstream paths each edit replaced.
"""

from __future__ import annotations

import hashlib
import re
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


#: The D60 default paths each D61 path edit wrote, as (old text, new text).
_Edits = tuple[tuple[str, str], ...]

_PLAN_EXAMPLE: Final[_Edits] = (
    ("docs/superpowers/plans/feature-plan.md", "docs/plans/feature-plan.md"),
)
_TRACKER_SEED: Final[_Edits] = (
    (
        "Issues and specs for this repo live as markdown files in `.scratch/`.",
        "Issues and specs for this repo live as markdown files in `docs/specs/` and `docs/plans/`.",
    ),
    (
        "- One feature per directory: `.scratch/<feature-slug>/`",
        "- One feature per slug, dated when it is created: `YYYY-MM-DD-<feature-slug>`",
    ),
    (
        "- The spec is `.scratch/<feature-slug>/spec.md`",
        "- The spec is `docs/specs/YYYY-MM-DD-<feature-slug>.md`",
    ),
    (
        "one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`",
        "one file per ticket at `docs/plans/YYYY-MM-DD-<feature-slug>/<NN>-<slug>.md`",
    ),
    (
        "- `.scratch/` is untracked working state: never stage it in a commit",
        "- `.scratch/` holds only throwaway prototypes, never a spec, ticket or map: "
        "never stage it in a commit",
    ),
    (
        "Create a new file under `.scratch/<feature-slug>/` (creating",
        "Create the spec at `docs/specs/YYYY-MM-DD-<feature-slug>.md`, or a ticket under "
        "`docs/plans/YYYY-MM-DD-<feature-slug>/` (creating",
    ),
    ("- **Map**: `.scratch/<effort>/map.md`", "- **Map**: `docs/plans/YYYY-MM-DD-<effort>.md`"),
    (
        "- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`",
        "- **Child ticket**: `docs/plans/YYYY-MM-DD-<effort>/NN-<slug>.md`",
    ),
    (
        "- **Frontier**: scan `.scratch/<effort>/issues/` for",
        "- **Frontier**: scan `docs/plans/YYYY-MM-DD-<effort>/` for",
    ),
    ("Decisions-so-far in `map.md`.", "Decisions-so-far in the map file."),
    ("appends to `map.md`;", "appends to the map file;"),
)

#: Each file D61 edited: (plugin, file under skills/, SHA-256 of its text before
#: the edits, the edits). Undoing exactly these edits must give back that text,
#: so an unlisted change to an edited file fails here.
PATH_EDITS: Final[tuple[tuple[str, str, str, _Edits], ...]] = (
    (
        "superpowers",
        "brainstorming/SKILL.md",
        "0a8beb71b1b8cb89fd1132db58c78d3630ad7cdd3e10daaa254b1713e36eee1d",
        (
            (
                "`docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`",
                "`docs/specs/YYYY-MM-DD-<topic>-design.md`",
            ),
        ),
    ),
    (
        "superpowers",
        "writing-plans/SKILL.md",
        "75c7554b61fe5d59e8bc76752d7fcac825821d8526b77c4d88bf159a056a958a",
        (
            (
                "`docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`",
                "`docs/plans/YYYY-MM-DD-<feature-name>.md`",
            ),
            (
                "saved to `docs/superpowers/plans/<filename>.md`",
                "saved to `docs/plans/<filename>.md`",
            ),
        ),
    ),
    (
        "superpowers",
        "requesting-code-review/SKILL.md",
        "0cfe103a8b67d99a075223c999ed9bef80c23ff1d0ad94d68e65ed488e8c0540",
        (("docs/superpowers/plans/deployment-plan.md", "docs/plans/deployment-plan.md"),),
    ),
    (
        "superpowers",
        "executing-plans/SKILL.md",
        "c5492ec5b2fe3278c1b08b44494cc8639f583f43202cf686824323b7811225d9",
        _PLAN_EXAMPLE,
    ),
    (
        "superpowers",
        "subagent-driven-development/SKILL.md",
        "3c29b8d8d463ec9b5dc237da54ae840ef5c1c991211d4ecc8649e8b75ae491b7",
        _PLAN_EXAMPLE,
    ),
    (
        "mattpocock_skills",
        "ask-matt/SKILL.md",
        "7e59df484a2d4f67be83eb996f3aa87d333107f5c8ab664e9a3dfeece3fc42ce",
        (
            (
                "one file per ticket under `.scratch/<feature>/issues/`",
                "one file per ticket under `docs/plans/YYYY-MM-DD-<feature>/`",
            ),
        ),
    ),
    (
        "mattpocock_skills",
        "setup-matt-pocock-skills/SKILL.md",
        "bd24426a13744d7d6995156efe834c1fd9afb2a2d5d5eec2694afd3edf54be21",
        (
            (
                "- `.scratch/`: a sign that",
                "- `docs/specs/` and `docs/plans/`: a sign that",
            ),
            (
                "write a markdown file under `.scratch/` or follow",
                "write a markdown file under `docs/specs/` or `docs/plans/` or follow",
            ),
            (
                "issues live as files under `.scratch/<feature>/` in this repo",
                "issues live as files under `docs/plans/YYYY-MM-DD-<feature>/` in this repo",
            ),
        ),
    ),
    (
        "mattpocock_skills",
        "setup-matt-pocock-skills/references/issue-tracker-local.md",
        "1c717bd6bb25a0e2fe4fd9e9944b04ce5bb61de46dbd7647521ebf725d103311",
        _TRACKER_SEED,
    ),
    (
        "mattpocock_skills",
        "to-tickets/SKILL.md",
        "adf2116e7575cd583bc48cfe87a40dbd52f55be45ef4c57be20736a7999cce1f",
        (
            (
                "under `.scratch/<feature-slug>/issues/<NN>-<slug>.md`",
                "under `docs/plans/YYYY-MM-DD-<feature-slug>/<NN>-<slug>.md`",
            ),
        ),
    ),
    (
        "mattpocock_skills",
        "two-axis-review/SKILL.md",
        "1dd02cf46ad6cb40eebbcd2258d63651ff3abf603ae63be64845234d84fd4871",
        (
            (
                "A spec file under `docs/`, `specs/`, or `.scratch/`",
                "A spec file under `docs/specs/`, `docs/`, or `specs/`",
            ),
        ),
    ),
)


def _edited_text(plugin: str, file: str) -> str:
    return (_PLUGINS_ROOT / plugin / "skills" / file).read_text(encoding="utf-8")


def _ids(case: tuple[str, str, str, _Edits]) -> str:
    return f"{case[0]}/{case[1]}"


@pytest.mark.parametrize("case", PATH_EDITS, ids=_ids)
def test_each_path_edit_names_the_default_layout(case: tuple[str, str, str, _Edits]) -> None:
    plugin, file, _, edits = case
    text = _edited_text(plugin, file)
    assert [new for _, new in edits if new not in text] == []


@pytest.mark.parametrize("case", PATH_EDITS, ids=_ids)
def test_the_path_edits_are_the_only_changes_to_an_edited_file(
    case: tuple[str, str, str, _Edits],
) -> None:
    """Undoing the listed edits restores the vendored text byte for byte (D61)."""
    plugin, file, digest, edits = case
    text = _edited_text(plugin, file)
    for old, new in edits:
        text = text.replace(new, old)
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == digest
