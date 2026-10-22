"""CI gate: ``catalog/core/ATTRIBUTIONS.md`` maps every vendored core file (ADR 0004, D31).

Core copies upstream Python guidance and adapts it (D1). The credit and the
provenance live in one file: one section per source with its D11 pin, and inside
it one table per core skill mapping each upstream file to the core files it
became, or to DROP with a reason. A per-skill ``Engine-written files`` list
covers the files with no upstream text. A distilled source (prU D50) has no
pin: its rows credit engine-written files by page, or DROP them. The parser is
``tests/_attributions.py``; each check here runs once on the shipped file and once
on a synthetic tree.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from tests._attributions import (
    ATTRIBUTIONS_PATH,
    SOURCE_PINS,
    Attributions,
    attribution_errors,
    distill_action_errors,
    distill_actions,
    load_core_attributions,
    parse_attributions,
    write_tree,
)
from tests._catalog import CORE_SKILLS_ROOT

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_PIN = "a" * 40
_LICENSE = b"MIT License\n\nCopyright (c) 2026 Somebody\n"

_SYNTHETIC = textwrap.dedent(
    f"""\
    # Attributions

    Header prose.

    ## up-source

    Source: an upstream collection.
    Commit: `{_PIN}`
    License: MIT License.

    ### alpha

    | Upstream file | Core files | Changes |
    | --- | --- | --- |
    | `skills/a.md` | `rules/a.md`, `references/guide.md` | Engine frontmatter; no URLs. |
    | `skills/b.md` | DROP | Recommends a tool the engine does not adopt. |

    Distilled (credited by name only, no vendored text):

    - `rules/d.md`

    ## Engine-written files

    ### alpha

    - `SKILL.md`
    """
)


# --------------------------------------------------------------------------- #
# The shipped file.
# --------------------------------------------------------------------------- #


def test_core_attributions_map_every_core_skill_file() -> None:
    errors = attribution_errors(load_core_attributions())
    assert errors == [], "catalog/core/ATTRIBUTIONS.md is out of step:\n" + "\n".join(errors)


def test_core_attributions_name_both_pins_and_drop_the_fresh_text_policy() -> None:
    """ADR 0004 retires 'written fresh' and the prS pin; D11's two commits replace them."""
    text = ATTRIBUTIONS_PATH.read_text(encoding="utf-8")
    assert "written fresh" not in text
    assert "bf64c51" not in text
    assert dict(SOURCE_PINS) == {
        "python-best-practices": "fa0d3f58afb8bf56c028bb559e0e7bc1538e079a",
        "python-clean-architecture": "9d627ca7bedbe0bb9e2fcf3c83d81814a6133dce",
    }
    commits = {
        name: source.commit
        for name, source in load_core_attributions().sources.items()
        if not source.distilled
    }
    assert commits == dict(SOURCE_PINS)


@pytest.mark.parametrize(
    ("skill", "dropped", "used"),
    [
        ("domino-apps", "user_guide/71635d", "user_guide/cb9195"),
        ("domino-jobs", "user_guide/66b789", "user_guide/da707d"),
        ("domino-jobs", "legal/terms", "user_guide/fda6d8"),
        ("domino-jobs", "user_guide/ca786d", "user_guide/55fc89"),
    ],
)
def test_core_attributions_record_the_domino_docs_drops_per_page(
    skill: str, dropped: str, used: str
) -> None:
    """prU D50: the distilled Domino documentation has page rows, DROP rows included.

    Each row keeps the mapping's page id (its path, never a URL host), so a mapping
    drop is traceable by id.
    """
    source = load_core_attributions().sources["domino-docs"]
    assert source.distilled
    assert source.commit is None
    rows = source.skills[skill].rows
    assert dropped in {row.upstream for row in rows if row.dropped}
    assert used in {row.upstream for row in rows if not row.dropped}


