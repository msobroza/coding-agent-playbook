"""prU F-02: the final state of the vendored core skills, checked once every lane has merged.

Each lane pins its own skill; these checks span them all, on the shipped tree:

- every section a core skill declares holds at least one member rule;
- every file under a core skill's ``references/`` and ``examples/`` (license files
  excepted) is covered by its ``playbook.references`` (D47), for every core skill,
  not only those ``playbook validate``'s check reaches (it skips skills that
  declare neither sections nor references);
- the ids prU retires (D21) are gone from core and no file reuses them;
- every core skill with a ``playbook:`` block has an active member on its probe:
  the reference probe, or the Domino (D63) or authoring (D70) probe for the skills
  only those activate;
- every upstream file at the two D11 pins has an ``ATTRIBUTIONS.md`` row, and every
  row names an upstream file that exists there (the paths-only inventories under
  ``tests/fixtures/upstream_inventory/`` were listed once from the pinned clones);
  a second row for one file in one skill's sub-table already fails
  ``tests/_attributions.attribution_errors`` (D31 keeps one sub-table per skill, so
  a file feeding several skills has one row in each);
- the reference probe's "Where guidance lives" map is the one sync renders, with a
  line for each of the eight skills it activates (D4). Its 800-word cap with the
  always rules and the 1,500-word ``AGENTS.md`` cap (D35) live in
  ``tests/integration/test_context_budget.py``, on the same probe.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.skills.document import where_entry, where_guidance_section
from coding_agent_playbook.sync.render import render_artifacts
from coding_agent_playbook.validation.context import SyncContext
from tests._attributions import load_core_attributions
from tests._catalog import CORE_ROOT, CORE_SKILLS_ROOT, REPO_ROOT, RETIRED_RULE_IDS, core_rules
from tests._core_skill_layout import LICENSE_COPY_NAMES
from tests.core_skill_pins import ALL_PINS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from tests.core_skill_pins import CoreSkillPins

pytestmark = pytest.mark.catalog

INVENTORY_DIR: Final = REPO_ROOT / "tests" / "fixtures" / "upstream_inventory"
#: Source name in ATTRIBUTIONS.md -> its inventory, the ``git ls-tree -r`` paths at the D11 pin.
UPSTREAM_INVENTORIES: Final[Mapping[str, Path]] = {
    "python-best-practices": INVENTORY_DIR / "pbp-fa0d3f58.txt",
    "python-clean-architecture": INVENTORY_DIR / "pca-9d627ca.txt",
}
_LISTED_DIRS: Final = ("references", "examples")
#: Tool caches a local test run may leave inside an example app; never shipped.
_CACHE_DIRS: Final = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})


def _playbook_block(skill_dir: Path) -> dict[str, object]:
    """The ``playbook:`` block of ``skill_dir``'s authored ``SKILL.md``; ``{}`` without one."""
    frontmatter, _ = split_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    block = frontmatter.get("playbook")
    return block if isinstance(block, dict) else {}


def _core_skill_dirs() -> list[Path]:
    return sorted(path for path in CORE_SKILLS_ROOT.iterdir() if path.is_dir())


def _declared_section_ids(skill_dir: Path) -> list[str]:
    sections = _playbook_block(skill_dir).get("sections") or []
    assert isinstance(sections, list), f"{skill_dir.name}: sections is {sections!r}"
    for section in sections:
        assert isinstance(section, dict) and "id" in section, (
            f"{skill_dir.name}: section {section!r} is not a mapping with an id"
        )
    return [str(section["id"]) for section in sections]


def _listable_files(skill_dir: Path) -> list[PurePosixPath]:
    """Every shipped file under ``references/`` and ``examples/``, license copies excepted."""
    files = []
    for name in _LISTED_DIRS:
        for path in (skill_dir / name).rglob("*"):
            relative = PurePosixPath(path.relative_to(skill_dir).as_posix())
            if path.is_file() and not _CACHE_DIRS.intersection(relative.parts):
                files.append(relative)
    return sorted(f for f in files if f.name not in LICENSE_COPY_NAMES)


def _listed_reference_paths(skill_dir: Path) -> list[PurePosixPath]:
    entries = _playbook_block(skill_dir).get("references") or []
    assert isinstance(entries, list), f"{skill_dir.name}: references is {entries!r}"
    for entry in entries:
        assert isinstance(entry, dict) and "path" in entry, (
            f"{skill_dir.name}: reference {entry!r} is not a mapping with a path"
        )
    return [PurePosixPath(str(entry["path"])) for entry in entries]


@pytest.mark.parametrize("skill_dir", _core_skill_dirs(), ids=lambda path: path.name)
def test_every_declared_section_has_a_member(skill_dir: Path) -> None:
    members = [r for r in core_rules().values() if r.frontmatter.skill == skill_dir.name]
    filled = {rule.frontmatter.section for rule in members}
    empty = [sid for sid in _declared_section_ids(skill_dir) if sid not in filled]
    assert not empty, f"{skill_dir.name} declares sections with no member rule: {empty}"