def test_core_attributions_record_the_domino_jobs_pages_and_drops() -> None:
    """prU D50: domino-jobs credits each page its rules restate and drops the rest."""
    rows = load_core_attributions().sources["domino-docs"].skills["domino-jobs"].rows
    used = {row.upstream: row.targets for row in rows if not row.dropped}
    assert "rules/domino-job-schedules.md" in used["user_guide/5dce1f"]
    assert "rules/domino-launch-jobs-from-code.md" in used["api_guide/c5ef26"]
    assert "user_guide/db2820" in {row.upstream for row in rows if row.dropped}


def test_core_attributions_list_engine_written_files_per_core_skill() -> None:
    """Every core skill has its own Engine-written list, so lanes never share one."""
    on_disk = {p.name for p in CORE_SKILLS_ROOT.iterdir() if p.is_dir()}
    assert on_disk <= set(load_core_attributions().engine_written)


def test_core_attributions_list_no_distilled_rule_as_a_mapping_target() -> None:
    """D78(15): a rule its mapping spec distills holds no upstream text, so no row maps to it."""
    errors = distill_action_errors(load_core_attributions(), distill_actions())
    assert errors == [], "\n".join(errors)


def test_distill_actions_read_each_mapping_spec() -> None:
    """Guard against a spec reader that silently finds no distilled rule."""
    assert "rules/python-comments-why.md" in distill_actions()["python-coding"]


# --------------------------------------------------------------------------- #
# The parser and the checks, on synthetic input.
# --------------------------------------------------------------------------- #


def _parsed(text: str = _SYNTHETIC) -> Attributions:
    return parse_attributions(text)


def test_parse_reads_sources_pins_rows_distilled_and_engine_written() -> None:
    parsed = _parsed()

    source = parsed.sources["up-source"]
    assert source.commit == _PIN
    alpha = source.skills["alpha"]
    assert [(r.upstream, r.targets, r.dropped) for r in alpha.rows] == [
        ("skills/a.md", ("rules/a.md", "references/guide.md"), False),
        ("skills/b.md", (), True),
    ]
    assert alpha.rows[1].changes == "Recommends a tool the engine does not adopt."
    assert alpha.distilled == ("rules/d.md",)
    assert parsed.engine_written == {"alpha": ("SKILL.md",)}


@pytest.mark.parametrize(
    ("line", "match"),
    [
        ("| `skills/c.md` | `rules/c.md` |", r":16: a mapping row needs 3 cells"),
        ("| skills/c.md | `rules/c.md` | Changed. |", r":16: expected one `path` in backticks"),
        ("| `skills/c.md` | rules/c.md | Changed. |", r":16: expected one `path` in backticks"),
    ],
)
def test_parse_rejects_a_malformed_row(line: str, match: str) -> None:
    text = _SYNTHETIC.replace("| `skills/b.md` | DROP", f"{line}\n| `skills/b.md` | DROP")
    with pytest.raises(ValueError, match=match):
        parse_attributions(text)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("| `a.md` | `b.md` | Changed. |\n", r":1: a table row outside a source's skill"),
        ("## src\n| `a.md` | `b.md` | Changed. |\n", r":2: a table row outside"),
        ("## Engine-written files\n### s\n| `a.md` | `b.md` | x |\n", r":3: a table row outside"),
        ("- `SKILL.md`\n", r":1: a listed file outside a skill: '- `SKILL.md`'"),
        ("## Engine-written files\nCommit: `abc`\n", r":2: a Commit line belongs under a source"),
        ("## src\n### s\nCommit: `abc`\n", r":3: a Commit line belongs under a source"),
        ("## src\n### s\nForm: distilled.\n", r":3: a Form line belongs under a source"),
        ("### s\n", r":1: skill heading 's' before any section"),
    ],
)
def test_parse_rejects_a_misplaced_line(text: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_attributions(text)


#: The synthetic skill tree that :data:`_SYNTHETIC` describes exactly.
_TREE: dict[str, bytes] = {
    "alpha/SKILL.md": b"# Alpha\n",
    "alpha/rules/a.md": b"# A\n",
    "alpha/rules/d.md": b"# D\n",
    "alpha/references/guide.md": b"# Guide\n",
    "alpha/references/LICENSE.up-source": _LICENSE,
}


def _errors(
    tmp_path: Path, text: str = _SYNTHETIC, tree: dict[str, bytes] | None = None
) -> list[str]:
    write_tree(tmp_path, _TREE if tree is None else tree)
    return attribution_errors(
        parse_attributions(text), tmp_path, pins={"up-source": _PIN}, sources=("up-source",)
    )


def test_a_consistent_mapping_has_no_errors(tmp_path: Path) -> None:
    assert _errors(tmp_path) == []


def test_a_wrong_pin_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace(_PIN, "b" * 40)
    assert _errors(tmp_path, text) == [
        f"up-source: commit {'b' * 40} does not match the D11 pin {_PIN}"
    ]


def test_a_missing_or_unknown_source_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("## up-source", "## other-source")
    errors = _errors(tmp_path, text)
    assert "up-source: no section for this pinned source" in errors
    assert "other-source: a source without a D11 pin" in errors


def test_a_dangling_core_path_fails(tmp_path: Path) -> None:
    tree = {k: v for k, v in _TREE.items() if k != "alpha/rules/d.md"}
    assert _errors(tmp_path, tree=tree) == [
        "alpha/rules/d.md: listed in ATTRIBUTIONS.md but not in the skill"
    ]


def test_an_unlisted_core_skill_file_fails(tmp_path: Path) -> None:
    tree = {**_TREE, "alpha/scripts/tool.py": b"print()\n", "beta/SKILL.md": b"# Beta\n"}
    assert _errors(tmp_path, tree=tree) == [
        "alpha/scripts/tool.py: neither a mapping target nor engine-written in ATTRIBUTIONS.md",
        "beta/SKILL.md: neither a mapping target nor engine-written in ATTRIBUTIONS.md",
    ]


def test_a_directory_target_covers_every_file_under_it(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("`references/guide.md`", "`references/guide.md`, `examples/app/`")
    tree = {**_TREE, "alpha/examples/app/main.py": b"x = 1\n", "alpha/examples/app/a/b.py": b""}
    assert _errors(tmp_path, text, tree) == []


def test_a_drop_row_without_a_reason_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("Recommends a tool the engine does not adopt.", "")
    assert _errors(tmp_path, text) == ["up-source/alpha: `skills/b.md` is dropped without a reason"]


def test_a_mapped_row_without_changes_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("Engine frontmatter; no URLs.", "")
    assert _errors(tmp_path, text) == ["up-source/alpha: `skills/a.md` lists no changes"]


def test_an_upstream_file_mapped_twice_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("`skills/b.md` | DROP", "`skills/a.md` | DROP")
    # The message names the skill whose table holds the duplicate: the file may feed others.
    assert _errors(tmp_path, text) == [
        "up-source/alpha: `skills/a.md` appears in more than one row"
    ]


def test_an_upstream_file_may_feed_two_skills_one_row_each(tmp_path: Path) -> None:
    """A long upstream reference can feed rules of two skills (prU mapping handovers).

    Each skill's sub-section lists the core files of that skill, so the file gets one
    row per skill; twice in one skill's table still fails.
    """
    beta = "\n### beta\n\n| Upstream file | Core files | Changes |\n| --- | --- | --- |\n"
    beta += "| `skills/a.md` | `rules/b.md` | Lines 3-4 become a Note. |\n"
    text = _SYNTHETIC.replace("\n## Engine-written files", beta + "\n## Engine-written files")
    tree = {
        **_TREE,
        "beta/SKILL.md": b"# Beta\n",
        "beta/rules/b.md": b"# B\n",
        "beta/references/LICENSE.up-source": _LICENSE,
    }
    text = text.replace(
        "### alpha\n\n- `SKILL.md`", "### alpha\n\n- `SKILL.md`\n\n### beta\n\n- `SKILL.md`"
    )

    assert _errors(tmp_path, text, tree) == []


def test_an_upstream_file_may_feed_several_skills_one_row_each(tmp_path: Path) -> None:
    beta = "### beta\n\n| Upstream file | Core files | Changes |\n| --- | --- | --- |\n"
    twice = _SYNTHETIC.replace(
        "## Engine-written files",
        beta + "| `skills/a.md` | DROP | Not beta material. |\n\n## Engine-written files",
        1,
    )
    assert _errors(tmp_path, twice) == []


def test_a_file_both_engine_written_and_mapped_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("- `SKILL.md`", "- `SKILL.md`\n- `rules/a.md`")
    assert _errors(tmp_path, text) == [
        "alpha/rules/a.md: listed as engine-written and as holding upstream text"
    ]


def test_targets_without_a_license_copy_fail(tmp_path: Path) -> None:
    tree = {k: v for k, v in _TREE.items() if "LICENSE" not in k}
    assert _errors(tmp_path, tree=tree) == [
        "alpha: holds text from up-source but ships no references/LICENSE.up-source"
    ]


def test_a_license_copy_without_targets_fails(tmp_path: Path) -> None:
    tree = {**_TREE, "beta/SKILL.md": b"# Beta\n", "beta/references/LICENSE.up-source": _LICENSE}
    text = _SYNTHETIC + "\n### beta\n\n- `SKILL.md`\n"
    assert _errors(tmp_path, text, tree) == [
        "beta: ships references/LICENSE.up-source but holds no text from up-source"
    ]


def test_a_distilled_file_needs_no_license_copy(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace(
        "| `skills/a.md` | `rules/a.md`, `references/guide.md` | Engine frontmatter; no URLs. |\n",
        "",
    ).replace("- `SKILL.md`", "- `SKILL.md`\n- `rules/a.md`\n- `references/guide.md`")
    tree = {k: v for k, v in _TREE.items() if "LICENSE" not in k}
    assert _errors(tmp_path, text, tree) == []


def test_a_changed_license_copy_is_left_to_the_license_gate(tmp_path: Path) -> None:
    """One home per check: the bytes are test_core_license_copies.py's, not this gate's."""
    tree = {**_TREE, "alpha/references/LICENSE.up-source": _LICENSE + b"\n"}
    assert _errors(tmp_path, tree=tree) == []


def test_a_file_both_distilled_and_mapped_fails(tmp_path: Path) -> None:
    """D78(15): a distilled file is credited by name only, never with a change list."""
    text = _SYNTHETIC.replace("- `rules/d.md`", "- `rules/d.md`\n- `rules/a.md`")
    assert _errors(tmp_path, text) == [
        "alpha/rules/a.md: listed as distilled and as a mapping target with a change list"
    ]


def test_a_mapped_skill_without_a_directory_fails_once(tmp_path: Path) -> None:
    text = _SYNTHETIC + "\n### gamma\n\n- `SKILL.md`\n- `rules/g.md`\n"
    assert _errors(tmp_path, text) == [
        "gamma: ATTRIBUTIONS.md lists its files, but core ships no such skill"
    ]


def test_an_empty_sub_section_for_a_skill_not_created_yet_passes(tmp_path: Path) -> None:
    """A lane's seeded, empty sub-section is fine before its skill exists."""
    assert _errors(tmp_path, _SYNTHETIC + "\n### gamma\n") == []


def test_a_distill_action_listed_as_a_mapping_target_fails() -> None:
    actions = {"alpha": {"rules/a.md", "rules/d.md"}, "beta": {"rules/a.md"}}
    assert distill_action_errors(_parsed(), actions) == [
        "alpha/rules/a.md: the mapping spec distills it, but a table row maps upstream text to it"
    ]


def test_a_distill_action_matches_a_jinja_target() -> None:
    text = _SYNTHETIC.replace("`rules/a.md`, `references", "`rules/a.md.j2`, `references")
    assert distill_action_errors(_parsed(text), {"alpha": {"rules/a.md"}}) == [
        "alpha/rules/a.md: the mapping spec distills it, but a table row maps upstream text to it"
    ]


def test_distill_actions_read_the_action_column(tmp_path: Path) -> None:
    write_tree(
        tmp_path,
        {
            "mapping-alpha.md": (
                "| Rule file | Section | Priority | Action | Est. lines |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| `rules/a.md` | s (HIGH) | 1 | distill | 40 |\n"
                "| `rules/b.md` | s (HIGH) | 2 | split-new | 40 |\n"
                "| `references/c.md` | x | y | distill | z |\n"
            ),
            "mapping-beta.md": "No table.\n",
        },
    )
    assert distill_actions(tmp_path) == {"alpha": frozenset({"rules/a.md"}), "beta": frozenset()}


# --------------------------------------------------------------------------- #
# A distilled source (prU D50): credited by name, no pin, no license copy.
# --------------------------------------------------------------------------- #

_DISTILLED_SECTION = textwrap.dedent(
    """\
    ## docs-source

    Source: documentation without an open license.
    Form: distilled (credited by name only, not vendored).

    ### alpha

    | Upstream file | Core files | Changes |
    | --- | --- | --- |
    | `guide/p1` | `SKILL.md` | Facts restated in the engine's own words. |
    | `guide/p2` | DROP | A landing page with nothing actionable. |

    """
)


def _with_distilled(section: str = _DISTILLED_SECTION) -> str:
    return _SYNTHETIC.replace("## Engine-written files", section + "## Engine-written files")


def test_parse_marks_a_distilled_source_without_a_pin() -> None:
    source = _parsed(_with_distilled()).sources["docs-source"]

    assert source.distilled
    assert source.commit is None
    assert [(r.upstream, r.targets) for r in source.skills["alpha"].rows] == [
        ("guide/p1", ("SKILL.md",)),
        ("guide/p2", ()),
    ]
    assert not _parsed().sources["up-source"].distilled


def test_a_distilled_source_needs_no_pin_and_no_license_copy(tmp_path: Path) -> None:
    """Its rows credit engine-written files: they hold no upstream text (D50)."""
    assert _errors(tmp_path, _with_distilled()) == []


def test_a_distilled_source_with_a_commit_pin_fails(tmp_path: Path) -> None:
    section = _DISTILLED_SECTION.replace("Form: distilled", f"Commit: `{_PIN}`\nForm: distilled")
    assert _errors(tmp_path, _with_distilled(section)) == [
        "docs-source: a distilled source carries no commit pin"
    ]


def test_a_distilled_row_crediting_a_vendored_file_fails(tmp_path: Path) -> None:
    section = _DISTILLED_SECTION.replace("| `SKILL.md` |", "| `rules/a.md` |")
    assert _errors(tmp_path, _with_distilled(section)) == [
        "alpha/rules/a.md: credited to a distilled source but not listed as engine-written"
        " or distilled"
    ]


def test_a_distilled_page_may_feed_several_skills_but_one_row_each(tmp_path: Path) -> None:
    beta = "### beta\n\n| Upstream file | Core files | Changes |\n| --- | --- | --- |\n"
    twice = _DISTILLED_SECTION + beta + "| `guide/p1` | DROP | Not beta material. |\n\n"
    assert _errors(tmp_path, _with_distilled(twice)) == []

    section = _DISTILLED_SECTION.replace("`guide/p2` | DROP", "`guide/p1` | DROP")
    assert _errors(tmp_path, _with_distilled(section)) == [
        "docs-source/alpha: `guide/p1` appears in more than one row"
    ]


def test_a_distilled_source_row_is_not_a_distill_action_conflict() -> None:
    """Its targets hold no upstream text, so a rule the mapping distills may be one."""
    section = _DISTILLED_SECTION.replace("| `SKILL.md` |", "| `rules/d.md` |")
    assert distill_action_errors(_parsed(_with_distilled(section)), {"alpha": {"rules/d.md"}}) == []