@pytest.mark.parametrize("skill_dir", _core_skill_dirs(), ids=lambda path: path.name)
def test_every_reference_and_example_file_is_listed(skill_dir: Path) -> None:
    listed = _listed_reference_paths(skill_dir)
    unlisted = [
        str(path)
        for path in _listable_files(skill_dir)
        if not any(path == entry or entry in path.parents for entry in listed)
    ]
    assert not unlisted, f"{skill_dir.name}: not in playbook.references: {unlisted}"


@pytest.mark.parametrize("rule_id", sorted(RETIRED_RULE_IDS))
def test_retired_id_is_gone_from_core(rule_id: str) -> None:
    assert rule_id not in core_rules(), f"retired id {rule_id!r} still ships (D21)"


@pytest.mark.parametrize("rule_id", sorted(RETIRED_RULE_IDS))
def test_no_core_file_reuses_a_retired_id(rule_id: str) -> None:
    reused = [
        path.relative_to(CORE_ROOT).as_posix()
        for path in CORE_ROOT.rglob("*")
        if path.is_file() and path.name.split(".")[0] == rule_id
    ]
    assert not reused, f"retired id {rule_id!r} is reused by {reused} (D21)"


@pytest.mark.parametrize("pins", ALL_PINS, ids=lambda pins: pins.skill_id)
def test_core_skill_has_an_active_member_on_its_probe(
    pins: CoreSkillPins, request: pytest.FixtureRequest
) -> None:
    """The skill's probe writes at least one member rule into its emitted skill."""
    repo: Path = request.getfixturevalue(f"{pins.probe}_probe_repo")
    rules_dir = repo / ".claude" / "skills" / pins.skill_id / "rules"
    emitted = sorted(p.name for p in rules_dir.rglob("*.md")) if rules_dir.is_dir() else []
    assert emitted, f"the {pins.probe} probe activates no member of {pins.skill_id}"


def _inventory(source: str) -> list[str]:
    lines = UPSTREAM_INVENTORIES[source].read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line]


def _row_covers(row_path: str, upstream: str) -> bool:
    """A row names one file, a directory (ending in ``/``) or a glob of files."""
    if row_path.endswith("/"):
        return upstream.startswith(row_path)
    return fnmatch.fnmatchcase(upstream, row_path) if "*" in row_path else upstream == row_path


def _row_paths(source: str) -> set[str]:
    skills = load_core_attributions().sources[source].skills.values()
    return {row.upstream for mapping in skills for row in mapping.rows}


@pytest.mark.parametrize("source", sorted(UPSTREAM_INVENTORIES))
def test_every_upstream_file_at_the_pin_has_a_row(source: str) -> None:
    rows = _row_paths(source)
    missing = [f for f in _inventory(source) if not any(_row_covers(r, f) for r in rows)]
    assert not missing, f"{source}: upstream files with no ATTRIBUTIONS.md row: {missing}"


@pytest.mark.parametrize("source", sorted(UPSTREAM_INVENTORIES))
def test_every_row_names_an_upstream_file_at_the_pin(source: str) -> None:
    inventory = _inventory(source)
    phantom = sorted(r for r in _row_paths(source) if not any(_row_covers(r, f) for f in inventory))
    assert not phantom, f"{source}: rows name no file at the pin: {phantom}"


def test_row_covers_a_file_a_directory_or_a_glob() -> None:
    assert _row_covers("skills/a/SKILL.md", "skills/a/SKILL.md")
    assert not _row_covers("skills/a/SKILL.md", "skills/a/SKILL.md.bak")
    assert _row_covers("testing/", "testing/models/book.py")
    assert not _row_covers("testing/", "testing.md")
    assert _row_covers("skills/a/rules/*.md", "skills/a/rules/x.md")
    assert not _row_covers("skills/a/rules/*.md", "skills/a/README.md")


def test_reference_probe_where_map_lists_the_eight_reference_skills(
    reference_probe_repo: Path,
) -> None:
    """The map in ``AGENTS.md`` is the engine's, with one line per skill the probe activates."""
    rendered = render_artifacts(SyncContext.from_repo(reference_probe_repo))
    entries = [entry for skill in rendered.skills if (entry := where_entry(skill)) is not None]
    agents_md = (reference_probe_repo / "AGENTS.md").read_text(encoding="utf-8")
    assert where_guidance_section(entries) in agents_md, "AGENTS.md lacks the rendered map"
    on_reference = sorted(pins.skill_id for pins in ALL_PINS if pins.probe == "reference")
    assert sorted(entry.skill_id for entry in entries) == on_reference
